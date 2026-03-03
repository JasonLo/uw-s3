"""File Manager screen — local files + S3 objects in a unified view."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Label,
    Log,
    Select,
)

from uw_s3.sync.config import add_mapping
from uw_s3.sync.engine import SyncEngine
from uw_s3.sync.models import SyncMap


def _human_size(size: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:,.1f} {unit}" if unit != "B" else f"{size} B"
        size //= 1024
    return f"{size:,.1f} PB"


class FileManagerScreen(Screen):
    """Unified file manager: local files on the left, S3 objects on the right."""

    BINDINGS = [
        Binding("u", "upload", "Upload"),
        Binding("d", "download", "Download"),
        Binding("p", "preview_push", "Preview Push"),
        Binding("l", "preview_pull", "Preview Pull"),
        Binding("P", "push_all", "Push All", key_display="shift+p"),
        Binding("L", "pull_all", "Pull All", key_display="shift+l"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "new_bucket", "New Bucket"),
        Binding("escape", "pop_screen", "Back"),
    ]

    CSS = """
    #bucket-bar { height: auto; padding: 1 2; }
    #bucket-bar Horizontal { height: auto; align: left middle; }
    #bucket-bar Label { margin: 0 1 0 0; }
    #bucket-bar Select { width: 40; }
    #bucket-info { margin-left: 2; }
    #panes { height: 1fr; }
    #local-tree { width: 1fr; height: 1fr; margin: 0 1 0 0; border: round $accent; }
    #s3-pane { width: 1fr; height: 1fr; border: round $accent; }
    #s3-table { height: 1fr; }
    #action-bar { height: auto; padding: 0 2; }
    #action-bar Button { margin: 1 1 0 0; }
    #preview-bar { height: auto; padding: 0 2; }
    #preview-bar Button { margin: 0 1 0 0; }
    #log { height: 10; margin: 0 2; border: round $panel; }
    """

    selected_local_path: str = ""
    _selected_s3_key: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="bucket-bar"):
            with Horizontal():
                yield Label("[bold]Bucket:[/]")
                yield Select([], id="bucket-select", prompt="Loading buckets...")
                yield Label("", id="bucket-info")
        with Horizontal(id="panes"):
            tree = DirectoryTree(".", id="local-tree")
            tree.border_title = "Local Files"
            yield tree
            with Vertical(id="s3-pane") as pane:
                pane.border_title = "S3 Objects"
                yield DataTable(id="s3-table")
        with Horizontal(id="action-bar"):
            yield Button("Upload [u]", id="upload-btn")
            yield Button("Download [d]", id="download-btn")
            yield Button("Push All [P]", variant="primary", id="push-btn")
            yield Button("Pull All [L]", variant="success", id="pull-btn")
        with Horizontal(id="preview-bar"):
            yield Button("Preview Upload", id="preview-upload-btn")
            yield Button("Preview Download", id="preview-download-btn")
            yield Button("Preview Push [p]", id="preview-push-btn")
            yield Button("Preview Pull [l]", id="preview-pull-btn")
        log = Log(id="log", max_lines=100)
        log.border_title = "Output"
        yield log
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#s3-table", DataTable)
        table.cursor_type = "row"
        self._load_buckets()

    def on_screen_resume(self) -> None:
        self._load_buckets()

    # --- data loading ---

    @work(thread=True)
    def _load_buckets(self) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        try:
            buckets = app.s3.list_buckets()
            options: list[tuple[str, str]] = [(b, b) for b in buckets]
            sel = self.query_one("#bucket-select", Select)
            prev = self.app.call_from_thread(lambda: sel.value)
            self.app.call_from_thread(setattr, sel, "prompt", "Select a bucket")
            self.app.call_from_thread(sel.set_options, options)
            if prev is not Select.BLANK and str(prev) in buckets:
                self.app.call_from_thread(setattr, sel, "value", prev)
            info = self.query_one("#bucket-info", Label)
            self.app.call_from_thread(info.update, f"[dim]{len(buckets)} bucket(s)[/]")
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.app.call_from_thread(log.write_line, f"Error loading buckets: {exc}")

    @work(thread=True)
    def _load_objects(self, bucket: str) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        table = self.query_one("#s3-table", DataTable)
        try:
            objects = app.s3.list_objects_detail(bucket)
            self.app.call_from_thread(table.clear, columns=True)
            self.app.call_from_thread(table.add_column, "Object Key", key="key")
            self.app.call_from_thread(table.add_column, "Size", key="size")
            self.app.call_from_thread(table.add_column, "Last Modified", key="modified")
            for obj in objects:
                modified = (
                    obj.last_modified.strftime("%Y-%m-%d %H:%M")
                    if obj.last_modified
                    else "—"
                )
                self.app.call_from_thread(
                    table.add_row,
                    obj.name,
                    _human_size(obj.size),
                    modified,
                    key=obj.name,
                )
            info = self.query_one("#bucket-info", Label)
            self.app.call_from_thread(info.update, f"[dim]{len(objects)} object(s)[/]")
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.app.call_from_thread(log.write_line, f"Error loading objects: {exc}")

    # --- selection tracking ---

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.selected_local_path = str(event.path)

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.selected_local_path = str(event.path)

    @on(DataTable.RowHighlighted, "#s3-table")
    def handle_s3_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is not None:
            self._selected_s3_key = str(event.row_key.value)

    @on(Select.Changed, "#bucket-select")
    def handle_bucket_changed(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self._selected_s3_key = ""
            self._load_objects(str(event.value))

    # --- helpers ---

    def _current_bucket(self) -> str | None:
        val = self.query_one("#bucket-select", Select).value
        if val is Select.BLANK:
            return None
        return str(val)

    def _selected_local_dir(self) -> Path | None:
        if not self.selected_local_path:
            return None
        p = Path(self.selected_local_path)
        return p if p.is_dir() else p.parent

    def _log(self) -> Log:
        return self.query_one("#log", Log)

    # --- preview upload ---

    @on(Button.Pressed, "#preview-upload-btn")
    @work(thread=True, exclusive=True)
    def _do_preview_upload(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local = self.selected_local_path
        if not local or not Path(local).is_file():
            self.app.call_from_thread(log.write_line, "Select a local file to preview.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        local_path = Path(local)
        local_dir = self._selected_local_dir()
        if local_dir:
            try:
                obj_key = local_path.relative_to(local_dir).as_posix()
            except ValueError:
                obj_key = local_path.name
        else:
            obj_key = local_path.name

        local_size = local_path.stat().st_size
        self.app.call_from_thread(log.clear)
        self.app.call_from_thread(log.write_line, f"Preview upload: {obj_key}")
        try:
            if app.s3.exists(bucket, obj_key):
                stat = app.s3.stat_object(bucket, obj_key)
                remote_size = stat.size if hasattr(stat, "size") else 0
                self.app.call_from_thread(
                    log.write_line,
                    f"  OVERWRITE {obj_key} "
                    f"(local {_human_size(local_size)} → remote {_human_size(remote_size)})",
                )
            else:
                self.app.call_from_thread(
                    log.write_line,
                    f"  NEW {obj_key} ({_human_size(local_size)})",
                )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- preview download ---

    @on(Button.Pressed, "#preview-download-btn")
    @work(thread=True, exclusive=True)
    def _do_preview_download(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        if not self._selected_s3_key:
            self.app.call_from_thread(
                log.write_line, "Highlight an S3 object to preview."
            )
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        obj_key = self._selected_s3_key
        local_dir = self._selected_local_dir() or Path.cwd()
        filename = obj_key.rsplit("/", 1)[-1] if "/" in obj_key else obj_key
        dest = local_dir / filename

        self.app.call_from_thread(log.clear)
        self.app.call_from_thread(log.write_line, f"Preview download: {obj_key}")
        try:
            stat = app.s3.stat_object(bucket, obj_key)
            remote_size = stat.size if hasattr(stat, "size") else 0
            if dest.exists():
                local_size = dest.stat().st_size
                self.app.call_from_thread(
                    log.write_line,
                    f"  OVERWRITE {dest} "
                    f"(remote {_human_size(remote_size)} → local {_human_size(local_size)})",
                )
            else:
                self.app.call_from_thread(
                    log.write_line,
                    f"  NEW {dest} ({_human_size(remote_size)})",
                )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- preview push all ---

    def action_preview_push(self) -> None:
        self._do_preview_push()

    @on(Button.Pressed, "#preview-push-btn")
    def _on_preview_push_btn(self) -> None:
        self._do_preview_push()

    @work(thread=True, exclusive=True)
    def _do_preview_push(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local_dir = self.app.call_from_thread(self._selected_local_dir)
        if not local_dir:
            self.app.call_from_thread(log.write_line, "Select a local directory first.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        mapping = SyncMap(
            local_dir=str(local_dir), bucket=bucket, endpoint=app.s3.endpoint
        )
        engine = SyncEngine(app.s3, mapping)
        try:
            actions = engine.status_push()
            self.app.call_from_thread(log.clear)
            if not actions:
                self.app.call_from_thread(
                    log.write_line, "Nothing to push — all in sync."
                )
            else:
                self.app.call_from_thread(
                    log.write_line, f"{len(actions)} file(s) would be pushed:"
                )
                for a in actions:
                    self.app.call_from_thread(
                        log.write_line, f"  ▲ {a.relative_path}  ({a.reason})"
                    )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- preview pull all ---

    def action_preview_pull(self) -> None:
        self._do_preview_pull()

    @on(Button.Pressed, "#preview-pull-btn")
    def _on_preview_pull_btn(self) -> None:
        self._do_preview_pull()

    @work(thread=True, exclusive=True)
    def _do_preview_pull(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local_dir = self.app.call_from_thread(self._selected_local_dir)
        if not local_dir:
            self.app.call_from_thread(log.write_line, "Select a local directory first.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        mapping = SyncMap(
            local_dir=str(local_dir), bucket=bucket, endpoint=app.s3.endpoint
        )
        engine = SyncEngine(app.s3, mapping)
        try:
            actions = engine.status_pull()
            self.app.call_from_thread(log.clear)
            if not actions:
                self.app.call_from_thread(
                    log.write_line, "Nothing to pull — all in sync."
                )
            else:
                self.app.call_from_thread(
                    log.write_line, f"{len(actions)} file(s) would be pulled:"
                )
                for a in actions:
                    self.app.call_from_thread(
                        log.write_line, f"  ▼ {a.relative_path}  ({a.reason})"
                    )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- single upload ---

    def action_upload(self) -> None:
        self._do_upload()

    @on(Button.Pressed, "#upload-btn")
    def _on_upload_btn(self) -> None:
        self._do_upload()

    @work(thread=True, exclusive=True)
    def _do_upload(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local = self.selected_local_path
        if not local or not Path(local).is_file():
            self.app.call_from_thread(log.write_line, "Select a local file to upload.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        local_path = Path(local)
        local_dir = self._selected_local_dir()
        if local_dir:
            try:
                obj_key = local_path.relative_to(local_dir).as_posix()
            except ValueError:
                obj_key = local_path.name
        else:
            obj_key = local_path.name

        self.app.call_from_thread(log.write_line, f"Uploading {obj_key}...")
        try:
            app.s3.upload_file(bucket, obj_key, local_path)
            self.app.call_from_thread(log.write_line, f"Uploaded {obj_key}")
            self._load_objects(bucket)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- single download ---

    def action_download(self) -> None:
        self._do_download()

    @on(Button.Pressed, "#download-btn")
    def _on_download_btn(self) -> None:
        self._do_download()

    @work(thread=True, exclusive=True)
    def _do_download(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        if not self._selected_s3_key:
            self.app.call_from_thread(
                log.write_line, "Highlight an S3 object to download."
            )
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        obj_key = self._selected_s3_key
        local_dir = self._selected_local_dir() or Path.cwd()

        filename = obj_key.rsplit("/", 1)[-1] if "/" in obj_key else obj_key
        dest = local_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        self.app.call_from_thread(log.write_line, f"Downloading {obj_key}...")
        try:
            app.s3.download_file(bucket, obj_key, dest)
            self.app.call_from_thread(log.write_line, f"Saved to {dest}")
            self.app.call_from_thread(
                self.query_one("#local-tree", DirectoryTree).reload
            )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- Push All ---

    def action_push_all(self) -> None:
        self._do_push_all()

    @on(Button.Pressed, "#push-btn")
    def _on_push_btn(self) -> None:
        self._do_push_all()

    @work(thread=True, exclusive=True)
    def _do_push_all(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local_dir = self.app.call_from_thread(self._selected_local_dir)
        if not local_dir:
            self.app.call_from_thread(log.write_line, "Select a local directory first.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        mapping = SyncMap(
            local_dir=str(local_dir), bucket=bucket, endpoint=app.s3.endpoint
        )
        engine = SyncEngine(app.s3, mapping)
        self.app.call_from_thread(log.write_line, "Pushing...")
        try:
            actions = engine.push(
                callback=lambda a: self.app.call_from_thread(
                    log.write_line, f"  ▲ {a.relative_path}"
                )
            )
            self.app.call_from_thread(
                log.write_line, f"Done — {len(actions)} file(s) pushed."
            )
            add_mapping(mapping)
            self._load_objects(bucket)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- Pull All ---

    def action_pull_all(self) -> None:
        self._do_pull_all()

    @on(Button.Pressed, "#pull-btn")
    def _on_pull_btn(self) -> None:
        self._do_pull_all()

    @work(thread=True, exclusive=True)
    def _do_pull_all(self) -> None:
        log = self._log()
        bucket = self.app.call_from_thread(self._current_bucket)
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select a bucket first.")
            return
        local_dir = self.app.call_from_thread(self._selected_local_dir)
        if not local_dir:
            self.app.call_from_thread(log.write_line, "Select a local directory first.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        mapping = SyncMap(
            local_dir=str(local_dir), bucket=bucket, endpoint=app.s3.endpoint
        )
        engine = SyncEngine(app.s3, mapping)
        self.app.call_from_thread(log.write_line, "Pulling...")
        try:
            actions = engine.pull(
                callback=lambda a: self.app.call_from_thread(
                    log.write_line, f"  ▼ {a.relative_path}"
                )
            )
            self.app.call_from_thread(
                log.write_line, f"Done — {len(actions)} file(s) pulled."
            )
            add_mapping(mapping)
            self.app.call_from_thread(
                self.query_one("#local-tree", DirectoryTree).reload
            )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    # --- refresh / new bucket / back ---

    def action_refresh(self) -> None:
        bucket = self._current_bucket()
        self._load_buckets()
        if bucket:
            self._load_objects(bucket)

    def action_new_bucket(self) -> None:
        from uw_s3.tui.screens.create_bucket import CreateBucketScreen

        self.app.push_screen(CreateBucketScreen())

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

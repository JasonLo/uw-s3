"""File Manager screen — local files + S3 objects in a unified view."""

from pathlib import Path
from typing import Literal

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Log,
    Select,
)

from uw_s3.sync.config import add_mapping
from uw_s3.sync.engine import SyncEngine
from uw_s3.sync.models import SyncMap
from uw_s3.tui.screens.base import EndpointBar, S3Screen


def _human_size(size: int) -> str:
    """Format bytes into a human-readable string."""
    fsize: float = size
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(fsize) < 1024:
            return f"{fsize:,.1f} {unit}" if unit != "B" else f"{size} B"
        fsize /= 1024
    return f"{fsize:,.1f} PB"


class FileManagerScreen(S3Screen):
    """Unified file manager: local files on the left, S3 objects on the right."""

    BINDINGS = [
        Binding("u", "upload", "Upload"),
        Binding("d", "download", "Download"),
        Binding("p", "preview_push", "Preview Push"),
        Binding("l", "preview_pull", "Preview Pull"),
        Binding("P", "push_all", "Push All", key_display="shift+p"),
        Binding("L", "pull_all", "Pull All", key_display="shift+l"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
    ]

    CSS = """
    #bucket-bar { height: auto; margin: 0 2; align: left middle; }
    #bucket-bar Select { width: 40; border: round $accent; border-title-align: left; padding: 0 1; }

    #panes { height: 1fr; margin: 1 2 0 2; }
    #local-tree { width: 1fr; height: 1fr; margin-right: 1; border: round $accent; }
    #s3-pane { width: 1fr; height: 1fr; border: round $accent; }
    #s3-table { height: 1fr; }
    #action-bar { height: auto; margin: 0 2; }
    #action-bar Button { margin-right: 1; }
    .action-group { width: 1fr; height: auto; }
    .action-group-right { margin-left: 1; }
    #log { height: 10; margin: 0 2 1 2; border: round $panel; }
    """

    selected_local_path: str = ""
    _selected_s3_key: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield EndpointBar()
        with Horizontal(id="bucket-bar"):
            sel = Select(
                [], id="bucket-select", prompt="Loading buckets...", compact=True
            )
            sel.border_title = "Bucket"
            yield sel
        with Horizontal(id="panes"):
            tree = DirectoryTree(".", id="local-tree")
            tree.border_title = "Local Files"
            yield tree
            with Vertical(id="s3-pane") as pane:
                pane.border_title = "S3 Objects"
                yield DataTable(id="s3-table")
        with Horizontal(id="action-bar"):
            with Horizontal(classes="action-group"):
                yield Button("Upload [u]", id="upload-btn")
                yield Button("Preview Push [p]", id="preview-push-btn")
                yield Button("Push All [P]", variant="primary", id="push-btn")
            with Horizontal(classes="action-group action-group-right"):
                yield Button("Download [d]", id="download-btn")
                yield Button("Preview Pull [l]", id="preview-pull-btn")
                yield Button("Pull All [L]", variant="success", id="pull-btn")
        log = Log(id="log", max_lines=100)
        log.border_title = "Output"
        yield log
        yield Footer()

    def on_mount(self) -> None:
        self._update_endpoint_bar()
        table = self.query_one("#s3-table", DataTable)
        table.cursor_type = "row"
        self._load_buckets()

    def on_screen_resume(self) -> None:
        self._update_endpoint_bar()
        self._load_buckets()

    def on_endpoint_switched(self) -> None:
        self._load_buckets()

    # --- data loading ---

    @work(thread=True)
    def _load_buckets(self) -> None:
        try:
            buckets = self.s3_app.s3.list_buckets()
            options: list[tuple[str, str]] = [(b, b) for b in buckets]
            sel = self.query_one("#bucket-select", Select)
            prev = self.ui(lambda: sel.value)
            self.ui(setattr, sel, "prompt", "Select a bucket")
            self.ui(sel.set_options, options)
            if prev is not Select.NULL and str(prev) in buckets:
                self.ui(setattr, sel, "value", prev)
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.ui(log.write_line, f"Error loading buckets: {exc}")

    @work(thread=True)
    def _load_objects(self, bucket: str) -> None:
        try:
            objects = self.s3_app.s3.list_objects_detail(bucket)
            rows: list[tuple[str, str, str]] = []
            for obj in objects:
                modified = (
                    obj.last_modified.strftime("%Y-%m-%d %H:%M")
                    if obj.last_modified
                    else "—"
                )
                rows.append((obj.name, _human_size(obj.size), modified))

            def _rebuild_table() -> None:
                table = self.query_one("#s3-table", DataTable)
                table.clear(columns=True)
                table.add_column("Object Key", key="key")
                table.add_column("Size", key="size")
                table.add_column("Last Modified", key="modified")
                for name, size, mod in rows:
                    table.add_row(name, size, mod, key=name)

            self.ui(_rebuild_table)
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.ui(log.write_line, f"Error loading objects: {exc}")

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
        if event.value is not Select.NULL:
            self._selected_s3_key = ""
            self._load_objects(str(event.value))

    # --- helpers ---

    def _current_bucket(self) -> str | None:
        val = self.query_one("#bucket-select", Select).value
        if val is Select.NULL:
            return None
        return str(val)

    def _selected_local_dir(self) -> Path | None:
        if not self.selected_local_path:
            return None
        p = Path(self.selected_local_path)
        return p if p.is_dir() else p.parent

    def _log(self) -> Log:
        return self.query_one("#log", Log)

    # --- sync helpers ---

    def _make_engine(self) -> tuple[SyncEngine, Log] | None:
        """Validate bucket + local dir and return (engine, log) or None."""
        log = self._log()
        bucket = self.ui(self._current_bucket)
        if not bucket:
            self.ui(log.write_line, "Select a bucket first.")
            return None
        local_dir = self.ui(self._selected_local_dir)
        if not local_dir:
            self.ui(log.write_line, "Select a local directory first.")
            return None
        mapping = SyncMap(
            local_dir=str(local_dir), bucket=bucket, endpoint=self.s3_app.s3.endpoint
        )
        return SyncEngine(self.s3_app.s3, mapping), log

    def _run_preview(self, direction: Literal["push", "pull"]) -> None:
        result = self._make_engine()
        if not result:
            return
        engine, log = result
        arrow = "▲" if direction == "push" else "▼"
        status_fn = engine.status_push if direction == "push" else engine.status_pull
        try:
            actions = status_fn()
            self.ui(log.clear)
            if not actions:
                self.ui(log.write_line, f"Nothing to {direction} — all in sync.")
            else:
                self.ui(
                    log.write_line, f"{len(actions)} file(s) would be {direction}ed:"
                )
                for a in actions:
                    self.ui(
                        log.write_line, f"  {arrow} {a.relative_path}  ({a.reason})"
                    )
        except Exception as exc:
            self.ui(log.write_line, f"Error: {exc}")

    def _run_sync(self, direction: Literal["push", "pull"]) -> None:
        result = self._make_engine()
        if not result:
            return
        engine, log = result
        arrow = "▲" if direction == "push" else "▼"
        sync_fn = engine.push if direction == "push" else engine.pull
        self.ui(log.write_line, f"{direction.capitalize()}ing...")
        try:
            actions = sync_fn(
                callback=lambda a: self.ui(
                    log.write_line, f"  {arrow} {a.relative_path}"
                )
            )
            self.ui(log.write_line, f"Done — {len(actions)} file(s) {direction}ed.")
            add_mapping(engine.mapping)
            if direction == "push":
                self._load_objects(engine.mapping.bucket)
            else:
                self.ui(self.query_one("#local-tree", DirectoryTree).reload)
        except Exception as exc:
            self.ui(log.write_line, f"Error: {exc}")

    # --- preview ---

    @on(Button.Pressed, "#preview-push-btn")
    @work(thread=True, exclusive=True)
    def action_preview_push(self) -> None:
        self._run_preview("push")

    @on(Button.Pressed, "#preview-pull-btn")
    @work(thread=True, exclusive=True)
    def action_preview_pull(self) -> None:
        self._run_preview("pull")

    # --- upload ---

    @on(Button.Pressed, "#upload-btn")
    @work(thread=True, exclusive=True)
    def action_upload(self) -> None:
        log = self._log()
        bucket = self.ui(self._current_bucket)
        if not bucket:
            self.ui(log.write_line, "Select a bucket first.")
            return
        local = self.selected_local_path
        if not local or not Path(local).is_file():
            self.ui(log.write_line, "Select a local file to upload.")
            return

        local_path = Path(local)
        local_dir = self._selected_local_dir()
        if local_dir:
            try:
                obj_key = local_path.relative_to(local_dir).as_posix()
            except ValueError:
                obj_key = local_path.name
        else:
            obj_key = local_path.name

        self.ui(log.write_line, f"Uploading {obj_key}...")
        try:
            self.s3_app.s3.upload_file(bucket, obj_key, local_path)
            self.ui(log.write_line, f"Uploaded {obj_key}")
            self._load_objects(bucket)
        except Exception as exc:
            self.ui(log.write_line, f"Error: {exc}")

    # --- download ---

    @on(Button.Pressed, "#download-btn")
    @work(thread=True, exclusive=True)
    def action_download(self) -> None:
        log = self._log()
        bucket = self.ui(self._current_bucket)
        if not bucket:
            self.ui(log.write_line, "Select a bucket first.")
            return
        if not self._selected_s3_key:
            self.ui(log.write_line, "Highlight an S3 object to download.")
            return

        obj_key = self._selected_s3_key
        local_dir = self._selected_local_dir() or Path.cwd()

        filename = obj_key.rsplit("/", 1)[-1] if "/" in obj_key else obj_key
        dest = local_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        self.ui(log.write_line, f"Downloading {obj_key}...")
        try:
            self.s3_app.s3.download_file(bucket, obj_key, dest)
            self.ui(log.write_line, f"Saved to {dest}")
            self.ui(self.query_one("#local-tree", DirectoryTree).reload)
        except Exception as exc:
            self.ui(log.write_line, f"Error: {exc}")

    # --- push / pull all ---

    @on(Button.Pressed, "#push-btn")
    @work(thread=True, exclusive=True)
    def action_push_all(self) -> None:
        self._run_sync("push")

    @on(Button.Pressed, "#pull-btn")
    @work(thread=True, exclusive=True)
    def action_pull_all(self) -> None:
        self._run_sync("pull")

    # --- refresh / back ---

    def action_refresh(self) -> None:
        self._load_buckets()

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

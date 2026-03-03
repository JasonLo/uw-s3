"""Mount screen — mount an S3 bucket as a local folder via rclone."""

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
    Input,
    Label,
    Log,
)

from rich.text import Text

from uw_s3.rclone import RcloneMount, find_rclone
from uw_s3.validators import BUCKET_NAME_RE

_DEFAULT_MOUNT_ROOT = Path("./s3")


class MountScreen(Screen):
    """Mount an S3 bucket as a local directory using rclone."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    CSS = """
    #active-mounts-panel { height: auto; max-height: 12; margin: 0 2; border: round $accent; padding: 1; }
    #active-mounts { height: auto; max-height: 8; }
    #unmount-row { height: auto; margin-top: 1; }
    #unmount-row Button { margin-right: 1; }
    #layout { height: 1fr; }
    #tree { width: 1fr; height: 1fr; margin-right: 1; border: solid $accent; }
    #buckets { width: 1fr; height: 1fr; margin-right: 1; padding: 1 2; border: solid $accent; }
    #controls { width: 1fr; height: 1fr; padding: 1 2; border: solid $accent; }
    #bucket-table { height: 1fr; }
    #create-row { height: auto; margin-top: 1; }
    #new-bucket-name { width: 1fr; }
    #create-bucket-btn { margin-left: 1; }
    .btn-row { height: auto; }
    .btn-row Button { margin: 1 1 0 0; }
    #log { height: 1fr; margin-top: 1; border: solid $panel; }
    """

    _selected_bucket: str = ""
    _selected_path: str = ""
    _selected_active_mount: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="active-mounts-panel") as amp:
            amp.border_title = "Active Mounts"
            yield DataTable(id="active-mounts")
            with Horizontal(id="unmount-row"):
                yield Button(
                    "Unmount Selected",
                    variant="error",
                    id="unmount-active-btn",
                    disabled=True,
                )
        with Horizontal(id="layout"):
            tree = DirectoryTree(str(_DEFAULT_MOUNT_ROOT), id="tree")
            tree.border_title = "Mount Point"
            yield tree

            with Vertical(id="buckets") as bp:
                bp.border_title = "Buckets"
                yield DataTable(id="bucket-table")
                with Horizontal(id="create-row"):
                    yield Input(placeholder="new-bucket-name", id="new-bucket-name")
                    yield Button("Create", variant="success", id="create-bucket-btn")

            with Vertical(id="controls") as cp:
                cp.border_title = "Mount"
                yield Label("Bucket: [dim](none)[/]", id="selected-bucket")
                yield Label(
                    f"Folder: [dim]{_DEFAULT_MOUNT_ROOT.resolve()}[/]",
                    id="selected-dir",
                )
                yield Input(
                    value=str(_DEFAULT_MOUNT_ROOT),
                    placeholder="./s3",
                    id="mount-path",
                )
                yield Label("[dim]Not mounted[/]", id="mount-status")
                with Horizontal(classes="btn-row"):
                    yield Button("Mount", variant="primary", id="mount-btn")
                    yield Button(
                        "Unmount", variant="error", id="unmount-btn", disabled=True
                    )
                log = Log(id="log")
                log.border_title = "Output"
                yield log
        yield Footer()

    def on_mount(self) -> None:
        _DEFAULT_MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
        table = self.query_one("#bucket-table", DataTable)
        table.add_column("Bucket Name", key="name")
        table.cursor_type = "row"
        am_table = self.query_one("#active-mounts", DataTable)
        am_table.add_column("Bucket", key="bucket")
        am_table.add_column("Mount Point", key="path")
        am_table.add_column("Status", key="status")
        am_table.cursor_type = "row"
        self._selected_path = str(_DEFAULT_MOUNT_ROOT.resolve())
        self._load_buckets()
        self._refresh_active_mounts()
        if find_rclone() is None:
            log = self.query_one("#log", Log)
            log.write_line(
                "rclone is not installed. Install it from https://rclone.org/install/"
            )
            self.query_one("#mount-status", Label).update(
                "[bold red]rclone not found[/]"
            )
            self.query_one("#mount-btn", Button).disabled = True

    @work(thread=True)
    def _load_buckets(self) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        table = self.query_one("#bucket-table", DataTable)
        try:
            buckets = app.s3.list_buckets()
            self.app.call_from_thread(table.clear)
            for b in buckets:
                self.app.call_from_thread(table.add_row, b, key=b)
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.app.call_from_thread(log.write_line, f"Error loading buckets: {exc}")

    def _refresh_active_mounts(self) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        table = self.query_one("#active-mounts", DataTable)
        table.clear()
        self._selected_active_mount = ""
        self.query_one("#unmount-active-btn", Button).disabled = True
        for bucket, rm in app.active_mounts.items():
            status = (
                Text("mounted", style="green")
                if rm.is_mounted
                else Text("stopped", style="red")
            )
            table.add_row(bucket, str(rm.mount_point), status, key=bucket)

    @on(DataTable.RowHighlighted, "#active-mounts")
    def _on_active_mount_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is not None:
            self._selected_active_mount = str(event.row_key.value)
            self.query_one("#unmount-active-btn", Button).disabled = False

    @on(Button.Pressed, "#unmount-active-btn")
    @work(thread=True, exclusive=True)
    def handle_unmount_active(self) -> None:
        log = self.query_one("#log", Log)
        bucket = self._selected_active_mount
        if not bucket:
            self.app.call_from_thread(log.write_line, "Select an active mount first.")
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        rm = app.active_mounts.get(bucket)
        if rm is None:
            self.app.call_from_thread(log.write_line, f"{bucket} is not mounted.")
            return

        self.app.call_from_thread(log.write_line, f"Unmounting {bucket}...")
        try:
            rm.unmount()
            del app.active_mounts[bucket]
            self.app.call_from_thread(log.write_line, f"Unmounted {bucket}.")
            self.app.call_from_thread(self._refresh_active_mounts)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Unmount failed: {exc}")

    @on(DataTable.RowSelected, "#bucket-table")
    def _on_bucket_selected(self, event: DataTable.RowSelected) -> None:
        bucket = str(event.row_key.value)
        self._selected_bucket = bucket
        self.query_one("#selected-bucket", Label).update(f"Bucket: [bold]{bucket}[/]")

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._selected_path = str(event.path)
        self.query_one("#selected-dir", Label).update(
            f"Folder: [bold]{self._selected_path}[/]"
        )
        self.query_one("#mount-path", Input).value = self._selected_path

    @on(Input.Changed, "#mount-path")
    def _on_path_input_changed(self, event: Input.Changed) -> None:
        self._selected_path = event.value
        self.query_one("#selected-dir", Label).update(f"Folder: [bold]{event.value}[/]")

    @on(Button.Pressed, "#create-bucket-btn")
    @work(thread=True)
    def handle_create_bucket(self) -> None:
        name = self.app.call_from_thread(
            lambda: self.query_one("#new-bucket-name", Input).value.strip()
        )
        log = self.query_one("#log", Log)

        if not name:
            self.app.call_from_thread(log.write_line, "Bucket name is required.")
            return
        if not BUCKET_NAME_RE.match(name):
            self.app.call_from_thread(
                log.write_line,
                "Invalid name: 3-63 chars, lowercase letters/digits/hyphens/dots.",
            )
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        try:
            if app.s3.bucket_exists(name):
                self.app.call_from_thread(
                    log.write_line, f"Bucket '{name}' already exists."
                )
                return
            app.s3.create_bucket(name)
            self.app.call_from_thread(log.write_line, f"Bucket '{name}' created.")
            self.app.call_from_thread(
                setattr, self.query_one("#new-bucket-name", Input), "value", ""
            )
            self._load_buckets()
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error creating bucket: {exc}")

    @on(Button.Pressed, "#mount-btn")
    @work(thread=True, exclusive=True)
    def handle_mount(self) -> None:
        mount_path = self.app.call_from_thread(
            lambda: self.query_one("#mount-path", Input).value
        )
        log = self.query_one("#log", Log)

        if not self._selected_bucket:
            self.app.call_from_thread(log.write_line, "Please select a bucket first.")
            return
        if not mount_path:
            self.app.call_from_thread(log.write_line, "Please enter a mount point.")
            return

        bucket = self._selected_bucket
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)

        if bucket in app.active_mounts and app.active_mounts[bucket].is_mounted:
            self.app.call_from_thread(log.write_line, f"{bucket} is already mounted.")
            return

        resolved = Path(mount_path).expanduser().resolve()
        self.app.call_from_thread(log.write_line, f"Mounting {bucket} at {resolved}...")

        try:
            rm = RcloneMount(
                access_key=app.access_key,
                secret_key=app.secret_key,
                endpoint=app.s3.endpoint,
                bucket=bucket,
                mount_point=mount_path,
            )
            rm.mount()
            app.active_mounts[bucket] = rm
            self.app.call_from_thread(log.write_line, f"Mounted {bucket} at {resolved}")
            self.app.call_from_thread(self._update_ui_mounted, True)
            self.app.call_from_thread(self._refresh_active_mounts)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Mount failed: {exc}")

    @on(Button.Pressed, "#unmount-btn")
    @work(thread=True, exclusive=True)
    def handle_unmount(self) -> None:
        log = self.query_one("#log", Log)

        if not self._selected_bucket:
            self.app.call_from_thread(log.write_line, "No bucket selected.")
            return

        bucket = self._selected_bucket
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)

        rm = app.active_mounts.get(bucket)
        if rm is None or not rm.is_mounted:
            self.app.call_from_thread(log.write_line, f"{bucket} is not mounted.")
            return

        self.app.call_from_thread(log.write_line, f"Unmounting {bucket}...")
        try:
            rm.unmount()
            del app.active_mounts[bucket]
            self.app.call_from_thread(log.write_line, f"Unmounted {bucket}.")
            self.app.call_from_thread(self._update_ui_mounted, False)
            self.app.call_from_thread(self._refresh_active_mounts)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Unmount failed: {exc}")

    def _update_ui_mounted(self, mounted: bool) -> None:
        status = self.query_one("#mount-status", Label)
        mount_btn = self.query_one("#mount-btn", Button)
        unmount_btn = self.query_one("#unmount-btn", Button)
        if mounted:
            status.update("[bold green]Mounted[/]")
            mount_btn.disabled = True
            unmount_btn.disabled = False
        else:
            status.update("[dim]Not mounted[/]")
            mount_btn.disabled = False
            unmount_btn.disabled = True

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

"""Mount screen — mount an S3 bucket as a local folder via FUSE (Python s3fs)."""

from pathlib import Path

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
    Input,
    Label,
    Log,
)

from rich.text import Text

from uw_s3 import mounts_config
from uw_s3.client import CAMPUS_ENDPOINT
from uw_s3.mount_backend import Mount, WorkerMount, find_backend
from uw_s3.tui.screens.base import NetworkBar, S3Screen

_DEFAULT_MOUNT_ROOT = Path("./s3")


def _domain_name(endpoint: str) -> str:
    """Short domain label for the bucket list."""
    return "campus" if endpoint == CAMPUS_ENDPOINT else "web"


def _ensure_mount_root() -> Path:
    """Create _DEFAULT_MOUNT_ROOT if possible and return its resolved path."""
    try:
        _DEFAULT_MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
        list(_DEFAULT_MOUNT_ROOT.iterdir())
        return _DEFAULT_MOUNT_ROOT.resolve()
    except OSError:
        return Path.cwd().resolve()


class MountScreen(S3Screen):
    """Mount an S3 bucket as a local directory using Python s3fs over FUSE."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
    ]

    CSS = """
    #active-mounts-panel { height: auto; max-height: 12; margin: 1 2 0 2; background: $boost; border: round $accent; padding: 1; }
    #active-mounts { height: auto; max-height: 8; }
    #unmount-row { height: auto; margin-top: 1; }
    #unmount-row Button { margin-right: 1; }
    #layout { height: 1fr; margin: 1 2 0 2; }
    #tree { width: 1fr; height: 1fr; margin-right: 1; border: round $accent; }
    #buckets { width: 1fr; height: 1fr; margin-right: 1; padding: 1 2; border: round $accent; }
    #controls { width: 1fr; height: 1fr; padding: 1 2; border: round $accent; }
    #bucket-table { height: 1fr; }
    .btn-row { height: auto; margin-top: 1; }
    .btn-row Button { margin-right: 1; }
    #log { height: 1fr; margin-top: 1; border: round $panel; }
    """

    _selected_bucket: str = ""
    _selected_path: str = ""
    _selected_active_mount: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield NetworkBar()
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
            tree = DirectoryTree(".", id="tree")
            tree.border_title = "Mount Point"
            yield tree

            with Vertical(id="buckets") as bp:
                bp.border_title = "Buckets"
                yield DataTable(id="bucket-table")

            with Vertical(id="controls") as cp:
                cp.border_title = "Mount"
                yield Label("Bucket: [dim](none)[/]", id="selected-bucket")
                yield Label("Folder: [dim](select below)[/]", id="selected-dir")
                yield Input(value="", placeholder="./s3", id="mount-path")
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
        self._update_network_bar()
        default = _ensure_mount_root()
        self._selected_path = str(default)
        self.query_one("#mount-path", Input).value = str(default)
        self.query_one("#selected-dir", Label).update(f"Folder: [bold]{default}[/]")
        table = self.query_one("#bucket-table", DataTable)
        table.add_column("Bucket Name", key="name")
        table.add_column("Domain", key="domain")
        table.cursor_type = "row"
        am_table = self.query_one("#active-mounts", DataTable)
        am_table.add_column("Bucket", key="bucket")
        am_table.add_column("Mount Point", key="path")
        am_table.add_column("Status", key="status")
        am_table.cursor_type = "row"
        self._load_buckets()
        self._refresh_active_mounts()
        if find_backend() is None:
            log = self.query_one("#log", Log)
            log.write_line("Python s3fs is not installed. Run `uv sync` to install it.")
            self.query_one("#mount-status", Label).update(
                "[bold red]mount backend not available[/]"
            )
            self.query_one("#mount-btn", Button).disabled = True

    def reload_buckets(self) -> None:
        self._load_buckets()

    @work(thread=True, exclusive=True, group="load")
    def _load_buckets(self) -> None:
        table = self.query_one("#bucket-table", DataTable)
        try:
            entries = self.s3_app.s3.entries()
            self.ui(table.clear)
            for e in entries:
                if e.reachable:
                    name_cell: Text = Text(e.name)
                    domain_cell = Text(_domain_name(e.endpoint))
                else:
                    name_cell = Text(e.name, style="dim")
                    domain_cell = Text(
                        f"{_domain_name(e.endpoint)} 🔒 VPN", style="dim"
                    )
                self.ui(table.add_row, name_cell, domain_cell, key=e.name)
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.ui(log.write_line, f"Error loading buckets: {exc}")

    def _refresh_active_mounts(self) -> None:
        table = self.query_one("#active-mounts", DataTable)
        table.clear()
        self._selected_active_mount = ""
        self.query_one("#unmount-active-btn", Button).disabled = True
        for bucket, rm in self.s3_app.active_mounts.items():
            if not rm.is_mounted:
                status = Text("stopped", style="red")
            elif isinstance(rm, WorkerMount):
                status = Text("detached", style="cyan")
            else:
                status = Text("mounted", style="green")
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
            self.ui(log.write_line, "Select an active mount first.")
            return

        rm = self.s3_app.active_mounts.get(bucket)
        if rm is None:
            self.ui(log.write_line, f"{bucket} is not mounted.")
            return

        self.ui(log.write_line, f"Unmounting {bucket}...")
        try:
            rm.unmount()
            if isinstance(rm, WorkerMount):
                mounts_config.remove(bucket, str(rm.mount_point))
            del self.s3_app.active_mounts[bucket]
            self.ui(log.write_line, f"Unmounted {bucket}.")
            self.ui(self._refresh_active_mounts)
            self.ui(self.query_one("#tree", DirectoryTree).reload)
        except Exception as exc:
            self.ui(log.write_line, f"Unmount failed: {exc}")

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

    @on(Button.Pressed, "#mount-btn")
    @work(thread=True, exclusive=True)
    def handle_mount(self) -> None:
        mount_path = self.ui(lambda: self.query_one("#mount-path", Input).value)
        log = self.query_one("#log", Log)

        if not self._selected_bucket:
            self.ui(log.write_line, "Please select a bucket first.")
            return
        if not mount_path:
            self.ui(log.write_line, "Please enter a mount point.")
            return

        bucket = self._selected_bucket

        if (
            bucket in self.s3_app.active_mounts
            and self.s3_app.active_mounts[bucket].is_mounted
        ):
            self.ui(log.write_line, f"{bucket} is already mounted.")
            return

        endpoint = self.s3_app.s3.endpoint_for(bucket)
        if endpoint is None or not self.s3_app.s3.is_reachable(bucket):
            self.ui(
                log.write_line,
                f"Cannot mount {bucket}: its endpoint is unreachable "
                "— connect to the UW network or VPN and Refresh.",
            )
            return

        resolved = Path(mount_path).expanduser().resolve()
        self.ui(log.write_line, f"Mounting {bucket} at {resolved}...")

        try:
            rm = Mount(
                access_key=self.s3_app.access_key,
                secret_key=self.s3_app.secret_key,
                endpoint=endpoint,
                bucket=bucket,
                mount_point=mount_path,
            )
            rm.mount()
            self.s3_app.active_mounts[bucket] = rm
            if rm.cleared_stale:
                self.ui(
                    log.write_line,
                    f"Cleared stale mount at {resolved} from a prior session.",
                )
            self.ui(log.write_line, f"Mounted {bucket} at {resolved}")
            try:
                sample = sorted(p.name for p in resolved.iterdir())[:5]
                preview = ", ".join(sample) if sample else "(empty)"
                self.ui(log.write_line, f"Contents: {preview}")
            except OSError as exc:
                self.ui(log.write_line, f"Could not list mount point: {exc}")
            self.ui(self._update_ui_mounted, True)
            self.ui(self._refresh_active_mounts)
            self.ui(self.query_one("#tree", DirectoryTree).reload)
        except Exception as exc:
            self.ui(log.write_line, f"Mount failed: {exc}")

    @on(Button.Pressed, "#unmount-btn")
    @work(thread=True, exclusive=True)
    def handle_unmount(self) -> None:
        log = self.query_one("#log", Log)

        if not self._selected_bucket:
            self.ui(log.write_line, "No bucket selected.")
            return

        bucket = self._selected_bucket

        rm = self.s3_app.active_mounts.get(bucket)
        if rm is None or not rm.is_mounted:
            self.ui(log.write_line, f"{bucket} is not mounted.")
            return

        self.ui(log.write_line, f"Unmounting {bucket}...")
        try:
            rm.unmount()
            if isinstance(rm, WorkerMount):
                mounts_config.remove(bucket, str(rm.mount_point))
            del self.s3_app.active_mounts[bucket]
            self.ui(log.write_line, f"Unmounted {bucket}.")
            self.ui(self._update_ui_mounted, False)
            self.ui(self._refresh_active_mounts)
            self.ui(self.query_one("#tree", DirectoryTree).reload)
        except Exception as exc:
            self.ui(log.write_line, f"Unmount failed: {exc}")

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

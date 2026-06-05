"""Bucket management screen — list, create, delete, set permissions."""

from typing import TYPE_CHECKING

from rich.text import Text

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

from minio.error import S3Error

from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT
from uw_s3.s3_router import EndpointUnreachable
from uw_s3.validators import BUCKET_NAME_RE
from uw_s3.tui.screens.base import NetworkBar, S3Screen
from uw_s3.tui.screens.confirm import ConfirmScreen

if TYPE_CHECKING:
    from textual.widgets._data_table import RowKey

PERMISSION_OPTIONS: list[tuple[str, str]] = [
    ("Private (default)", "private"),
    ("Public Read", "public-read"),
    ("Public Read/Write (not recommended)", "public-readwrite"),
]

_DOMAIN_LABELS: dict[str, str] = {
    CAMPUS_ENDPOINT: "Campus (UW network / VPN only)",
    WEB_ENDPOINT: "Web (public internet)",
}


def _domain_name(endpoint: str) -> str:
    """Short domain label for the bucket list."""
    return "campus" if endpoint == CAMPUS_ENDPOINT else "web"


class CreateBucketScreen(ModalScreen[tuple[str, str, str] | None]):
    """Modal dialog for creating a new bucket on a chosen endpoint."""

    CSS = """
    CreateBucketScreen { align: center middle; }
    #create-dialog {
        width: 64;
        height: auto;
        padding: 2 4;
        border: round $accent;
        background: $boost;
    }
    #create-title { margin-bottom: 1; text-style: bold; }
    #create-dialog Label { margin-top: 1; }
    #create-dialog Input { margin-top: 0; }
    #create-dialog Select { margin-top: 0; }
    #create-buttons { height: auto; align: center middle; margin-top: 1; }
    #create-buttons Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, reachable: set[str]) -> None:
        super().__init__()
        # Only endpoints we can reach can host a new bucket. Prefer web as the
        # default (it works from anywhere); fall back to campus.
        ordered = [e for e in (WEB_ENDPOINT, CAMPUS_ENDPOINT) if e in reachable]
        self._domain_options = [(_DOMAIN_LABELS[e], e) for e in ordered]
        self._default_domain = ordered[0] if ordered else WEB_ENDPOINT

    def compose(self) -> ComposeResult:
        with Vertical(id="create-dialog"):
            yield Label("Create New Bucket", id="create-title")
            yield Label("Bucket Name")
            yield Input(placeholder="e.g. netid-bucket-01", id="bucket_name")
            yield Label("Domain")
            yield Select(
                self._domain_options,
                value=self._default_domain,
                id="domain",
                allow_blank=False,
            )
            yield Label("Permission")
            yield Select(
                PERMISSION_OPTIONS,
                value="private",
                id="permission",
                allow_blank=False,
            )
            with Horizontal(id="create-buttons"):
                yield Button("Create", variant="primary", id="create-ok")
                yield Button("Cancel", variant="default", id="create-cancel")

    def on_mount(self) -> None:
        self.query_one("#bucket_name", Input).focus()

    @on(Button.Pressed, "#create-ok")
    @on(Input.Submitted, "#bucket_name")
    def _submit(self) -> None:
        name = self.query_one("#bucket_name", Input).value.strip()
        permission = str(self.query_one("#permission", Select).value)
        endpoint = str(self.query_one("#domain", Select).value)
        self.dismiss((name, permission, endpoint))

    @on(Button.Pressed, "#create-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class BucketManagementScreen(S3Screen):
    """Manage S3 buckets: list, create, delete, set permissions."""

    class BucketNotEmpty(Message):
        """Worker → main: bucket has objects; ask user before force-deleting."""

        def __init__(self, bucket_name: str, row_key: "RowKey") -> None:
            super().__init__()
            self.bucket_name = bucket_name
            self.row_key = row_key

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("delete", "delete_bucket", "Delete"),
    ]

    CSS = """
    #bucket-table {
        height: 1fr;
        margin: 0 2;
        border: round $accent;
    }
    #action-row {
        height: auto;
        padding: 0 2;
    }
    #action-row Button {
        margin-right: 1;
    }
    #status {
        margin: 0 2;
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield NetworkBar()
        yield DataTable(id="bucket-table")
        with Horizontal(id="action-row"):
            yield Button("New Bucket", variant="primary", id="create_btn")
            yield Button("Delete Selected", variant="error", id="delete_btn")
            yield Button("Refresh", variant="default", id="refresh_btn")
        yield Label("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._update_network_bar()
        table = self.query_one("#bucket-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Bucket", "Domain")
        self._load_buckets()

    def reload_buckets(self) -> None:
        self._load_buckets()

    @work(thread=True, exclusive=True, group="load")
    def _load_buckets(self) -> None:
        status = self.query_one("#status", Label)
        self.ui(status.update, "Loading buckets...")
        try:
            entries = self.s3_app.s3.entries()
            table = self.query_one("#bucket-table", DataTable)
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
            self.ui(status.update, f"{len(entries)} bucket(s)")
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @on(Button.Pressed, "#create_btn")
    def _open_create_dialog(self) -> None:
        def on_result(result: tuple[str, str, str] | None) -> None:
            if result is not None:
                self._create_bucket(*result)

        self.app.push_screen(
            CreateBucketScreen(self.s3_app.s3.reachable_endpoints), on_result
        )

    @on(Button.Pressed, "#refresh_btn")
    def action_refresh(self) -> None:
        self.s3_app.start_probe()
        self._load_buckets()

    @on(Button.Pressed, "#delete_btn")
    def action_delete_bucket(self) -> None:
        self._delete_selected()

    @work(thread=True, exclusive=True, group="delete")
    def _delete_selected(self) -> None:
        table = self.query_one("#bucket-table", DataTable)
        status = self.query_one("#status", Label)

        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            self.ui(status.update, "No bucket selected.")
            return

        bucket_name = str(row_key.value)
        self.ui(status.update, f"Deleting '{bucket_name}'...")
        try:
            self.s3_app.s3.delete_bucket(bucket_name)
            self.ui(status.update, f"Bucket '{bucket_name}' deleted.")
            self.ui(table.remove_row, row_key)
        except EndpointUnreachable as exc:
            self.ui(status.update, str(exc))
        except S3Error as exc:
            if exc.code == "BucketNotEmpty":
                self.post_message(self.BucketNotEmpty(bucket_name, row_key))
            else:
                self.ui(status.update, f"Error: {exc}")
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @on(BucketNotEmpty)
    def _on_bucket_not_empty(self, message: BucketNotEmpty) -> None:
        bucket_name = message.bucket_name
        row_key = message.row_key

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._force_delete(bucket_name, row_key)

        self.app.push_screen(
            ConfirmScreen(
                f"Bucket '{bucket_name}' is not empty.\n"
                "Delete all objects and remove the bucket?"
            ),
            on_confirm,
        )

    @work(thread=True, exclusive=True, group="delete")
    def _force_delete(self, bucket_name: str, row_key: RowKey) -> None:
        table = self.query_one("#bucket-table", DataTable)
        status = self.query_one("#status", Label)

        self.ui(status.update, f"Removing all objects from '{bucket_name}'...")
        try:
            self.s3_app.s3.empty_bucket(bucket_name)
            self.s3_app.s3.delete_bucket(bucket_name)
            self.ui(status.update, f"Bucket '{bucket_name}' and all objects deleted.")
            self.ui(table.remove_row, row_key)
        except EndpointUnreachable as exc:
            self.ui(status.update, str(exc))
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @work(thread=True, exclusive=True, group="create")
    def _create_bucket(self, name: str, permission: str, endpoint: str) -> None:
        status = self.query_one("#status", Label)

        if not name:
            self.ui(status.update, "Bucket name is required.")
            return
        if not BUCKET_NAME_RE.match(name):
            self.ui(
                status.update,
                "Invalid name: 3-63 chars, lowercase letters/digits/hyphens/dots.",
            )
            return

        domain = _domain_name(endpoint)
        try:
            if self.s3_app.s3.bucket_exists(name, endpoint=endpoint):
                self.ui(status.update, f"Bucket '{name}' already exists.")
                return
            self.s3_app.s3.create_bucket(name, endpoint=endpoint)
            if permission != "private":
                self.s3_app.s3.set_bucket_policy(name, str(permission))
            self.ui(
                status.update,
                f"Bucket '{name}' created on {domain} ({permission})!",
            )
            self._load_buckets()
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

"""Bucket management screen — list, create, delete, set permissions."""

from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

from minio.error import S3Error

from uw_s3.validators import BUCKET_NAME_RE
from uw_s3.tui.screens.base import EndpointBar, S3Screen
from uw_s3.tui.screens.confirm import ConfirmScreen

if TYPE_CHECKING:
    from textual.widgets._data_table import RowKey

PERMISSION_OPTIONS: list[tuple[str, str]] = [
    ("Private (default)", "private"),
    ("Public Read", "public-read"),
    ("Public Read/Write (not recommended)", "public-readwrite"),
]


class CreateBucketScreen(ModalScreen[tuple[str, str] | None]):
    """Modal dialog for creating a new bucket."""

    CSS = """
    CreateBucketScreen { align: center middle; }
    #create-dialog {
        width: 60;
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

    def compose(self) -> ComposeResult:
        with Vertical(id="create-dialog"):
            yield Label("Create New Bucket", id="create-title")
            yield Label("Bucket Name")
            yield Input(placeholder="e.g. netid-bucket-01", id="bucket_name")
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
        self.dismiss((name, permission))

    @on(Button.Pressed, "#create-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class BucketManagementScreen(S3Screen):
    """Manage S3 buckets: list, create, delete, set permissions."""

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
        yield EndpointBar()
        yield DataTable(id="bucket-table")
        with Horizontal(id="action-row"):
            yield Button("New Bucket", variant="primary", id="create_btn")
            yield Button("Delete Selected", variant="error", id="delete_btn")
            yield Button("Refresh", variant="default", id="refresh_btn")
        yield Label("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._update_endpoint_bar()
        table = self.query_one("#bucket-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Bucket")
        self._load_buckets()

    def on_endpoint_switched(self) -> None:
        self._load_buckets()

    @work(thread=True, exclusive=True, group="load")
    def _load_buckets(self) -> None:
        status = self.query_one("#status", Label)
        self.ui(status.update, "Loading buckets...")
        try:
            buckets = self.s3_app.s3.list_buckets()
            table = self.query_one("#bucket-table", DataTable)
            self.ui(table.clear)
            for name in sorted(buckets):
                self.ui(table.add_row, name, key=name)
            self.ui(status.update, f"{len(buckets)} bucket(s)")
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @on(Button.Pressed, "#create_btn")
    def _open_create_dialog(self) -> None:
        def on_result(result: tuple[str, str] | None) -> None:
            if result is not None:
                self._create_bucket(*result)

        self.app.push_screen(CreateBucketScreen(), on_result)

    @on(Button.Pressed, "#refresh_btn")
    def action_refresh(self) -> None:
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
        except S3Error as exc:
            if exc.code == "BucketNotEmpty":
                self._confirm_force_delete(bucket_name, row_key)
            else:
                self.ui(status.update, f"Error: {exc}")
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    def _confirm_force_delete(self, bucket_name: str, row_key: RowKey) -> None:
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._force_delete(bucket_name, row_key)

        self.ui(
            self.app.push_screen,
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
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @work(thread=True, exclusive=True, group="create")
    def _create_bucket(self, name: str, permission: str) -> None:
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

        try:
            if self.s3_app.s3.bucket_exists(name):
                self.ui(status.update, f"Bucket '{name}' already exists.")
                return
            self.s3_app.s3.create_bucket(name)
            if permission != "private":
                self.s3_app.s3.set_bucket_policy(name, str(permission))
            self.ui(status.update, f"Bucket '{name}' created ({permission})!")
            self._load_buckets()
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

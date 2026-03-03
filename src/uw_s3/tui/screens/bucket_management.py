"""Bucket management screen — list, create, delete, set permissions."""

from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

from minio.deleteobjects import DeleteObject
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


class BucketManagementScreen(S3Screen):
    """Manage S3 buckets: list, create, delete, set permissions."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("delete", "delete_bucket", "Delete"),
    ]

    CSS = """
    #bucket-table {
        height: 1fr;
        margin: 1 2 0 2;
        border: round $accent;
    }
    #action-row {
        height: auto;
        padding: 1 2;
    }
    #action-row Button {
        margin-right: 1;
    }
    #create-form {
        height: auto;
        margin: 0 2;
        padding: 1 2;
        background: $boost;
        border: round $primary;
    }
    #create-form .title {
        text-style: bold;
        margin-bottom: 1;
    }
    #create-form Label {
        margin-top: 1;
    }
    #create-form Button {
        margin-top: 1;
    }
    #status {
        margin: 0 2 1 2;
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
            yield Button("Delete Selected", variant="error", id="delete_btn")
            yield Button("Refresh", variant="default", id="refresh_btn")
        with Vertical(id="create-form"):
            yield Label("Create Bucket", classes="title")
            yield Label("Bucket Name")
            yield Input(placeholder="e.g. netid-bucket-01", id="bucket_name")
            yield Label("Permission")
            yield Select(
                PERMISSION_OPTIONS,
                value="private",
                id="permission",
                allow_blank=False,
            )
            yield Button("Create Bucket", variant="primary", id="create_btn")
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
            objects = list(
                self.s3_app.s3.client.list_objects(bucket_name, recursive=True)
            )
            if objects:
                delete_list = [DeleteObject(obj.object_name) for obj in objects]
                errors = list(
                    self.s3_app.s3.client.remove_objects(bucket_name, delete_list)
                )
                if errors:
                    self.ui(
                        status.update,
                        f"Error removing objects: {errors[0].message}",
                    )
                    return
            self.s3_app.s3.delete_bucket(bucket_name)
            self.ui(status.update, f"Bucket '{bucket_name}' and all objects deleted.")
            self.ui(table.remove_row, row_key)
        except Exception as exc:
            self.ui(status.update, f"Error: {exc}")

    @on(Button.Pressed, "#create_btn")
    @work(thread=True, exclusive=True, group="create")
    def handle_create(self) -> None:
        name = self.query_one("#bucket_name", Input).value.strip()
        permission = self.query_one("#permission", Select).value
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

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

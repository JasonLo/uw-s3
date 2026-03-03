"""Browse buckets and objects screen."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from uw_s3 import CAMPUS_ENDPOINT


class BucketListScreen(Screen):
    """List all buckets; select one to see its objects."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    CSS = """
    #info {
        dock: top;
        height: 1;
        padding: 0 1;
    }
    DataTable {
        height: 1fr;
    }
    """

    _viewing_objects: bool = False
    _current_bucket: str = ""

    def _endpoint_label(self) -> str:
        app = self.app  # type: ignore[assignment]
        return "Campus" if app.s3.endpoint == CAMPUS_ENDPOINT else "Web"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Loading buckets...", id="info")
        yield DataTable(id="table")
        yield Footer()

    def on_mount(self) -> None:
        self._load_buckets()

    @work(thread=True)
    def _load_buckets(self) -> None:
        app = self.app  # type: ignore[assignment]
        table = self.query_one("#table", DataTable)
        info = self.query_one("#info", Label)
        endpoint = self._endpoint_label()
        try:
            buckets = app.s3.list_buckets()
            self.app.call_from_thread(
                info.update, f"{len(buckets)} bucket(s) — connected via {endpoint}"
            )
            self.app.call_from_thread(table.clear, columns=True)
            self.app.call_from_thread(table.add_column, "Bucket Name", key="name")
            self.app.call_from_thread(table.add_column, "Endpoint", key="endpoint")
            for b in buckets:
                self.app.call_from_thread(table.add_row, b, endpoint, key=b)
            self._viewing_objects = False
        except Exception as exc:
            self.app.call_from_thread(info.update, f"Error: {exc}")

    @work(thread=True)
    def _load_objects(self, bucket: str) -> None:
        app = self.app  # type: ignore[assignment]
        table = self.query_one("#table", DataTable)
        info = self.query_one("#info", Label)
        endpoint = self._endpoint_label()
        try:
            objects = app.s3.list_objects(bucket)
            self.app.call_from_thread(
                info.update,
                f"Bucket: {bucket} ({endpoint}) — {len(objects)} object(s)",
            )
            self.app.call_from_thread(table.clear, columns=True)
            self.app.call_from_thread(table.add_column, "Object Key", key="key")
            for obj in objects:
                self.app.call_from_thread(table.add_row, obj, key=obj)
            self._viewing_objects = True
            self._current_bucket = bucket
        except Exception as exc:
            self.app.call_from_thread(info.update, f"Error: {exc}")

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        if not self._viewing_objects:
            bucket = str(event.row_key.value)
            self._load_objects(bucket)

    def action_go_back(self) -> None:
        if self._viewing_objects:
            self._load_buckets()
        else:
            self.app.pop_screen()

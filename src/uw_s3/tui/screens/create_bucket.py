"""Create-bucket screen."""

from __future__ import annotations

from typing import cast

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3.validators import BUCKET_NAME_RE

ENDPOINT_OPTIONS: list[tuple[str, str]] = [
    ("Campus (UW network / VPN)", CAMPUS_ENDPOINT),
    ("Web (any network)", WEB_ENDPOINT),
]


class CreateBucketScreen(Screen):
    """Form to create a new S3 bucket."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
    ]

    CSS = """
    #form {
        width: 60;
        height: auto;
        padding: 1 2;
    }
    #form Label {
        margin-top: 1;
    }
    #status {
        margin-top: 1;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Endpoint")
            yield Select(
                ENDPOINT_OPTIONS,
                value=CAMPUS_ENDPOINT,
                id="endpoint",
                allow_blank=False,
            )
            yield Label("Bucket Name")
            yield Input(placeholder="e.g. netid-bucket-01", id="bucket_name")
            yield Button("Create Bucket", variant="primary", id="create_btn")
            yield Label("", id="status")
        yield Footer()

    @on(Button.Pressed, "#create_btn")
    @work(thread=True)
    def handle_create(self) -> None:
        endpoint = self.query_one("#endpoint", Select).value
        name = self.query_one("#bucket_name", Input).value.strip()
        status = self.query_one("#status", Label)

        if not name:
            self.app.call_from_thread(status.update, "Bucket name is required.")
            return
        if not BUCKET_NAME_RE.match(name):
            self.app.call_from_thread(
                status.update,
                "Invalid name: 3-63 chars, lowercase letters/digits/hyphens/dots.",
            )
            return

        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        client = UWS3(app.access_key, app.secret_key, endpoint=str(endpoint))

        try:
            if client.bucket_exists(name):
                self.app.call_from_thread(
                    status.update, f"Bucket '{name}' already exists."
                )
                return
            client.create_bucket(name)
            self.app.call_from_thread(
                status.update, f"Bucket '{name}' created successfully!"
            )
        except Exception as exc:
            self.app.call_from_thread(status.update, f"Error: {exc}")

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

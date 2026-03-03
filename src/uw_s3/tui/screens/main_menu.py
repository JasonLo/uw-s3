"""Main menu screen."""

from __future__ import annotations

from typing import cast

from rich.console import Group
from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option


def _option(key: str, title: str, desc: str) -> Group:
    return Group(
        Text.from_markup(f" [bold]{key}[/]   {title}"),
        Text.from_markup(f"      [dim]{desc}[/]"),
    )


class MainMenuScreen(Screen):
    """Landing screen with navigation options."""

    BINDINGS = [
        Binding("e", "switch_endpoint", "Switch Endpoint"),
        Binding("f", "file_manager", "File Manager"),
        Binding("m", "mount_bucket", "Mount Bucket"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    #endpoint-info {
        height: auto;
        padding: 1 2;
    }
    #menu {
        margin: 0 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="endpoint-info")
        yield OptionList(
            Option(
                _option(
                    "f",
                    "File Manager",
                    "Browse buckets, upload/download files, and sync folders",
                ),
                id="file_manager",
            ),
            Option(
                _option(
                    "m",
                    "Mount Bucket",
                    "Mount an S3 bucket as a local directory via rclone",
                ),
                id="mount",
            ),
            Option(
                _option("q", "Quit", "Exit the application"),
                id="quit",
            ),
            id="menu",
        )
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        actions = {
            "file_manager": self.action_file_manager,
            "mount": self.action_mount_bucket,
            "quit": self.action_quit,
        }
        action = actions.get(event.option.id or "")
        if action:
            action()

    def _update_endpoint_label(self) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        ep = app.endpoint_label
        info = self.query_one("#endpoint-info", Static)
        info.update(
            Text.from_markup(
                f"  [bold]Endpoint:[/] {ep}   [dim italic]press e to switch[/]"
            )
        )

    def on_mount(self) -> None:
        self._update_endpoint_label()

    def on_screen_resume(self) -> None:
        self._update_endpoint_label()

    def action_switch_endpoint(self) -> None:
        from uw_s3.tui.app import UWS3App

        app = cast(UWS3App, self.app)
        app.switch_endpoint()
        self._update_endpoint_label()
        self.notify(f"Switched to {app.endpoint_label}")

    def action_file_manager(self) -> None:
        from uw_s3.tui.screens.file_manager import FileManagerScreen

        self.app.push_screen(FileManagerScreen())

    def action_mount_bucket(self) -> None:
        from uw_s3.tui.screens.mount import MountScreen

        self.app.push_screen(MountScreen())

    def action_quit(self) -> None:
        self.app.exit()

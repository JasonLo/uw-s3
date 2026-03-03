"""Main menu screen."""

from __future__ import annotations

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
        Binding("s", "sync_folder", "Sync Folder"),
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
                _option("s", "Sync Folder", "Push and pull files between a local folder and S3"),
                id="sync",
            ),
            Option(
                _option("m", "Mount Bucket", "Mount an S3 bucket as a local directory via rclone"),
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
            "sync": self.action_sync_folder,
            "mount": self.action_mount_bucket,
            "quit": self.action_quit,
        }
        action = actions.get(event.option.id or "")
        if action:
            action()

    def _update_endpoint_label(self) -> None:
        app = self.app  # type: ignore[assignment]
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
        app = self.app  # type: ignore[assignment]
        app.switch_endpoint()
        self._update_endpoint_label()
        self.notify(f"Switched to {app.endpoint_label}")

    def action_sync_folder(self) -> None:
        from uw_s3.tui.screens.sync import SyncScreen

        self.app.push_screen(SyncScreen())

    def action_mount_bucket(self) -> None:
        from uw_s3.tui.screens.mount import MountScreen

        self.app.push_screen(MountScreen())

    def action_quit(self) -> None:
        self.app.exit()

"""Main menu screen."""

import os
import threading

from rich.console import Group
from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, OptionList
from textual.widgets.option_list import Option

from uw_s3.tui.screens.base import EndpointBar, S3Screen


def _option(key: str, title: str, desc: str) -> Group:
    return Group(
        Text.from_markup(f" [bold]{key}[/]   {title}"),
        Text.from_markup(f"      [dim]{desc}[/]"),
    )


class MainMenuScreen(S3Screen):
    """Landing screen with navigation options."""

    BINDINGS = [
        Binding("1", "bucket_management", "Manage Buckets"),
        Binding("2", "file_manager", "Manage Files"),
        Binding("3", "mount_bucket", "Mount Bucket"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    #menu {
        margin: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield EndpointBar()
        yield OptionList(
            Option(
                _option(
                    "1",
                    "Manage Buckets",
                    "Create, delete, and set permissions on S3 buckets",
                ),
                id="bucket_management",
            ),
            Option(
                _option(
                    "2",
                    "Manage Files",
                    "Browse buckets, upload/download files, and sync folders",
                ),
                id="file_manager",
            ),
            Option(
                _option(
                    "3",
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
            "bucket_management": self.action_bucket_management,
            "mount": self.action_mount_bucket,
            "quit": self.action_quit,
        }
        action = actions.get(event.option.id or "")
        if action:
            action()

    def on_mount(self) -> None:
        self._update_endpoint_bar()

    def on_screen_resume(self) -> None:
        self._update_endpoint_bar()

    def action_file_manager(self) -> None:
        from uw_s3.tui.screens.file_manager import FileManagerScreen

        self.app.push_screen(FileManagerScreen())

    def action_bucket_management(self) -> None:
        from uw_s3.tui.screens.bucket_management import BucketManagementScreen

        self.app.push_screen(BucketManagementScreen())

    def action_quit(self) -> None:
        self.s3_app.cleanup_mounts()
        self.app.exit()
        threading.Timer(1.0, os._exit, args=(0,)).start()

    def action_mount_bucket(self) -> None:
        from uw_s3.tui.screens.mount import MountScreen

        self.app.push_screen(MountScreen())



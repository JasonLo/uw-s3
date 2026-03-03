"""Main Textual application for uw-s3."""

from __future__ import annotations

from textual.app import App
from textual.theme import Theme

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3.rclone import RcloneMount
from uw_s3.tui.screens.main_menu import MainMenuScreen

UW_THEME = Theme(
    name="uw-s3",
    primary="#7AA2F7",
    secondary="#7B8FA1",
    accent="#BB9AF7",
    foreground="#C0CAF5",
    background="#1A1B26",
    success="#9ECE6A",
    warning="#E0AF68",
    error="#F7768E",
    surface="#24283B",
    panel="#414868",
    dark=True,
    variables={
        "footer-key-foreground": "#7AA2F7",
        "block-cursor-text-style": "bold",
        "input-selection-background": "#7AA2F7 30%",
    },
)


class UWS3App(App):
    """Terminal UI for UW-Madison Research Object Storage."""

    TITLE = "uw-s3"
    SUB_TITLE = "UW-Madison Research Object Storage"

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        endpoint: str = CAMPUS_ENDPOINT,
    ) -> None:
        super().__init__()
        self.access_key = access_key
        self.secret_key = secret_key
        self.s3 = UWS3(access_key, secret_key, endpoint=endpoint)
        self.active_mounts: dict[str, RcloneMount] = {}

    @property
    def endpoint_label(self) -> str:
        return "Campus" if self.s3.endpoint == CAMPUS_ENDPOINT else "Web"

    def switch_endpoint(self) -> None:
        """Toggle between Campus and Web endpoints."""
        new = WEB_ENDPOINT if self.s3.endpoint == CAMPUS_ENDPOINT else CAMPUS_ENDPOINT
        self.s3 = UWS3(self.access_key, self.secret_key, endpoint=new)
        self.sub_title = f"Endpoint: {self.endpoint_label}"

    def on_mount(self) -> None:
        self.register_theme(UW_THEME)
        self.theme = "uw-s3"
        self.sub_title = f"Endpoint: {self.endpoint_label}"
        self.push_screen(MainMenuScreen())

    def on_unmount(self) -> None:
        """Clean up any active rclone mounts when the app exits."""
        for rm in self.active_mounts.values():
            try:
                rm.unmount()
            except Exception:
                pass
        self.active_mounts.clear()

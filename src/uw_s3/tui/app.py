"""Main Textual application for uw-s3."""

from textual.app import App

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3.preferences import load_preferences, update_preference
from uw_s3.rclone import RcloneMount
from uw_s3.tui.screens.main_menu import MainMenuScreen


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
        prefs = load_preferences()
        self.last_bucket: str = prefs.get("last_bucket", "")

    @property
    def endpoint_label(self) -> str:
        return "Campus" if self.s3.endpoint == CAMPUS_ENDPOINT else "Web"

    def switch_endpoint(self) -> None:
        """Toggle between Campus and Web endpoints."""
        new = WEB_ENDPOINT if self.s3.endpoint == CAMPUS_ENDPOINT else CAMPUS_ENDPOINT
        self.s3 = UWS3(self.access_key, self.secret_key, endpoint=new)
        self.sub_title = f"Endpoint: {self.endpoint_label}"
        update_preference("endpoint", new)

    def save_last_bucket(self, bucket: str) -> None:
        """Persist the last-selected bucket."""
        self.last_bucket = bucket
        update_preference("last_bucket", bucket)

    def on_mount(self) -> None:
        self.theme = "atom-one-dark"
        self.sub_title = f"Endpoint: {self.endpoint_label}"
        self.push_screen(MainMenuScreen())

    def cleanup_mounts(self) -> None:
        """Terminate all rclone subprocesses and remove temp configs."""
        for rm in self.active_mounts.values():
            try:
                rm.unmount()
            except Exception:
                pass
        self.active_mounts.clear()

    def on_unmount(self) -> None:
        self.cleanup_mounts()

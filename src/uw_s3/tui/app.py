"""Main Textual application for uw-s3."""

import asyncio

from textual.app import App

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3 import mounts_config
from uw_s3.mount_backend import Mount, WorkerMount, clear_stale_mount
from uw_s3.preferences import load_preferences, update_preference
from uw_s3.tui.screens.main_menu import MainMenuScreen
from uw_s3.tui.screens.survival_prompt import SurvivalPromptScreen


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
        self.active_mounts: dict[str, Mount | WorkerMount] = {}
        self._quitting: bool = False
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
        self.restore_active_mounts()
        self.push_screen(MainMenuScreen())

    def restore_active_mounts(self) -> None:
        """Re-attach to any surviving worker processes from prior sessions."""
        dead = mounts_config.clear_dead()
        for record in dead:
            clear_stale_mount(record.mount_point)
        for record in mounts_config.load():
            self.active_mounts[record.bucket] = WorkerMount.attach(record)

    async def action_quit(self) -> None:
        """Prompt the user about active mounts before exiting."""
        if self._quitting:
            return
        if not self.active_mounts:
            self.exit()
            return
        self._quitting = True
        keep = await self.push_screen_wait(
            SurvivalPromptScreen(len(self.active_mounts))
        )
        try:
            await asyncio.to_thread(self._finalize_mounts, bool(keep))
        finally:
            self.exit()

    def _finalize_mounts(self, keep: bool) -> None:
        """Background-thread finalization. Constitution §4 keeps event loop free."""
        if keep:
            self._detach_all()
        else:
            self._unmount_all()

    def _detach_all(self) -> None:
        """Convert in-process Mounts to detached WorkerMounts; leave existing workers."""
        for bucket, m in list(self.active_mounts.items()):
            if isinstance(m, WorkerMount):
                continue
            try:
                m.unmount()
                worker = WorkerMount(
                    access_key=m.access_key,
                    secret_key=m.secret_key,
                    endpoint=m.endpoint,
                    bucket=m.bucket,
                    mount_point=m.mount_point,
                )
                worker.mount()
                mounts_config.add(worker.to_record())
                self.active_mounts[bucket] = worker
            except Exception:
                pass

    def _unmount_all(self) -> None:
        """Unmount every active mount and clear persisted records."""
        for bucket, m in list(self.active_mounts.items()):
            try:
                m.unmount()
            except Exception:
                pass
            if isinstance(m, WorkerMount):
                mounts_config.remove(bucket, str(m.mount_point))
        self.active_mounts.clear()

    async def on_unmount(self) -> None:
        """Fallback cleanup for non-interactive exits (SIGHUP, crash).

        Interactive quits go through `action_quit` and have already handled
        teardown; this path only fires when the prompt never ran. It unmounts
        in-process Mounts (since no one's alive to detach them) and leaves
        existing WorkerMounts alone — they were already detached.
        """
        if self._quitting:
            return
        for bucket, m in list(self.active_mounts.items()):
            if isinstance(m, WorkerMount):
                continue
            try:
                await asyncio.to_thread(m.unmount)
            except Exception:
                pass
            self.active_mounts.pop(bucket, None)

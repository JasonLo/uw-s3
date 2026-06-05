"""Base screen class for S3 TUI screens."""

from typing import TYPE_CHECKING, Any, cast

from rich.text import Text

from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Static
from textual.worker import NoActiveWorker, get_current_worker

from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT

if TYPE_CHECKING:
    from uw_s3.tui.app import UWS3App


def network_status_text(reachable: set[str]) -> str:
    """Render the passive network status line from the reachable-endpoint set."""
    has_campus = CAMPUS_ENDPOINT in reachable
    has_web = WEB_ENDPOINT in reachable
    if has_campus and has_web:
        return "  [bold]Network:[/] Campus + Web [dim]— all buckets reachable[/]"
    if has_web:
        return (
            "  [bold]Network:[/] Web only "
            "[dim]— campus buckets need the UW network or VPN[/]"
        )
    if has_campus:
        return "  [bold]Network:[/] Campus only [dim]— on the UW network[/]"
    return "  [bold]Network:[/] [red]offline[/] [dim]— no endpoints reachable[/]"


class NetworkBar(Static):
    """Passive banner showing which S3 endpoints are reachable right now."""

    DEFAULT_CSS = """
    NetworkBar {
        height: auto;
        padding: 0 2;
        margin: 0 2;
        background: $boost;
        border: round $primary;
    }
    """


class S3Screen(Screen):
    """Screen with typed access to UWS3App and a threading shorthand."""

    @property
    def s3_app(self) -> UWS3App:
        from uw_s3.tui.app import UWS3App

        return cast(UWS3App, self.app)

    def ui(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Call a function on the main thread from a worker; no-op if cancelled."""
        try:
            worker = get_current_worker()
        except NoActiveWorker:
            return fn(*args, **kwargs)
        if worker.is_cancelled:
            return None
        return self.app.call_from_thread(fn, *args, **kwargs)

    def action_pop_screen(self) -> None:
        self.workers.cancel_all()
        self.app.pop_screen()

    def _update_network_bar(self) -> None:
        try:
            bar = self.query_one(NetworkBar)
        except NoMatches:
            return
        bar.update(
            Text.from_markup(network_status_text(self.s3_app.s3.reachable_endpoints))
        )

    def reload_buckets(self) -> None:
        """Override to reload bucket-derived data after a probe refresh."""

    def refresh_for_probe(self) -> None:
        """Called after a background probe completes; refresh bar + data."""
        self._update_network_bar()
        self.reload_buckets()

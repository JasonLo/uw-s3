"""Base screen class for S3 TUI screens."""

from typing import TYPE_CHECKING, Any, cast

from rich.text import Text

from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

if TYPE_CHECKING:
    from uw_s3.tui.app import UWS3App


class EndpointBar(Static, can_focus=True):
    """Displays the current S3 endpoint — click or press e to switch."""

    DEFAULT_CSS = """
    EndpointBar {
        height: auto;
        padding: 0 2;
        margin: 0 2;
        background: $boost;
        border: round $primary;
    }
    EndpointBar:hover {
        background: $primary 20%;
    }
    """

    def on_click(self) -> None:
        self.screen.action_switch_endpoint()


class S3Screen(Screen):
    """Screen with typed access to UWS3App and a threading shorthand."""

    BINDINGS = [
        Binding("e", "switch_endpoint", "Switch Endpoint"),
    ]

    @property
    def s3_app(self) -> UWS3App:
        from uw_s3.tui.app import UWS3App

        return cast(UWS3App, self.app)

    def ui(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Call a function on the main thread from a worker."""
        try:
            return self.app.call_from_thread(fn, *args, **kwargs)
        except Exception:
            return None

    def action_pop_screen(self) -> None:
        self.workers.cancel_all()
        self.app.pop_screen()

    def _update_endpoint_bar(self) -> None:
        try:
            bar = self.query_one(EndpointBar)
        except Exception:
            return
        ep = self.s3_app.endpoint_label
        hint = (
            "requires UW network or VPN" if ep == "Campus" else "works from any network"
        )
        bar.update(
            Text.from_markup(
                f"  [bold]Endpoint:[/] {ep} [dim]({hint})[/]"
                f"   [dim]— buckets are tied to their creation endpoint[/]"
            )
        )

    def action_switch_endpoint(self) -> None:
        self.s3_app.switch_endpoint()
        self._update_endpoint_bar()
        self.notify(f"Switched to {self.s3_app.endpoint_label}")
        self.on_endpoint_switched()

    def on_endpoint_switched(self) -> None:
        """Override to reload data after an endpoint switch."""

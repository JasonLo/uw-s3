"""Exit-time survival prompt — keep mounts running after the TUI exits?"""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class SurvivalPromptScreen(ModalScreen[bool]):
    """Modal asking whether to detach the active mounts or unmount them."""

    BINDINGS = [Binding("escape", "unmount_all", "Unmount all")]

    CSS = """
    SurvivalPromptScreen { align: center middle; }
    #survival-dialog { width: 72; height: auto; padding: 2 4; border: round $warning; background: $boost; }
    #survival-title { margin-bottom: 1; text-style: bold; }
    #survival-body { margin-bottom: 2; }
    #survival-buttons { height: auto; align: center middle; }
    #survival-buttons Button { margin: 0 1; }
    """

    def __init__(self, mount_count: int) -> None:
        super().__init__()
        self._mount_count = mount_count

    def compose(self) -> ComposeResult:
        plural = "mount" if self._mount_count == 1 else "mounts"
        with Vertical(id="survival-dialog"):
            yield Label(
                f"You have {self._mount_count} active {plural}.",
                id="survival-title",
            )
            yield Label(
                "Keep running in the background after the TUI exits? Open file "
                "handles at the mount point may see a brief stale-FS error during "
                "the handoff.",
                id="survival-body",
            )
            with Horizontal(id="survival-buttons"):
                unmount_btn = Button(
                    "Unmount all",
                    variant="default",
                    id="survival-unmount",
                )
                yield unmount_btn
                yield Button(
                    f"Keep {self._mount_count} {plural} running",
                    variant="warning",
                    id="survival-keep",
                )

    def on_mount(self) -> None:
        self.query_one("#survival-unmount", Button).focus()

    @on(Button.Pressed, "#survival-keep")
    def _keep(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#survival-unmount")
    def action_unmount_all(self) -> None:
        self.dismiss(False)

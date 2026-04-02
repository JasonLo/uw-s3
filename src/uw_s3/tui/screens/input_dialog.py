"""Generic single-field input dialog screen."""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class InputScreen(ModalScreen[str | None]):
    """Modal dialog that prompts the user for a single text value."""

    CSS = """
    InputScreen { align: center middle; }
    #input-dialog {
        width: 60;
        height: auto;
        padding: 2 4;
        border: round $accent;
        background: $boost;
    }
    #input-title { margin-bottom: 1; text-style: bold; }
    #input-dialog Input { margin-top: 0; }
    #input-buttons { height: auto; align: center middle; margin-top: 1; }
    #input-buttons Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, value: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._value = value

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Label(self._prompt, id="input-title")
            yield Input(value=self._value, id="input-field")
            with Horizontal(id="input-buttons"):
                yield Button("OK", variant="primary", id="input-ok")
                yield Button("Cancel", variant="default", id="input-cancel")

    def on_mount(self) -> None:
        field = self.query_one("#input-field", Input)
        field.focus()
        field.cursor_position = len(self._value)

    @on(Button.Pressed, "#input-ok")
    @on(Input.Submitted, "#input-field")
    def _submit(self) -> None:
        value = self.query_one("#input-field", Input).value.strip()
        self.dismiss(value if value else None)

    @on(Button.Pressed, "#input-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)

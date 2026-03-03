"""Sync screen — map a local folder to an S3 bucket and push/pull."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Label,
    Log,
    Select,
)

from uw_s3 import UWS3
from uw_s3.sync.config import add_mapping
from uw_s3.sync.engine import SyncEngine
from uw_s3.sync.models import SyncMap


class SyncScreen(Screen):
    """Configure and run sync between a local folder and an S3 bucket."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    CSS = """
    #layout { height: 1fr; }
    #tree { width: 1fr; height: 1fr; margin: 0 1 0 0; border: solid $accent; }
    #controls { width: 1fr; height: 1fr; padding: 1 2; border: solid $accent; }
    .btn-row { height: auto; }
    .btn-row Button { margin: 1 1 0 0; }
    #log { height: 1fr; margin-top: 1; border: solid $panel; }
    #selected-dir { margin: 1 0; }
    """

    selected_path: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            tree = DirectoryTree(".", id="tree")
            tree.border_title = "Local Files"
            yield tree
            with Vertical(id="controls") as panel:
                panel.border_title = "Sync"
                yield Label("[bold]Bucket[/]")
                yield Select([], id="bucket-select", prompt="Loading buckets...")
                yield Label("Selected folder: [dim](none)[/]", id="selected-dir")
                with Horizontal(classes="btn-row"):
                    yield Button("Preview Push", id="preview-push")
                    yield Button("Preview Pull", id="preview-pull")
                with Horizontal(classes="btn-row"):
                    yield Button("Push", variant="primary", id="push-btn")
                    yield Button("Pull", variant="success", id="pull-btn")
                log = Log(id="log")
                log.border_title = "Output"
                yield log
        yield Footer()

    def on_mount(self) -> None:
        self._load_buckets()

    @work(thread=True)
    def _load_buckets(self) -> None:
        app = self.app  # type: ignore[assignment]
        try:
            buckets = app.s3.list_buckets()
            options = [(b, b) for b in buckets]
            sel = self.query_one("#bucket-select", Select)
            self.app.call_from_thread(setattr, sel, "prompt", "Select a bucket")
            self.app.call_from_thread(sel.set_options, options)
        except Exception as exc:
            log = self.query_one("#log", Log)
            self.app.call_from_thread(log.write_line, f"Error loading buckets: {exc}")

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.selected_path = str(event.path)
        self.query_one("#selected-dir", Label).update(
            f"Selected folder: [bold]{self.selected_path}[/]"
        )

    def _get_mapping(self) -> SyncMap | None:
        bucket = self.query_one("#bucket-select", Select).value
        log = self.query_one("#log", Log)
        if bucket is Select.BLANK:
            log.write_line("Please select a bucket first.")
            return None
        if not self.selected_path:
            log.write_line("Please select a local folder first.")
            return None
        app = self.app  # type: ignore[assignment]
        return SyncMap(
            local_dir=self.selected_path,
            bucket=str(bucket),
            endpoint=app.s3.endpoint,
        )

    @on(Button.Pressed, "#preview-push")
    @work(thread=True)
    def handle_preview_push(self) -> None:
        mapping = self.app.call_from_thread(self._get_mapping)
        if not mapping:
            return
        log = self.query_one("#log", Log)
        app = self.app  # type: ignore[assignment]
        engine = SyncEngine(app.s3, mapping)
        try:
            actions = engine.status_push()
            self.app.call_from_thread(log.clear)
            if not actions:
                self.app.call_from_thread(log.write_line, "Nothing to push — all in sync.")
            else:
                self.app.call_from_thread(
                    log.write_line, f"{len(actions)} file(s) would be pushed:"
                )
                for a in actions:
                    self.app.call_from_thread(
                        log.write_line, f"  {a.relative_path}  ({a.reason})"
                    )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    @on(Button.Pressed, "#preview-pull")
    @work(thread=True)
    def handle_preview_pull(self) -> None:
        mapping = self.app.call_from_thread(self._get_mapping)
        if not mapping:
            return
        log = self.query_one("#log", Log)
        app = self.app  # type: ignore[assignment]
        engine = SyncEngine(app.s3, mapping)
        try:
            actions = engine.status_pull()
            self.app.call_from_thread(log.clear)
            if not actions:
                self.app.call_from_thread(log.write_line, "Nothing to pull — all in sync.")
            else:
                self.app.call_from_thread(
                    log.write_line, f"{len(actions)} file(s) would be pulled:"
                )
                for a in actions:
                    self.app.call_from_thread(
                        log.write_line, f"  {a.relative_path}  ({a.reason})"
                    )
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    @on(Button.Pressed, "#push-btn")
    @work(thread=True)
    def handle_push(self) -> None:
        mapping = self.app.call_from_thread(self._get_mapping)
        if not mapping:
            return
        log = self.query_one("#log", Log)
        app = self.app  # type: ignore[assignment]
        engine = SyncEngine(app.s3, mapping)
        self.app.call_from_thread(log.clear)
        self.app.call_from_thread(log.write_line, "Pushing...")
        try:
            actions = engine.push(
                callback=lambda a: self.app.call_from_thread(
                    log.write_line, f"  ▲ {a.relative_path}"
                )
            )
            self.app.call_from_thread(
                log.write_line, f"Done — {len(actions)} file(s) pushed."
            )
            add_mapping(mapping)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    @on(Button.Pressed, "#pull-btn")
    @work(thread=True)
    def handle_pull(self) -> None:
        mapping = self.app.call_from_thread(self._get_mapping)
        if not mapping:
            return
        log = self.query_one("#log", Log)
        app = self.app  # type: ignore[assignment]
        engine = SyncEngine(app.s3, mapping)
        self.app.call_from_thread(log.clear)
        self.app.call_from_thread(log.write_line, "Pulling...")
        try:
            actions = engine.pull(
                callback=lambda a: self.app.call_from_thread(
                    log.write_line, f"  ▼ {a.relative_path}"
                )
            )
            self.app.call_from_thread(
                log.write_line, f"Done — {len(actions)} file(s) pulled."
            )
            add_mapping(mapping)
        except Exception as exc:
            self.app.call_from_thread(log.write_line, f"Error: {exc}")

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

"""Textual TUI (Section 11).

Runs the same pipeline as `analyze`, holds a single Report, and renders a slice
of it per panel. `r` re-runs, `e` expands findings, `f` cycles a severity filter,
`s` saves to JSON, `q` quits.
"""

from __future__ import annotations

from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from ..models.finding import Severity
from ..models.report import Report
from ..output.json_out import render_json
from .panels import (
    clients,
    config,
    explore,
    health,
    keys,
    memory,
    replication,
    sentinel,
    slowlog,
    streams,
)

PANELS: list[tuple[str, Callable]] = [
    ("Health", health.render),
    ("Memory", memory.render),
    ("Keys", keys.render),
    ("Explore", explore.render),
    ("Streams", streams.render),
    ("Clients", clients.render),
    ("Slowlog", slowlog.render),
    ("Config", config.render),
    ("Replication", replication.render),
    ("Sentinel", sentinel.render),
]

_FILTER_CYCLE = [None, Severity.CRITICAL, Severity.WARNING]


class SaveScreen(ModalScreen[str]):
    """Prompt for a path to save the report JSON."""

    def compose(self) -> ComposeResult:
        yield Input(value="redis-doctor-report.json", placeholder="path to save JSON")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class RedisDoctorTUI(App):
    CSS = """
    #sidebar { width: 22; border: round $primary; }
    #content { padding: 1; }
    """

    BINDINGS = [
        ("r", "rerun", "Re-run"),
        ("e", "expand", "Expand"),
        ("f", "filter", "Filter"),
        ("s", "save", "Save"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, run_analysis: Callable[[], Report], target: str = ""):
        super().__init__()
        self._run_analysis = run_analysis
        self.target = target
        self.report: Report | None = None
        self.panel_index = 0
        self.filter_index = 0
        self.expanded = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(
                *[ListItem(Label(name), id=f"panel-{i}") for i, (name, _) in enumerate(PANELS)],
                id="sidebar",
            )
            with VerticalScroll(id="content-wrap"):
                yield Static("Running analysis...", id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "redis-doctor"
        self.sub_title = self.target
        self.run_worker(self._analyze, thread=True)

    def _analyze(self) -> None:
        report = self._run_analysis()
        self.call_from_thread(self._set_report, report)

    def _set_report(self, report: Report) -> None:
        self.report = report
        self.refresh_content()

    # --- actions ----------------------------------------------------------

    def action_rerun(self) -> None:
        self.query_one("#content", Static).update("Re-running analysis...")
        self.run_worker(self._analyze, thread=True)

    def action_expand(self) -> None:
        self.expanded = not self.expanded
        self.refresh_content()

    def action_filter(self) -> None:
        self.filter_index = (self.filter_index + 1) % len(_FILTER_CYCLE)
        self.refresh_content()

    def action_save(self) -> None:
        if self.report is None:
            return
        self.push_screen(SaveScreen(), self._do_save)

    def _do_save(self, path: str | None) -> None:
        if path and self.report is not None:
            self.save_to(path)
            self.notify(f"Saved report to {path}")

    def save_to(self, path: str) -> None:
        assert self.report is not None
        with open(path, "w") as fh:
            fh.write(render_json(self.report))

    # --- panel switching --------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is not None and event.item.id:
            self.panel_index = int(event.item.id.split("-")[1])
            self.refresh_content()

    def refresh_content(self) -> None:
        content = self.query_one("#content", Static)
        if self.report is None:
            content.update("Running analysis...")
            return
        _, render_fn = PANELS[self.panel_index]
        severity = _FILTER_CYCLE[self.filter_index]
        try:
            content.update(render_fn(self.report, severity, self.expanded))
        except Exception as e:  # never let a render error kill the TUI
            content.update(f"render error: {e}")

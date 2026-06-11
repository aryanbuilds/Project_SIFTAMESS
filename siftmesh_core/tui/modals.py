"""Cockpit detail modals (Epic C full-console) — read-only drill-downs over run files.

`ModalScreen`s the cockpit pushes for task / claim / replay detail. Each renders straight from the
run files + the tested `load_report_view` — no orchestration logic, no engine writes. Dismissed with
`escape`.
"""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Label,
    RadioButton,
    RadioSet,
    Static,
    TabbedContent,
    TabPane,
)

from siftmesh_core.orchestrator.human_gate import GATES
from siftmesh_core.reports import render_text_replay
from siftmesh_core.reports.loader import load_report_view
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import GateName
from siftmesh_core.tui import widgets


class GateScreen(ModalScreen["tuple[GateName, bool] | None"]):
    """Approve/reject ANY gate (codex-style selection pop-up). Returns (gate, approve) or None."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, blocked: str | None) -> None:
        super().__init__()
        self.blocked = blocked

    def compose(self) -> ComposeResult:
        yield Label("Resolve a gate:")
        with RadioSet(id="gatesel"):
            for g in GATES:
                yield RadioButton(g, value=(g == self.blocked), id=f"gate-{g}")
        with Horizontal(id="gatebtns"):
            yield Button("Approve", id="approve", variant="success")
            yield Button("Reject", id="reject", variant="error")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        rs = self.query_one("#gatesel", RadioSet)
        idx = rs.pressed_index if rs.pressed_index >= 0 else 0
        gate: GateName = GATES[idx]
        self.dismiss((gate, event.button.id == "approve"))


class TaskDetailScreen(ModalScreen[None]):
    """Drill-down for one task: contract YAML · result JSON · its claims · verdict."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, run: RunPaths, task_id: str) -> None:
        super().__init__()
        self.run = run
        self.task_id = task_id

    def compose(self) -> ComposeResult:
        view = load_report_view(self.run, strict=False)
        claims = [
            c
            for c in (*view.confirmed, *view.inferred, *view.contradicted, *view.unsupported)
            if c.task_id == self.task_id
        ]
        verdict = view.verdict_by_task_id.get(self.task_id)
        with TabbedContent(id="taskdetail"):
            with TabPane("Contract", id="td-contract"), VerticalScroll():
                yield Static(widgets.render_file(self.run.tasks / f"{self.task_id}.yaml"))
            with TabPane("Result", id="td-result"), VerticalScroll():
                yield Static(widgets.render_file(self.run.result_path(self.task_id)))
            with TabPane("Claims", id="td-claims"), VerticalScroll():
                body = (
                    "\n".join(f"[{c.status}] {c.claim_id}  {c.claim}" for c in claims)
                    or "(no claims)"
                )
                yield Static(body, markup=False)  # claim text may contain [..]; render literally
            with TabPane("Verdict", id="td-verdict"), VerticalScroll():
                text = (
                    f"{verdict.verdict}\n  " + "\n  ".join(verdict.reasons)
                    if verdict
                    else "(no verdict yet)"
                )
                yield Static(text, markup=False)
        yield Footer()


class ClaimDetailScreen(ModalScreen[None]):
    """Drill-down for one claim — the full claim JSON (mirrors `siftmesh claims show`)."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, run: RunPaths, claim_id: str) -> None:
        super().__init__()
        self.run = run
        self.claim_id = claim_id

    def compose(self) -> ComposeResult:
        view = load_report_view(self.run, strict=False)
        found = next(
            (
                c
                for c in (
                    *view.confirmed,
                    *view.inferred,
                    *view.contradicted,
                    *view.unsupported,
                )
                if c.claim_id == self.claim_id
            ),
            None,
        )
        body = found.model_dump_json(indent=2) if found else f"claim {self.claim_id} not found"
        with VerticalScroll():
            yield Static(Syntax(body, "json", word_wrap=True, background_color="default"))
        yield Footer()


class ReplayScreen(ModalScreen[None]):
    """The deterministic text replay of the run (mirrors `siftmesh replay`)."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, run: RunPaths) -> None:
        super().__init__()
        self.run = run

    def compose(self) -> ComposeResult:
        try:
            text = render_text_replay(load_report_view(self.run, strict=False))
        except Exception as exc:  # never crash the cockpit over a replay render
            text = f"replay unavailable: {exc}"
        with VerticalScroll():
            yield Static(text, markup=False)  # replay text is plain; never parse as markup
        yield Footer()


def open_file_path(run: RunPaths, rel: str) -> Path:
    """Resolve a run-relative path for the file-open modal (read-only)."""
    return Path(run.root) / rel

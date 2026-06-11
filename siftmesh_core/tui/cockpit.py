"""The live run cockpit (Epic O redesign) — vitals + progress + pipeline + tabbed panels + nav.

A `set_interval` poll (main thread) rebuilds the tested `CockpitSnapshot` and pushes it into the
widgets; when the screen launched the run, a `@work(thread=True)` worker drives the deterministic
engine while the same poll renders its file writes. Read-only except the gate keys (a/r), which call
the governed `human_gate.set_gate` + resume. Presentation only — `build_snapshot` is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from rich.markdown import Markdown as RichMarkdown
from rich.syntax import Syntax
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    LoadingIndicator,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import RunMode
from siftmesh_core.tui import runner, widgets
from siftmesh_core.tui.snapshot import CockpitSnapshot, build_snapshot

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_NAV_DIRS = ("context", "tasks", "results", "claims", "audit", "reports", "evidence")


class CockpitScreen(Screen):
    """Live cockpit for one run. Attach mode (run_dir) or launch mode (launch_params)."""

    BINDINGS = [
        ("a", "approve", "Approve gate"),
        ("r", "reject", "Reject gate"),
        ("escape", "app.pop_screen", "Back"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        run_dir: Path | None,
        *,
        settings: SiftmeshSettings,
        launch_params: dict | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.run: RunPaths | None = RunPaths(root=Path(run_dir)) if run_dir else None
        self.launch_params = launch_params
        self._last_lineno = -1
        self._spin = 0
        self._nav_built = False
        self._snap: CockpitSnapshot | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="vitals")
        yield ProgressBar(id="taskbar", total=100, show_eta=False)
        yield Static(id="ribbon")
        yield LoadingIndicator(id="loading")
        with Horizontal(id="working"):
            yield DataTable(id="tasks", zebra_stripes=True, cursor_type="row")
            with TabbedContent(id="side"):
                with TabPane("Claims", id="tab-claims"):
                    yield Static(id="claims")
                with TabPane("Agents", id="tab-agents"):
                    yield Static(id="agents")
                with TabPane("Budget", id="tab-budget"):
                    yield Static(id="budget")
            with Vertical(id="navcol"):
                yield Tree("run dir", id="nav")
                with VerticalScroll(id="filescroll"):
                    yield Static(id="fileview")
        yield RichLog(id="ticker", max_lines=1000, markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tasks", DataTable)
        table.add_columns("task", "status", "att", "family", "agent", "clm", "verdict")
        table.tooltip = "task: status · attempt · artifact family · agent · claims · verdict"
        self.query_one("#nav", Tree).tooltip = "Select a run file to view (markdown/JSON rendered)"
        self.query_one("#taskbar", ProgressBar).tooltip = "Tasks completed / total"
        # Cache the honest agent safety tiers once (pure profile classification — no subprocess).
        try:
            from siftmesh_core.doctor import profile_safety_tiers

            self._tiers = profile_safety_tiers()
        except Exception:
            self._tiers = {}
        self._build_nav()
        if self.launch_params is not None:
            self._launch_run()
        self.set_interval(1.0, self._refresh)
        self._refresh()

    # ---- live launch (this screen owns the engine) ----
    @work(thread=True, exclusive=True)
    def _launch_run(self) -> None:
        p = self.launch_params or {}
        mode: RunMode = p.get("mode", "auto")
        try:
            run = runner.init_case_for_run(
                p["case_dir"],
                p["evidence"],
                mode=mode,
                settings=self.settings,
                max_iterations=p.get("max_iterations"),
                brief=p.get("brief"),
                objective=p.get("objective"),
            )
        except Exception as exc:  # surface, keep the UI alive
            self.app.call_from_thread(self.notify, f"init failed: {exc}", severity="error")
            return
        self.run = run
        runner.drive_engine(
            run,
            p["evidence"],
            mode=mode,
            settings=self.settings,
            on_error=lambda m: self.app.call_from_thread(self.notify, m, severity="error"),
        )

    @work(thread=True, exclusive=True)
    def _resume_engine(self) -> None:
        if self.run is None:
            return
        from siftmesh_core.orchestrator.workflow_runner import run_engine

        try:
            run_engine(self.run, settings=self.settings)
        except Exception as exc:  #
            self.app.call_from_thread(self.notify, f"resume failed: {exc}", severity="error")

    # ---- gate actions (governed) ----
    def action_approve(self) -> None:
        self._resolve_gate("approved")

    def action_reject(self) -> None:
        self._resolve_gate("rejected")

    def _resolve_gate(self, status: str) -> None:
        if self.run is None or self._snap is None or not self._snap.blocked_gate:
            self.notify("no blocked gate to resolve")
            return
        from siftmesh_core.orchestrator.human_gate import set_gate

        gate = self._snap.blocked_gate
        set_gate(self.run, gate, status)  # type: ignore[arg-type]
        self.notify(f"gate {gate} → {status}")
        if status == "approved":
            self._resume_engine()

    # ---- polling render ----
    def _refresh(self) -> None:
        loading = self.query_one("#loading", LoadingIndicator)
        snap = build_snapshot(self.run) if self.run is not None else None
        if snap is None or not snap.exists:
            loading.display = True
            self.query_one("#vitals", Static).update("[$accent]starting run…[/]")
            return
        loading.display = False
        if not self._nav_built:
            self._build_nav()  # the launched run dir now exists
        self._spin = (self._spin + 1) % len(_SPINNER)
        self._snap = snap
        self.title = f"SIFTMesh · {snap.run_id}"
        self.query_one("#vitals", Static).update(
            widgets.vitals_text(snap, spinner=_SPINNER[self._spin])
        )
        bar = self.query_one("#taskbar", ProgressBar)
        bar.update(total=max(snap.tasks_total, 1), progress=snap.tasks_done)
        self.query_one("#ribbon", Static).update(widgets.ribbon_text(snap))
        self.query_one("#claims", Static).update(widgets.claims_text(snap))
        self.query_one("#agents", Static).update(
            widgets.agents_text(snap, getattr(self, "_tiers", {}))
        )
        self.query_one("#budget", Static).update(widgets.budget_text(snap))
        self._sync_tasks(snap)
        self._sync_ticker(snap)

    def _sync_tasks(self, snap: CockpitSnapshot) -> None:
        table = self.query_one("#tasks", DataTable)
        table.clear()
        for t in snap.tasks:
            table.add_row(
                t.task_id,
                widgets.status_cell(t.status),
                f"{t.attempt}/{t.max_attempts}",
                t.family,
                t.agent,
                str(t.claims),
                t.verdict,
                key=t.task_id,
            )

    def _sync_ticker(self, snap: CockpitSnapshot) -> None:
        log = self.query_one("#ticker", RichLog)
        for ev in snap.events:
            if ev.lineno > self._last_lineno:
                log.write(f"[dim]{ev.timestamp}[/] {ev.summary}")
                self._last_lineno = ev.lineno

    # ---- navigation tree ----
    def _build_nav(self) -> None:
        tree = self.query_one("#nav", Tree)
        tree.root.expand()
        if self.run is None:
            return
        root = Path(self.run.root)
        for sub in _NAV_DIRS:
            d = root / sub
            if not d.is_dir():
                continue
            branch = tree.root.add(sub)
            for f in sorted(d.glob("*")):
                if f.is_file():
                    branch.add_leaf(f.name, data=f)
        self._nav_built = True

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        view = self.query_one("#fileview", Static)
        if not isinstance(data, Path) or not data.is_file():
            return
        try:
            text = data.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            view.update(f"[$error]cannot read {data.name}: {exc}[/]")
            return
        clipped = text if len(text) <= 20000 else text[:20000] + "\n… (truncated)"
        suffix = data.suffix.lower()
        if suffix in (".md", ".markdown"):
            view.update(RichMarkdown(clipped))
        elif suffix in (".json", ".jsonl"):
            view.update(Syntax(clipped, "json", word_wrap=True, background_color="default"))
        elif suffix in (".yaml", ".yml"):
            view.update(Syntax(clipped, "yaml", word_wrap=True, background_color="default"))
        else:
            view.update(clipped)

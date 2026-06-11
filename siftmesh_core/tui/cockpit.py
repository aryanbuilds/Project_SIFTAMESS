"""The live run cockpit (Epic O redesign) — vitals + progress + pipeline + tabbed panels + nav.

A `set_interval` poll (main thread) rebuilds the tested `CockpitSnapshot` and pushes it into the
widgets; when the screen launched the run, a `@work(thread=True)` worker drives the deterministic
engine while the same poll renders its file writes. Read-only except the gate keys (a/r), which call
the governed `human_gate.set_gate` + resume. Presentation only — `build_snapshot` is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    LoadingIndicator,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.run import GateName, RunMode
from siftmesh_core.tui import runner, widgets
from siftmesh_core.tui.snapshot import CockpitSnapshot, build_snapshot

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_NAV_DIRS = ("context", "tasks", "results", "claims", "audit", "reports", "evidence")
_LEDGERS = ("events", "tool-calls", "agent-calls", "retries", "token-budget")


class CockpitScreen(Screen):
    """Live cockpit for one run. Attach mode (run_dir) or launch mode (launch_params)."""

    BINDINGS = [
        ("a", "approve", "Approve gate"),
        ("r", "reject", "Reject gate"),
        ("g", "gate_selector", "Gate…"),
        ("t", "retry_task", "Retry task"),
        ("R", "resume", "Resume/step"),
        ("P", "pause", "Pause"),
        ("p", "replay", "Replay"),
        ("s", "switch_run", "Switch run"),
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
        self._filter = ""
        self._ticker_ledger = "events"
        self._console_offsets: dict[str, int] = {}  # agent_raw.json path -> bytes already shown
        import threading

        self._stop_event = threading.Event()  # cooperative pause flag for the engine worker

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="vitals")
        yield ProgressBar(id="taskbar", total=100, show_eta=False)
        yield Static(id="ribbon")
        with Horizontal(id="controls"):
            yield Input(placeholder="filter tasks…", id="taskfilter")
            yield Select.from_values(_LEDGERS, value="events", id="ledgersel", allow_blank=False)
        yield LoadingIndicator(id="loading")
        with Horizontal(id="working"):
            yield DataTable(id="tasks", zebra_stripes=True, cursor_type="row")
            with TabbedContent(id="side"):
                with TabPane("Claims", id="tab-claims"):
                    yield Static(id="claims")
                with TabPane("Claim list", id="tab-claimlist"):
                    yield DataTable(id="claimlist", zebra_stripes=True, cursor_type="row")
                with TabPane("Agents", id="tab-agents"):
                    yield Static(id="agents")
                with TabPane("Budget", id="tab-budget"):
                    yield Static(id="budget")
                with TabPane("Console", id="tab-console"):
                    yield RichLog(id="console", max_lines=2000, markup=False, highlight=False)
            with Vertical(id="navcol"):
                yield Tree("run dir", id="nav")
                with VerticalScroll(id="filescroll"):
                    yield Static(id="fileview")
        yield RichLog(id="ticker", max_lines=1000, markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tasks", DataTable)
        table.add_columns("task", "status", "att", "family", "agent", "clm", "verdict")
        table.tooltip = (
            "task: status · attempt · artifact family · agent · claims · verdict (↵ details)"
        )
        claimlist = self.query_one("#claimlist", DataTable)
        claimlist.add_columns("claim", "status", "conf", "task", "artifact")
        claimlist.tooltip = "↵ to view the full claim JSON"
        self.query_one("#taskfilter", Input).tooltip = "filter tasks by id / family / status"
        self.query_one("#ledgersel", Select).tooltip = "which audit ledger the ticker shows"
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
            should_stop=self._stop_event.is_set,
        )

    @work(thread=True, exclusive=True)
    def _resume_engine(self) -> None:
        if self.run is None:
            return
        from siftmesh_core.orchestrator.workflow_runner import run_engine

        # Manual mode = exactly one transition per resume (matches `siftmesh resume`).
        single = (self._snap.mode if self._snap else "") == "manual"
        try:
            run_engine(
                self.run,
                settings=self.settings,
                single_step=single,
                should_stop=self._stop_event.is_set,
            )
        except Exception as exc:
            self.app.call_from_thread(self.notify, f"resume failed: {exc}", severity="error")

    # ---- gate actions (governed) ----
    def action_approve(self) -> None:
        self._quick_gate(True)

    def action_reject(self) -> None:
        self._quick_gate(False)

    def _quick_gate(self, approve: bool) -> None:
        """a/r shortcut: resolve the currently-blocked gate."""
        from typing import cast

        if self.run is None or self._snap is None or not self._snap.blocked_gate:
            self.notify("no blocked gate to resolve")
            return
        self._do_gate(cast(GateName, self._snap.blocked_gate), approve)

    def action_gate_selector(self) -> None:
        """g: choose ANY gate to approve/reject (codex-style pop-up)."""
        if self.run is None:
            return
        from siftmesh_core.tui.modals import GateScreen

        blocked = self._snap.blocked_gate if self._snap else None

        def _done(result: tuple[GateName, bool] | None) -> None:
            if result is not None:
                gate, approve = result
                self._do_gate(gate, approve)

        self.app.push_screen(GateScreen(blocked), _done)

    def _do_gate(self, gate: GateName, approve: bool) -> None:
        self._gate_worker(gate, approve)

    @work(thread=True, exclusive=True)
    def _gate_worker(self, gate: GateName, approve: bool) -> None:
        from siftmesh_core.tui import actions

        if self.run is None:
            return
        res = actions.resolve_gate(self.run, gate, approve=approve, settings=self.settings)
        self.app.call_from_thread(
            self.notify, res.message, severity="information" if res.ok else "error"
        )

    # ---- retry / resume / replay / switch ----
    def action_retry_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            self.notify("select a task row to retry")
            return
        self.notify(f"retrying {task_id}…")
        self._retry_worker(task_id)

    @work(thread=True, exclusive=True)
    def _retry_worker(self, task_id: str) -> None:
        from siftmesh_core.tui import actions

        if self.run is None:
            return
        res = actions.retry_task(self.run, task_id, settings=self.settings)
        self.app.call_from_thread(
            self.notify, res.message, severity="information" if res.ok else "warning"
        )

    def action_resume(self) -> None:
        if self.run is None or (self._snap and self._snap.terminal):
            self.notify("nothing to resume")
            return
        self._stop_event.clear()  # un-pause before re-driving
        self.notify("resuming…")
        self._resume_engine()

    def action_pause(self) -> None:
        """Request a cooperative pause — the engine stops at the next safe checkpoint (durable)."""
        if self.run is None or (self._snap and self._snap.terminal):
            self.notify("nothing to pause")
            return
        self._stop_event.set()
        self.notify("pausing at the next safe checkpoint… (R to resume)")

    def action_replay(self) -> None:
        if self.run is None:
            return
        from siftmesh_core.tui.modals import ReplayScreen

        self.app.push_screen(ReplayScreen(self.run))

    def action_switch_run(self) -> None:
        from siftmesh_core.tui.app import HomeScreen

        self.app.push_screen(HomeScreen(settings=self.settings))

    def _selected_task(self) -> str | None:
        from textual.coordinate import Coordinate

        table = self.query_one("#tasks", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key
            return str(row_key.value)
        except Exception:
            return None

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
        self._sync_claimlist(snap)
        self._sync_ticker(snap)
        self._sync_console()

    def _sync_tasks(self, snap: CockpitSnapshot) -> None:
        table = self.query_one("#tasks", DataTable)
        table.clear()
        flt = self._filter.lower()
        for t in snap.tasks:
            if flt and flt not in f"{t.task_id} {t.family} {t.status}".lower():
                continue
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

    def _sync_claimlist(self, snap: CockpitSnapshot) -> None:
        table = self.query_one("#claimlist", DataTable)
        table.clear()
        for c in snap.claims:
            table.add_row(
                c.claim_id,
                widgets.status_cell(c.status),
                f"{c.confidence:.2f}",
                c.task_id,
                c.source_artifact,
                key=c.claim_id,
            )

    def _sync_ticker(self, snap: CockpitSnapshot) -> None:
        log = self.query_one("#ticker", RichLog)
        rows = snap.ledger_lines.get(self._ticker_ledger, snap.events)
        for ev in rows:
            if ev.lineno > self._last_lineno:
                log.write(f"[dim]{ev.timestamp}[/] {ev.summary}")
                self._last_lineno = ev.lineno

    def _sync_console(self) -> None:
        """Tail the live agent's persisted stdout (results/*.agent_raw.json) by byte offset.

        Read-only file tailing — NOT a live subprocess stream (which would need core plumbing). The
        claude adapter already persists each agent's raw envelope; this surfaces it incrementally.
        """
        if self.run is None:
            return
        log = self.query_one("#console", RichLog)
        for path in sorted(self.run.results.glob("*.agent_raw.json")):
            key = path.name
            try:
                data = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            shown = self._console_offsets.get(key, 0)
            if len(data) > shown:
                log.write(f"── {key} ──")
                log.write(data[shown:])
                self._console_offsets[key] = len(data)

    # ---- interactive handlers ----
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self.run is None:
            return
        from siftmesh_core.tui.modals import ClaimDetailScreen, TaskDetailScreen

        key = str(event.row_key.value) if event.row_key else ""
        if event.data_table.id == "tasks" and key:
            self.app.push_screen(TaskDetailScreen(self.run, key))
        elif event.data_table.id == "claimlist" and key:
            self.app.push_screen(ClaimDetailScreen(self.run, key))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "taskfilter":
            self._filter = event.value
            if self._snap is not None:
                self._sync_tasks(self._snap)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "ledgersel" and event.value is not None:
            self._ticker_ledger = str(event.value)
            self.query_one("#ticker", RichLog).clear()
            self._last_lineno = -1  # repaint the chosen ledger from the top

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
        view.update(widgets.render_file(data))

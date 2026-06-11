"""New-investigation wizard (Epic C+) — a stepped TUI flow that wires the existing core fns.

Project → Evidence (DirectoryTree browse → add files/folders → curated hardlink dir) → Brief →
Verify+Space synthesis (options) → Toggles → Launch. The load-bearing, Textual-FREE unit is
``WizardDraft`` (every step reads/writes it; ``build_settings`` is the single source the legacy
``NewRunScreen`` also delegates to), so step logic is unit-tested without a terminal. Screens are
thin renderers; heavy work (curate, readiness) runs in ``@work`` threads. No orchestration here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RadioButton,
    RadioSet,
    Select,
    Static,
)

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.schemas.run import RunMode

_MODES = ("manual", "review_only", "auto_human_loop", "auto")
_JUDGE_CHOICES = [
    ("(persisted default)", ""),
    ("Tier-1 only", "none"),
    ("claude", "cli:claude"),
    ("gemini", "cli:gemini"),
    ("codex", "cli:codex"),
    ("opencode", "cli:opencode"),
]
_MODEL_AGENTS = ("claude", "gemini", "codex", "opencode")


@dataclass
class WizardDraft:
    """All wizard state (Textual-free) — the single source of truth shared across steps."""

    case_name: str = ""
    base_dir: str = "."
    save_scope: str = "none"  # none | global | project
    selected_paths: list[Path] = field(default_factory=list)
    curated_root: str | None = None
    brief_path: str | None = None
    objective: str | None = None
    mode: RunMode = "auto"
    agent: str = "deterministic"  # friendly name or "deterministic"
    judge: str = ""  # "" keep persisted · "none" off · "cli:<agent>"
    max_iterations: str = ""
    max_agent_tasks: str = ""
    models: dict[str, str] = field(default_factory=dict)  # friendly name -> model id
    parallel: bool = False
    all_live: bool = False
    force: bool = False
    run_style: str = "full"  # full | single | portions
    portion_plan: list[list[object]] = field(default_factory=list)

    @property
    def case_dir(self) -> str:
        return str(Path(self.base_dir) / self.case_name) if self.case_name else self.base_dir

    def add_path(self, p: Path) -> bool:
        """Add a selected file/folder (de-duped). Returns False if already present."""
        rp = Path(p)
        if rp in self.selected_paths:
            return False
        self.selected_paths.append(rp)
        return True

    def remove_path(self, p: Path) -> None:
        self.selected_paths = [x for x in self.selected_paths if x != Path(p)]

    def build_settings(self) -> tuple[SiftmeshSettings, int | None]:
        """Apply the per-run overrides via the SAME CLI helpers (as NewRunScreen._build_settings).

        Returns ``(settings, max_iterations|None)``.
        """
        from siftmesh_core.cli import _agent_overrides, _judge_overrides
        from siftmesh_core.config import load_settings

        overrides = dict(_agent_overrides(None if self.agent == "deterministic" else self.agent))
        if self.judge:
            overrides.update(_judge_overrides("off" if self.judge == "none" else self.judge))
        settings = load_settings(**overrides)

        models = {f"{name}_headless": v for name, v in self.models.items() if v}
        if models:
            settings = settings.model_copy(
                update={"agent_models": {**settings.agent_models, **models}}
            )
        if self.max_agent_tasks.isdigit():
            settings = settings.model_copy(
                update={
                    "caps": settings.caps.model_copy(
                        update={"max_agent_tasks": int(self.max_agent_tasks)}
                    )
                }
            )
        if self.parallel:
            settings = settings.model_copy(update={"parallel_dispatch": True})
        if self.all_live:
            settings = settings.model_copy(update={"live_extraction": True})
        mi = self.max_iterations
        return settings, (int(mi) if mi.isdigit() else None)


# ── Step 1: project / case ──────────────────────────────────────────────────


class Step1ProjectScreen(Screen):
    """Name the case + base dir + optional config scope."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft or WizardDraft()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="newrun"):
            yield Static("New investigation — Step 1/6: Project", id="wizstep")
            yield Label("Case name")
            yield Input(value=self.draft.case_name, placeholder="case_rocba", id="case")
            yield Label("Base directory")
            yield Input(value=self.draft.base_dir, placeholder=".", id="base")
            yield Label("Save agent config to:")
            with RadioSet(id="scope"):
                yield RadioButton("don't save", value=True, id="scope-none")
                yield RadioButton("global (~/.config)", id="scope-global")
                yield RadioButton("project (./siftmesh.toml)", id="scope-project")
            yield Button("Next: evidence →", id="next", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        self.draft.case_name = self.query_one("#case", Input).value.strip()
        self.draft.base_dir = self.query_one("#base", Input).value.strip() or "."
        if not self.draft.case_name:
            self.notify("a case name is required", severity="error")
            return
        idx = self.query_one("#scope", RadioSet).pressed_index
        self.draft.save_scope = ("none", "global", "project")[idx if idx >= 0 else 0]
        self.app.push_screen(Step2EvidenceScreen(settings=self.settings, draft=self.draft))


# ── Step 2: evidence picker (DirectoryTree → add-to-list → curate) ───────────


class Step2EvidenceScreen(Screen):
    """Browse the filesystem; add files/folders to the selected list; curate on Next."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft
        self._current: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Step 2/6: Evidence — browse, Add files/folders, then Next", id="wizstep")
        with Horizontal(id="pickrow"):
            yield DirectoryTree(str(Path(self.draft.base_dir).expanduser().resolve()), id="fstree")
            with Vertical(id="pickedcol"):
                yield Label("Selected evidence:")
                yield ListView(id="picked")
                with Horizontal(id="pickbtns"):
                    yield Button("Add", id="add", variant="success")
                    yield Button("Remove", id="remove")
        yield Static(id="pickstatus")
        yield Button("Next: brief →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_picked()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._current = Path(event.path)

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._current = Path(event.path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            if self._current is None:
                self.notify("select a file or folder in the tree first")
                return
            if self.draft.add_path(self._current):
                self._sync_picked()
            else:
                self.notify("already selected")
        elif event.button.id == "remove":
            lv = self.query_one("#picked", ListView)
            i = lv.index
            if i is not None and 0 <= i < len(self.draft.selected_paths):
                self.draft.remove_path(self.draft.selected_paths[i])
                self._sync_picked()
        elif event.button.id == "next":
            self._curate_and_advance()

    def _sync_picked(self) -> None:
        lv = self.query_one("#picked", ListView)
        lv.clear()
        for p in self.draft.selected_paths:
            lv.append(ListItem(Label(str(p))))
        self.query_one("#pickstatus", Static).update(
            f"{len(self.draft.selected_paths)} item(s) selected"
        )

    def _curate_and_advance(self) -> None:
        if not self.draft.selected_paths:
            self.notify("add at least one file or folder", severity="error")
            return
        self.query_one("#pickstatus", Static).update("curating evidence (hardlinks)…")
        self._curate()

    @work(thread=True, exclusive=True)
    def _curate(self) -> None:
        from siftmesh_core.evidence.curate import CurateError, curate_evidence

        dest = Path(self.draft.case_dir) / "curated_evidence"
        try:
            root = curate_evidence(self.draft.selected_paths, dest)
        except CurateError as exc:
            self.app.call_from_thread(self.notify, f"curate failed: {exc}", severity="error")
            return
        self.draft.curated_root = str(root)
        self.app.call_from_thread(
            self.app.push_screen, Step3BriefScreen(settings=self.settings, draft=self.draft)
        )


# ── Step 3: brief / objective ───────────────────────────────────────────────


class Step3BriefScreen(Screen):
    """Incident brief file OR inline objective text (mutually exclusive)."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="newrun"):
            yield Static(
                "Step 3/6: Brief — a TRUSTED objective (file or inline text)", id="wizstep"
            )
            yield Label("Brief file (.pptx/.docx/.pdf/.txt/.md) — or leave blank")
            yield Input(
                value=self.draft.brief_path or "", placeholder="…/BACKGROUND.pptx", id="brief"
            )
            yield Label("…or inline objective text")
            yield Input(
                value=self.draft.objective or "",
                placeholder="was host X compromised? find initial access",
                id="objective",
            )
            yield Button("Next: verify + space →", id="next", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        brief = self.query_one("#brief", Input).value.strip() or None
        objective = self.query_one("#objective", Input).value.strip() or None
        if brief and objective:
            self.notify("give a brief OR an objective, not both", severity="error")
            return
        self.draft.brief_path = brief
        self.draft.objective = objective
        self.app.push_screen(Step4VerifyScreen(settings=self.settings, draft=self.draft))


# ── Step 4: verify + space synthesis ────────────────────────────────────────


class Step4VerifyScreen(Screen):
    """Host verification + disk-space estimate → recommendation + options."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Step 4/6: Verify host + space", id="wizstep")
        yield LoadingIndicator(id="vloading")
        with VerticalScroll(id="vbody"):
            yield Static(id="vreport")
        with Horizontal(id="vbtns"):
            yield Button("Full (parallel)", id="opt-full", variant="success")
            yield Button("Single op + report", id="opt-single")
            yield Button("Run in portions", id="opt-portions", variant="warning")
        yield Footer()

    def on_mount(self) -> None:
        self._build()

    @work(thread=True, exclusive=True)
    def _build(self) -> None:
        from siftmesh_core.tui.space_view import build_readiness

        ev = self.draft.curated_root or self.draft.base_dir
        report = build_readiness(ev, run_location=self.draft.case_dir, settings=self.settings)
        self.app.call_from_thread(self._render_report, report)

    def _render_report(self, report: object) -> None:
        from siftmesh_core.tui.space_view import ReadinessReport

        assert isinstance(report, ReadinessReport)
        self._report = report
        self.query_one("#vloading", LoadingIndicator).display = False
        lines = [
            f"checks: {report.checks_ok} ok · {report.checks_warn} warn · "
            f"{report.checks_fail} fail",
            f"agent default: {report.agents.chosen}"
            + (
                f" · live ready: {report.agents.live_candidate}"
                if report.agents.live_candidate
                else ""
            ),
            f"space: needs ~{report.needed_human} · free {report.free_human} · "
            + ("FITS" if report.fits else "WON'T FIT"),
            "",
            f"recommendation: {report.recommendation.upper()}",
        ]
        if report.blocking:
            lines.append("[$error]host has FAIL checks — fix before running (see doctor).[/]")
        if not report.fits:
            lines.append("")
            lines.append(f"portions plan: {len(report.portions)} portion(s)")
            for i, portion in enumerate(report.portions, 1):
                names = ", ".join(Path(str(it.path)).name for it in portion)
                lines.append(f"  portion {i}: {names}")
        self.query_one("#vreport", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        report = getattr(self, "_report", None)
        if report is None:
            self.notify("still verifying…")
            return
        if event.button.id == "opt-full":
            self.draft.run_style, self.draft.parallel = "full", True
        elif event.button.id == "opt-single":
            self.draft.run_style, self.draft.parallel = "single", False
        elif event.button.id == "opt-portions":
            self.draft.run_style = "portions"
            self.draft.portion_plan = [list(p) for p in report.portions]
            self.draft.force = True  # proceeding despite the shortfall (operator chose portions)
        else:
            return
        self.app.push_screen(Step5OptionsScreen(settings=self.settings, draft=self.draft))


# ── Step 5: toggles ─────────────────────────────────────────────────────────


class Step5OptionsScreen(Screen):
    """Final knobs — mode/agent/judge/caps/models + parallel/all-live."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft

    def compose(self) -> ComposeResult:
        agents = [p for p in self.settings.agent_preference if p != "deterministic_executor"]
        agent_opts = [("deterministic (floor)", "deterministic")] + [
            (p.removesuffix("_headless"), p.removesuffix("_headless")) for p in agents
        ]
        yield Header()
        with VerticalScroll(id="newrun"):
            yield Static("Step 5/6: Options", id="wizstep")
            yield Label("Mode")
            yield Select(
                [(m, m) for m in _MODES], value=self.draft.mode, id="mode", allow_blank=False
            )
            yield Label("Agent")
            yield Select(agent_opts, value=self.draft.agent, id="agent", allow_blank=False)
            yield Label("Tier-2 judge")
            yield Select(_JUDGE_CHOICES, value=self.draft.judge, id="judge", allow_blank=False)
            yield Label("max iterations / max agent tasks (blank = default)")
            yield Input(value=self.draft.max_iterations, placeholder="3", id="max-iterations")
            yield Input(value=self.draft.max_agent_tasks, placeholder="10", id="max-agent-tasks")
            for name in _MODEL_AGENTS:
                yield Input(
                    value=self.draft.models.get(name, ""),
                    placeholder=f"{name} model (blank = default)",
                    id=f"model-{name}",
                )
            yield Checkbox("Parallel dispatch", value=self.draft.parallel, id="cb-parallel")
            yield Checkbox(
                "All-live (heavy tools on the agent)", value=self.draft.all_live, id="cb-alllive"
            )
            yield Button("Next: launch →", id="next", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        self.draft.mode = str(self.query_one("#mode", Select).value)  # type: ignore[assignment]
        self.draft.agent = str(self.query_one("#agent", Select).value)
        self.draft.judge = str(self.query_one("#judge", Select).value)
        self.draft.max_iterations = self.query_one("#max-iterations", Input).value.strip()
        self.draft.max_agent_tasks = self.query_one("#max-agent-tasks", Input).value.strip()
        self.draft.models = {
            name: self.query_one(f"#model-{name}", Input).value.strip() for name in _MODEL_AGENTS
        }
        self.draft.parallel = self.query_one("#cb-parallel", Checkbox).value
        self.draft.all_live = self.query_one("#cb-alllive", Checkbox).value
        self.app.push_screen(Step6LaunchScreen(settings=self.settings, draft=self.draft))


# ── Step 6: launch ──────────────────────────────────────────────────────────


class Step6LaunchScreen(Screen):
    """Summary + launch (normal → cockpit; portions → orchestrated run)."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft

    def compose(self) -> ComposeResult:
        d = self.draft
        yield Header()
        with Vertical(id="newrun"):
            yield Static("Step 6/6: Launch", id="wizstep")
            yield Static(
                f"case: {d.case_dir}\nevidence: {d.curated_root}\n"
                f"brief: {d.brief_path or d.objective or '(none)'}\n"
                f"mode: {d.mode} · agent: {d.agent} · style: {d.run_style} · "
                f"parallel: {d.parallel}",
                id="summary",
            )
            yield Button("Launch", id="launch", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "launch":
            return
        if self.draft.save_scope in ("global", "project"):
            self._persist_scope()
        settings, max_iterations = self.draft.build_settings()
        from siftmesh_core.tui.cockpit import CockpitScreen

        if self.draft.run_style == "portions" and self.draft.portion_plan:
            cockpit = CockpitScreen(None, settings=settings)
            cockpit.portions_params = {
                "case_dir": self.draft.case_dir,
                "portion_plan": self.draft.portion_plan,
                "evidence_root": self.draft.curated_root,
                "mode": self.draft.mode,
                "brief": self.draft.brief_path,
                "objective": self.draft.objective,
            }
            self.app.switch_screen(cockpit)
            return
        params = {
            "case_dir": self.draft.case_dir,
            "evidence": self.draft.curated_root,
            "objective": self.draft.objective,
            "brief": self.draft.brief_path,
            "mode": self.draft.mode,
            "max_iterations": max_iterations,
        }
        self.app.switch_screen(CockpitScreen(None, settings=settings, launch_params=params))

    def _persist_scope(self) -> None:
        from siftmesh_core.config import save_agent_selection

        try:
            save_agent_selection(
                self.settings.executor_selection,
                self.settings.agent_preference,
                scope=self.draft.save_scope,  # type: ignore[arg-type]
            )
        except Exception as exc:
            self.notify(f"config save failed: {exc}", severity="warning")

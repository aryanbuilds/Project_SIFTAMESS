"""New-investigation wizard (hybrid 2-screen flow) - thin wiring over the governed engine.

Screen 1 ``RunSetupScreen``: name the case + **browse the whole filesystem** for evidence (a
re-rootable ``DirectoryTree`` reachable ABOVE the project dir + a ``#file`` / ``#folder`` fuzzy
search box, with the picked list beside it) + the brief/objective. Screen 2 ``RunLaunchScreen``:
host/space synthesis + the run options + Launch. The load-bearing, Textual-FREE unit is
``WizardDraft`` (every screen reads/writes it; ``build_settings`` is the single source the legacy
``NewRunScreen`` also delegates to). Screens are thin renderers; heavy work (curate, readiness,
fuzzy search) runs in ``@work`` threads. Launch routes through ``CockpitScreen`` as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    OptionList,
    RadioButton,
    RadioSet,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.schemas.run import RunMode

_MODES = ("manual", "review_only", "auto_human_loop", "auto")
# Run-type choices shown as a labelled RadioSet (clearer than a bare dropdown). Order == _MODES.
_MODE_LABELS = (
    ("manual", "manual - one step per action"),
    ("review_only", "review-only - plan, then stop"),
    ("auto_human_loop", "auto + human gates"),
    ("auto", "auto - run end to end"),
)
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
    """All wizard state (Textual-free) - the single source of truth shared across steps."""

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


def resolve_brief_path(text: str, browse_root: str | Path) -> str | None:
    """Resolve a brief reference to an existing ABSOLUTE file path, or None if not found.

    Accepts an absolute path, a ``~`` path, or a bare filename / relative path (tried under the
    browse root first, then the cwd). The run needs the brief's full path - a bare filename would
    otherwise resolve against the wrong dir and the brief intake would fail closed.
    """
    p = Path(text).expanduser()
    candidates = [p] if p.is_absolute() else [p, Path(browse_root) / p, Path.cwd() / p]
    for c in candidates:
        try:
            resolved = c.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return str(resolved)
    return None


# ── Screen 1: setup (case + filesystem-wide evidence picker + brief) ──────────


class RunSetupScreen(Screen):
    """Name the case, browse the whole filesystem for evidence, give the brief; then curate."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("up", "go_up", "Up dir"),
        ("ctrl+f", "focus_search", "Search"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft or WizardDraft()
        self._current: Path | None = None
        self._hits: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("New investigation - Setup (1/2): case · evidence · brief", id="wizstep")
        with Horizontal(id="idrow"):
            yield Input(
                value=self.draft.case_name, placeholder="case name (e.g. case_rocba)", id="case"
            )
            yield Input(value=self.draft.base_dir, placeholder="runs base dir (.)", id="base")
        with Horizontal(id="navrow"):
            yield Input(value=str(Path.home()), placeholder="path to browse - Enter", id="evroot")
            yield Button("Up", id="up")
        with Horizontal(id="pickrow"):
            yield DirectoryTree(str(Path.home()), id="fstree")
            with Vertical(id="pickedcol"):
                yield Label("Selected evidence:")
                yield ListView(id="picked")
                with Horizontal(id="pickbtns"):
                    yield Button("Add", id="add", variant="success")
                    yield Button("Set brief", id="setbrief")
                    yield Button("Remove", id="remove")
        with Horizontal(id="searchrow"):
            yield Input(
                placeholder="#file <name>   or   #folder <name>   - Enter to search "
                "(then Add evidence or Set brief)",
                id="evsearch",
            )
        yield OptionList(id="evhits")
        yield Input(
            value=self.draft.brief_path or "",
            placeholder="brief file path (.pptx/.pdf/.md) - type a path, or pick + Set brief",
            id="brief",
        )
        yield Input(
            value=self.draft.objective or "",
            placeholder="inline objective / steering prompt (combines with the brief if both set)",
            id="objective",
        )
        yield Static(id="pickstatus", markup=False)
        yield Button("Next: options →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_picked()
        self.query_one("#evhits", OptionList).display = False  # appears only after a search

    # -- navigation / re-root --------------------------------------------------
    def _reroot(self, path: Path) -> None:
        tree = self.query_one("#fstree", DirectoryTree)
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            self.notify("cannot resolve that path", severity="error")
            return
        if not resolved.is_dir():
            self.notify("not a directory", severity="error")
            return
        tree.path = resolved  # path is a reactive in textual 8.2.7
        tree.reload()
        self.query_one("#evroot", Input).value = str(resolved)

    def action_go_up(self) -> None:
        cur = Path(self.query_one("#evroot", Input).value or str(Path.home()))
        self._reroot(cur.parent)

    def action_focus_search(self) -> None:
        self.query_one("#evsearch", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "evroot":
            self._reroot(Path(event.value))
        elif event.input.id == "evsearch":
            self._search(event.value)

    # -- tree selection → showcase --------------------------------------------
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._set_current(Path(event.path))

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._set_current(Path(event.path))

    def _set_current(self, path: Path) -> None:
        self._current = path

    # -- fuzzy search ----------------------------------------------------------
    def _search(self, raw: str) -> None:
        text = raw.strip()
        if not text:
            return
        mode = "both"
        if text.startswith("#file"):
            mode, query = "file", text[len("#file") :].strip()
        elif text.startswith("#folder"):
            mode, query = "folder", text[len("#folder") :].strip()
        else:
            query = text.lstrip("#").strip()
        if not query:
            self.notify("type a name after #file / #folder")
            return
        root = self.query_one("#evroot", Input).value or str(Path.home())
        self.query_one("#pickstatus", Static).update(f"searching '{query}' under {root}…")
        self._run_search(query, root, mode)

    @work(thread=True, exclusive=True)
    def _run_search(self, query: str, root: str, mode: str) -> None:
        from siftmesh_core.tui.fs_search import fuzzy_find

        hits = fuzzy_find(query, root=root, mode=mode)  # type: ignore[arg-type]
        self.app.call_from_thread(self._show_hits, query, hits)

    def _show_hits(self, query: str, hits: list[Path]) -> None:
        from textual.fuzzy import Matcher

        self._hits = hits
        optlist = self.query_one("#evhits", OptionList)
        optlist.display = True  # reveal the results pane now that we have hits
        optlist.clear_options()
        matcher = Matcher(query)
        for i, p in enumerate(hits):
            optlist.add_option(Option(matcher.highlight(str(p)), id=str(i)))
        self.query_one("#pickstatus", Static).update(
            f"{len(hits)} match(es) for '{query}' - Enter on one to add"
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._add_hit(event.option_index)

    def _add_hit(self, idx: int) -> None:
        """Add the idx-th fuzzy hit to the picked list (Enter on a result)."""
        if not (0 <= idx < len(self._hits)):
            return
        hit = self._hits[idx]
        self._set_current(hit)
        if self.draft.add_path(hit):
            self._sync_picked()
            self.notify(f"added {hit.name}")
        else:
            self.notify("already selected")

    # -- picked list -----------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "up":
            self.action_go_up()
        elif bid == "add":
            if self._current is None:
                self.notify("select a file/folder in the tree, or search with #file / #folder")
                return
            if self.draft.add_path(self._current):
                self._sync_picked()
                kind = "folder" if self._current.is_dir() else "file"
                self.notify(f"added {kind}: {self._current.name}")
            else:
                self.notify("already selected")
        elif bid == "setbrief":
            self._set_brief()
        elif bid == "remove":
            lv = self.query_one("#picked", ListView)
            i = lv.index
            if i is not None and 0 <= i < len(self.draft.selected_paths):
                self.draft.remove_path(self.draft.selected_paths[i])
                self._sync_picked()
        elif bid == "next":
            self._next()

    def _set_brief(self) -> None:
        """Mark the current tree/fuzzy selection as the brief (full path); brief is not evidence."""
        if self._current is None:
            self.notify(
                "pick a file in the tree or via #file search, then Set brief", severity="warning"
            )
            return
        if not self._current.is_file():
            self.notify("the brief must be a file", severity="error")
            return
        abs_path = self._current.expanduser().resolve()
        self.draft.remove_path(self._current)  # a brief is the trusted objective, never evidence
        self.draft.remove_path(abs_path)
        self._sync_picked()
        self.draft.brief_path = str(abs_path)
        self.query_one("#brief", Input).value = str(abs_path)  # show the full resolved path
        self.notify(f"brief set: {abs_path.name}")

    def _sync_picked(self) -> None:
        lv = self.query_one("#picked", ListView)
        lv.clear()
        for p in self.draft.selected_paths:
            lv.append(ListItem(Label(str(p))))
        self.query_one("#pickstatus", Static).update(
            f"{len(self.draft.selected_paths)} item(s) selected"
        )

    # -- advance: validate + curate -------------------------------------------
    def _next(self) -> None:
        self.draft.case_name = self.query_one("#case", Input).value.strip()
        self.draft.base_dir = self.query_one("#base", Input).value.strip() or "."
        if not self.draft.case_name:
            self.notify("a case name is required", severity="error")
            return
        if not self.draft.selected_paths:
            self.notify("add at least one file or folder", severity="error")
            return
        brief_text = self.query_one("#brief", Input).value.strip() or None
        objective = self.query_one("#objective", Input).value.strip() or None
        # brief + objective COMBINE (file background + inline steering); both is allowed.
        brief_abs: str | None = None
        if brief_text:
            root = self.query_one("#evroot", Input).value or "."
            brief_abs = resolve_brief_path(brief_text, root)
            if brief_abs is None:
                self.notify(f"brief file not found: {brief_text}", severity="error")
                return
        self.draft.brief_path = brief_abs  # full resolved path (the run reads it by absolute path)
        self.draft.objective = objective
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
            self.app.push_screen, RunLaunchScreen(settings=self.settings, draft=self.draft)
        )


# ── Screen 2: launch (verify + space + options) ──────────────────────────────


class RunLaunchScreen(Screen):
    """Host/space synthesis + run options + Launch (normal → cockpit; portions → orchestrated)."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings, draft: WizardDraft) -> None:
        super().__init__()
        self.settings = settings
        self.draft = draft
        self._report: Any = None

    def compose(self) -> ComposeResult:
        agents = [p for p in self.settings.agent_preference if p != "deterministic_executor"]
        agent_opts = [("deterministic (floor)", "deterministic")] + [
            (p.removesuffix("_headless"), p.removesuffix("_headless")) for p in agents
        ]
        yield Header()
        yield Static("New investigation - Launch (2/2): verify · options", id="wizstep")
        yield LoadingIndicator(id="vloading")
        with VerticalScroll(id="newrun"):
            yield Static(id="vreport")
            yield Label("Run style")
            with RadioSet(id="runstyle"):
                yield RadioButton("Full (parallel)", value=True, id="rs-full")
                yield RadioButton("Single op + report", id="rs-single")
                yield RadioButton("Run in portions (low disk)", id="rs-portions")
            yield Label("Run type")
            with RadioSet(id="mode"):
                for m, label in _MODE_LABELS:
                    yield RadioButton(label, value=(m == self.draft.mode), id=f"mode-{m}")
            yield Label("Agent")
            yield Select(agent_opts, value=self.draft.agent, id="agent", allow_blank=False)
            yield Label("Tier-2 judge")
            yield Select(_JUDGE_CHOICES, value=self.draft.judge, id="judge", allow_blank=False)
            with Collapsible(title="Advanced - caps · models · save", collapsed=True):
                yield Label("max iterations / max agent tasks (blank = default)")
                yield Input(value=self.draft.max_iterations, placeholder="3", id="max-iterations")
                yield Input(
                    value=self.draft.max_agent_tasks, placeholder="10", id="max-agent-tasks"
                )
                for name in _MODEL_AGENTS:
                    yield Input(
                        value=self.draft.models.get(name, ""),
                        placeholder=f"{name} model (blank = default)",
                        id=f"model-{name}",
                    )
                yield Checkbox("Parallel dispatch", value=self.draft.parallel, id="cb-parallel")
                yield Checkbox(
                    "All-live (heavy tools on the agent)",
                    value=self.draft.all_live,
                    id="cb-alllive",
                )
                yield Label("Save agent config to:")
                with RadioSet(id="scope"):
                    yield RadioButton("don't save", value=True, id="scope-none")
                    yield RadioButton("global (~/.config)", id="scope-global")
                    yield RadioButton("project (./siftmesh.toml)", id="scope-project")
        yield Button("Launch", id="launch", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self._build()

    @work(thread=True, exclusive=True)
    def _build(self) -> None:
        from siftmesh_core.tui.space_view import build_readiness

        ev = self.draft.curated_root or self.draft.base_dir
        report = build_readiness(ev, run_location=self.draft.case_dir, settings=self.settings)
        self.app.call_from_thread(self._render_report, report)

    def _render_report(self, report: Any) -> None:
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
            f"recommendation: {report.recommendation.upper()}",
        ]
        if report.blocking:
            lines.append("host has FAIL checks - fix before running (see doctor).")
        if not report.fits:
            lines.append(f"portions plan: {len(report.portions)} portion(s)")
            for i, portion in enumerate(report.portions, 1):
                names = ", ".join(Path(str(it.path)).name for it in portion)
                lines.append(f"  portion {i}: {names}")
        self.query_one("#vreport", Static).update("\n".join(lines))
        # pre-select the recommended run style (RadioSet enforces exclusivity when one is set True)
        target = {"full": 0, "single": 1, "portions": 2}.get(report.recommendation, 0)
        buttons = list(self.query_one("#runstyle", RadioSet).query(RadioButton))
        if 0 <= target < len(buttons):
            buttons[target].value = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "launch":
            return
        if self._report is None:
            self.notify("still verifying host + space…")
            return
        self._collect()
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

    def _collect(self) -> None:
        d = self.draft
        mode_idx = self.query_one("#mode", RadioSet).pressed_index
        d.mode = _MODES[mode_idx] if 0 <= mode_idx < len(_MODES) else "auto"  # type: ignore[assignment]
        d.agent = str(self.query_one("#agent", Select).value)
        d.judge = str(self.query_one("#judge", Select).value)
        d.max_iterations = self.query_one("#max-iterations", Input).value.strip()
        d.max_agent_tasks = self.query_one("#max-agent-tasks", Input).value.strip()
        d.models = {
            name: self.query_one(f"#model-{name}", Input).value.strip() for name in _MODEL_AGENTS
        }
        d.parallel = self.query_one("#cb-parallel", Checkbox).value
        d.all_live = self.query_one("#cb-alllive", Checkbox).value
        scope_idx = self.query_one("#scope", RadioSet).pressed_index
        d.save_scope = ("none", "global", "project")[scope_idx if scope_idx >= 0 else 0]
        style_idx = self.query_one("#runstyle", RadioSet).pressed_index
        d.run_style = ("full", "single", "portions")[style_idx if style_idx >= 0 else 0]
        if d.run_style == "full":
            d.parallel = True
        if d.run_style == "portions" and self._report is not None and self._report.portions:
            d.portion_plan = [list(p) for p in self._report.portions]
            d.force = True

    def _persist_scope(self) -> None:
        from siftmesh_core.config import save_agent_selection

        try:
            save_agent_selection(
                self.settings.executor_selection,
                self.settings.agent_preference,
                scope=self.draft.save_scope,  # type: ignore[arg-type]
            )
        except Exception as exc:  # pragma: no cover - config IO is best-effort here
            self.notify(f"config save failed: {exc}", severity="warning")


# Back-compat: HomeScreen "New run" entry point.
Step1ProjectScreen = RunSetupScreen

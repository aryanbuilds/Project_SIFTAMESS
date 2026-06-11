"""Onboarding screen (Epic O) — install backends, probe agents, pick a multi-agent set, persist."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from siftmesh_core.adapters.profiles import effective_model, load_profiles
from siftmesh_core.config import SiftmeshSettings, save_agent_selection
from siftmesh_core.doctor import probe_agents, run_setup

_FLOOR = "deterministic_executor"
# Advisory Tier-2 JUDGE choices (a separate purpose from the executor). litellm:<model> backends are
# set via the CLI/config (a Select can't free-type a model id).
_JUDGE_CHOICES = [
    ("Tier-1 only (no advisory judge)", "none"),
    ("claude (CLI — subscription or API)", "cli:claude"),
    ("gemini (CLI)", "cli:gemini"),
    ("codex (CLI)", "cli:codex"),
    ("opencode (CLI)", "cli:opencode"),
]
# Live agents that take a per-provider model override (friendly name → profile_id).
_MODEL_AGENTS = [
    ("claude", "claude_headless"),
    ("gemini", "gemini_headless"),
    ("codex", "codex_headless"),
    ("opencode", "opencode_headless"),
]


class OnboardingScreen(Screen):
    """Detect installed/authenticated/sandboxed agents and persist the chosen set."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings) -> None:
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Pick the agents SIFTMesh may use (live agents need a CLI + auth + a sandbox recipe). "
            "The deterministic floor is always available.",
            id="intro",
        )
        yield SelectionList[str](id="agentsel")
        with Collapsible(title="Per-provider models (blank = default)", id="models"):
            for name, profile_id in _MODEL_AGENTS:
                prof = load_profiles().get(profile_id)
                default = effective_model(self.settings, profile_id, prof.model if prof else None)
                yield Input(
                    value=default or "",
                    placeholder=f"{name} model (e.g. {default or 'auto / provider default'})",
                    id=f"model-{name}",
                )
        with Horizontal(id="judgerow"):
            yield Label("Tier-2 judge (advisory):")
            yield Select(
                _JUDGE_CHOICES,
                value=self._initial_judge(),
                id="judge",
                allow_blank=False,
            )
        with Horizontal(id="scoperow"):
            yield Label("Save to:")
            with RadioSet(id="scope"):
                yield RadioButton("global (~/.config)", value=True, id="scope-global")
                yield RadioButton("project (./siftmesh.toml)", id="scope-project")
        with Horizontal(id="setupbtns"):
            yield Button("Install all backends", id="install", variant="primary")
            yield Button("Re-probe", id="reprobe")
            yield Button("Save selection", id="save", variant="success")
        with VerticalScroll(id="setupstatus"):
            yield Static(id="statusline")
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        cap = probe_agents(self.settings)
        sel = self.query_one("#agentsel", SelectionList)
        sel.clear_options()
        chosen = set(self.settings.agent_preference)
        for a in cap.agents:
            if a.profile_id == _FLOOR:
                continue  # the floor is implicit (always appended)
            badge = (
                f"{a.profile_id:<18} "
                f"present={'yes' if a.present else 'no '} "
                f"auth={'yes' if a.auth_ok else 'no '} "
                f"sandboxed={'yes' if a.sandboxed else 'NO '} "
                f"tools={a.tool_reachable}"
            )
            ready = a.present and a.auth_ok and a.sandboxed
            sel.add_option(Selection(badge, a.profile_id, ready or a.profile_id in chosen))
        self._status(
            f"default agent today: {cap.chosen}"
            + (f" · live ready: {cap.live_candidate}" if cap.live_candidate else "")
        )

    def _status(self, msg: str) -> None:
        self.query_one("#statusline", Static).update(msg)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install":
            self._status("installing backends (uv sync --all-extras)…")
            self._install()
        elif event.button.id == "reprobe":
            self._populate()
        elif event.button.id == "save":
            self._save()

    @work(thread=True, exclusive=True)
    def _install(self) -> None:
        code = run_setup(self.settings)
        msg = "install complete — re-probing." if code == 0 else "install FAILED (see terminal)."
        self.app.call_from_thread(self._after_install, msg)

    def _after_install(self, msg: str) -> None:
        self._status(msg)
        self._populate()

    def _initial_judge(self) -> str:
        """Pre-select the Select from the current settings.judge (bare name → cli:name)."""
        j = getattr(self.settings, "judge", None)
        if not j:
            return "none"
        norm = j if ":" in j else f"cli:{j}"
        return norm if norm in {v for _, v in _JUDGE_CHOICES} else "none"

    def _collect_models(self) -> dict[str, str]:
        """Per-agent model overrides from the inputs (only those the operator filled in)."""
        models: dict[str, str] = {}
        for name, profile_id in _MODEL_AGENTS:
            val = self.query_one(f"#model-{name}", Input).value.strip()
            if val:
                models[profile_id] = val
        return models

    def _save(self) -> None:
        selected = list(self.query_one("#agentsel", SelectionList).selected)
        preference = [*selected, _FLOOR] if selected else [_FLOOR]
        executor = "auto" if selected else "deterministic"
        scope = "project" if self.query_one("#scope", RadioSet).pressed_index == 1 else "global"
        judge_choice = str(self.query_one("#judge", Select).value)
        judge = None if judge_choice == "none" else judge_choice
        models = self._collect_models()
        path = save_agent_selection(
            executor,
            preference,
            scope=scope,  # type: ignore[arg-type]
            judge=judge,
            llm_critic_enabled=judge is not None,  # picking a judge enables the advisory layer
            agent_models=models or None,
        )
        jlabel = judge or "Tier-1 only"
        self._status(
            f"saved → {path}  (executor={executor}, judge={jlabel}, preference={preference})"
        )

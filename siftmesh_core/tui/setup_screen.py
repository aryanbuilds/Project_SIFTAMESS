"""Onboarding (Epic O, simplified) — pick agents + set up the Tier-2 judge, in two tabs.

Agents tab: a greyed-until-ready multiselect of the four live agents (claude/opencode/codex/gemini)
with per-agent remediation, a **Launch auth** button (runs the vendor login on the real TTY via
``App.suspend()``), and a background re-probe (``set_interval``) that flips an agent from grey to
selectable the moment its CLI/auth lands. Models + save-scope + rename move to an Advanced section.

Tier-2 judge tab: a provider radio (Tier-1-only / claude / codex / opencode / gemini / zen /
custom litellm). CLI backends use their own auth (Launch auth); LiteLLM backends show an API-key
input saved to the 600-perm env file (``auth_actions.save_provider_key``, validated before persist).
The judge is advisory + fail-soft (Tier-1 stays the sole promoter).
"""

from __future__ import annotations

import subprocess
from typing import Any, Literal

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    RadioButton,
    RadioSet,
    SelectionList,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.selection_list import Selection

from siftmesh_core.adapters.profiles import effective_model, load_profiles
from siftmesh_core.config import SiftmeshSettings, save_agent_selection
from siftmesh_core.doctor import _is_ready, agent_remediation, probe_agents, run_setup
from siftmesh_core.schemas.agent_capabilities import SAFETY_TIER_DESC, safety_tier_label
from siftmesh_core.tui.auth_actions import auth_command, save_provider_key

_FLOOR = "deterministic_executor"
_MODEL_AGENTS = [
    ("claude", "claude_headless"),
    ("gemini", "gemini_headless"),
    ("codex", "codex_headless"),
    ("opencode", "opencode_headless"),
]
# Tier-2 judge provider radio: id -> metadata. kind ∈ {none, cli, litellm}.
_JUDGE_RADIO: dict[str, dict[str, Any]] = {
    "j-none": {"kind": "none", "desc": "Tier-1 deterministic critic only (the sole promoter)."},
    "j-claude": {
        "kind": "cli",
        "judge": "cli:claude",
        "profile": "claude_headless",
        "desc": "Advisory claude CLI (its own auth). Never promotes.",
    },
    "j-codex": {
        "kind": "cli",
        "judge": "cli:codex",
        "profile": "codex_headless",
        "desc": "Advisory codex CLI (codex login). Never promotes.",
    },
    "j-opencode": {
        "kind": "cli",
        "judge": "cli:opencode",
        "profile": "opencode_headless",
        "desc": "Advisory opencode CLI (opencode auth login). Never promotes.",
    },
    "j-gemini": {
        "kind": "litellm",
        "provider": "gemini",
        "model": "gemini/gemini-2.5-pro",
        "desc": "Advisory Gemini via LiteLLM (GEMINI_API_KEY).",
    },
    "j-zen": {
        "kind": "litellm",
        "provider": "zen",
        "model": "openai/glm-4.6",
        "needs_api_base": True,
        "desc": "opencode-go / zen (OpenAI-compatible gateway: OPENAI_API_KEY + api_base /v1).",
    },
    "j-custom": {
        "kind": "litellm",
        "provider": None,
        "model": "",
        "desc": "Any litellm:<provider/model> with an API key (provider inferred from the prefix).",
    },
}


def _provider_from_model(model: str) -> str:
    """Infer the LiteLLM provider for save_provider_key from a model string's prefix."""
    prefix = model.split("/", 1)[0] if "/" in model else ""
    return {"gemini": "gemini", "anthropic": "anthropic", "openai": "openai"}.get(prefix, "openai")


class OnboardingScreen(Screen):
    """Two tabs: pick the live agents, and set up the advisory Tier-2 judge. Floor (T0) implicit."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings) -> None:
        super().__init__()
        self.settings = settings
        self._reprobe_timer: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="agents-tab"):
            with TabPane("Agents", id="agents-tab"):
                yield Static(id="readiness")
                yield Static(
                    "Pick the live agents to use. Greyed = not installed/authed yet — fix it "
                    "below, then it becomes selectable automatically. The deterministic floor "
                    "(T0) always works with no keys.",
                    id="intro",
                )
                yield SelectionList[str](id="agentsel")
                with Horizontal(id="agentbtns"):
                    yield Button("Launch auth (highlighted)", id="launchauth", variant="primary")
                    yield Button("Install backends", id="install")
                    yield Button("Re-probe", id="reprobe")
                    yield Button("Save agents", id="save", variant="success")
                yield Static(id="guidance")
                with Collapsible(title="Advanced (models · rename · save scope)", id="advanced"):
                    for name, profile_id in _MODEL_AGENTS:
                        prof = load_profiles().get(profile_id)
                        default = effective_model(
                            self.settings, profile_id, prof.model if prof else None
                        )
                        yield Input(
                            value=default or "",
                            placeholder=f"{name} model (blank = default)",
                            id=f"model-{name}",
                        )
                        yield Input(
                            value=self.settings.agent_aliases.get(profile_id, ""),
                            placeholder=f"{name} display name (rename, optional)",
                            id=f"rename-{name}",
                        )
                    with RadioSet(id="scope"):
                        yield RadioButton("save: global (~/.config)", value=True, id="scope-global")
                        yield RadioButton("save: project (./siftmesh.toml)", id="scope-project")
            with TabPane("Tier-2 judge", id="judge-tab"):
                yield Static(
                    "An optional advisory second opinion. It can only lower confidence / "
                    "annotate — the deterministic Tier-1 critic stays the sole promoter.",
                    id="judgeintro",
                )
                with RadioSet(id="judgeprov"):
                    yield RadioButton("Tier-1 only (no judge)", value=True, id="j-none")
                    yield RadioButton("claude (CLI login)", id="j-claude")
                    yield RadioButton("codex (CLI login)", id="j-codex")
                    yield RadioButton("opencode (CLI login)", id="j-opencode")
                    yield RadioButton("gemini (API key)", id="j-gemini")
                    yield RadioButton("opencode-go / zen (API key)", id="j-zen")
                    yield RadioButton("custom litellm model (API key)", id="j-custom")
                yield Static(id="judgedesc")
                yield Button("Launch auth (this judge)", id="launchjudgeauth", variant="primary")
                yield Input(placeholder="API key", password=True, id="apikey")
                yield Input(placeholder="model id (e.g. gemini/gemini-2.5-pro)", id="litemodel")
                yield Input(placeholder="api_base (zen/custom; MUST end in /v1)", id="apibase")
                yield Button("Save judge", id="savejudge", variant="success")
                yield Static(id="judgestatus")
        yield Footer()

    def on_mount(self) -> None:
        self._populate_agents()
        self._init_judge_tab()
        self._reprobe_timer = self.set_interval(2.0, self._reprobe_tick)

    def on_unmount(self) -> None:
        if self._reprobe_timer is not None:
            self._reprobe_timer.stop()

    # ── Agents tab ────────────────────────────────────────────────────────────
    def _populate_agents(self) -> None:
        cap = probe_agents(self.settings)
        profiles = load_profiles()
        sel = self.query_one("#agentsel", SelectionList)
        # preserve the operator's current picks across a rebuild (re-probe must not drop selections)
        previously = set(sel.selected) if sel.options else set(self.settings.agent_preference)
        sel.clear_options()
        chosen = set(self.settings.agent_preference)
        fix: list[str] = []
        for a in cap.agents:
            if a.profile_id == _FLOOR:
                continue
            alias = self.settings.agent_aliases.get(a.profile_id, a.profile_id)
            selectable = _is_ready(a) or a.profile_id in chosen
            badge = (
                f"[{a.safety_tier}] {alias:<20} present={'y' if a.present else 'n'} "
                f"auth={'y' if a.auth_ok else 'n'} sandbox={'y' if a.sandboxed else 'n'} "
                f"tools={a.tool_reachable}"
            )
            state = selectable and a.profile_id in previously
            sel.add_option(Selection(badge, a.profile_id, state, disabled=not selectable))
            if not _is_ready(a):
                for hint in agent_remediation(a, profiles.get(a.profile_id)):
                    fix.append(f"  {alias}: {hint}")
        self._render_guidance(fix)
        self._render_readiness(cap)

    def _render_readiness(self, cap: Any) -> None:
        badge = self.query_one("#readiness", Static)
        if cap.live_candidate:
            badge.update(f"[$success]✓ live agent ready:[/] {cap.live_candidate} (T1/T2)")
        else:
            badge.update(
                "[$warning]● floor only (T0):[/] no live agent ready — fix one below, or just Save "
                "and run on the deterministic real-tool floor (no keys needed)."
            )

    def _render_guidance(self, fix: list[str]) -> None:
        lines: list[str] = []
        if fix:
            lines.append("To make an agent ready:")
            lines += fix
            lines.append("")
        lines.append("Safety tiers (labels only — never gate dispatch):")
        lines += [f"  {safety_tier_label(t)}" for t in SAFETY_TIER_DESC]
        self.query_one("#guidance", Static).update("\n".join(lines))

    @work(thread=True, exclusive=True)
    def _reprobe_tick(self) -> None:
        cap = probe_agents(self.settings)  # shells `--version` — keep off the UI thread
        self.app.call_from_thread(self._apply_reprobe, cap)

    def _apply_reprobe(self, _cap: Any) -> None:
        self._populate_agents()  # rebuild preserving selection

    def _highlighted_agent(self) -> str | None:
        sel = self.query_one("#agentsel", SelectionList)
        idx = sel.highlighted
        if idx is None:
            return None
        try:
            return str(sel.get_option_at_index(idx).value)
        except Exception:
            return None

    def _launch_auth(self, profile_id: str | None) -> None:
        if profile_id is None:
            self.notify("highlight an agent first")
            return
        cmd = auth_command(profile_id)
        if cmd is None:
            self.notify(f"{profile_id}: no interactive login — set its API key (env/.env)")
            return
        try:
            with self.app.suspend():
                subprocess.run(cmd, check=False)
        except (FileNotFoundError, OSError):
            self.notify(f"could not launch — run it yourself: {' '.join(cmd)}")
            return
        self.notify("re-probing after auth…")
        self._populate_agents()

    def _save_agents(self) -> None:
        selected = list(self.query_one("#agentsel", SelectionList).selected)
        preference = [*selected, _FLOOR] if selected else [_FLOOR]
        executor = "auto" if selected else "deterministic"
        scope = self._scope()
        models: dict[str, str] = {}
        aliases: dict[str, str] = {}
        for name, profile_id in _MODEL_AGENTS:
            mv = self.query_one(f"#model-{name}", Input).value.strip()
            if mv:
                models[profile_id] = mv
            av = self.query_one(f"#rename-{name}", Input).value.strip()
            if av:
                aliases[profile_id] = av
        path = save_agent_selection(
            executor,
            preference,
            scope=scope,
            agent_models=models or None,
            agent_aliases=aliases or None,
        )
        self.notify(f"saved agents → {path}")

    # ── Judge tab ─────────────────────────────────────────────────────────────
    def _init_judge_tab(self) -> None:
        rid = self._initial_judge_radio()
        self.query_one(f"#{rid}", RadioButton).value = True
        self._apply_judge_kind(rid)

    def _initial_judge_radio(self) -> str:
        j = getattr(self.settings, "judge", None)
        if not j:
            return "j-none"
        if j.startswith("cli:"):
            return {
                "claude": "j-claude",
                "codex": "j-codex",
                "opencode": "j-opencode",
                "gemini": "j-gemini",
            }.get(j.split(":", 1)[1], "j-none")
        if j.startswith("litellm:"):
            return "j-gemini" if j.split(":", 1)[1].startswith("gemini/") else "j-custom"
        return "j-none"

    def _apply_judge_kind(self, rid: str) -> None:
        meta = _JUDGE_RADIO.get(rid, {})
        kind = meta.get("kind")
        self.query_one("#judgedesc", Static).update(str(meta.get("desc", "")))
        self.query_one("#launchjudgeauth", Button).display = kind == "cli"
        is_litellm = kind == "litellm"
        for wid in ("#apikey", "#litemodel", "#apibase"):
            self.query_one(wid, Input).display = is_litellm
        if is_litellm and not self.query_one("#litemodel", Input).value:
            self.query_one("#litemodel", Input).value = str(meta.get("model") or "")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "judgeprov" and event.pressed is not None:
            self._apply_judge_kind(str(event.pressed.id))

    def _selected_judge_radio(self) -> str:
        rs = self.query_one("#judgeprov", RadioSet)
        pressed = rs.pressed_button
        return str(pressed.id) if pressed is not None else "j-none"

    def _save_judge(self) -> None:
        rid = self._selected_judge_radio()
        meta = _JUDGE_RADIO.get(rid, {})
        kind = meta.get("kind")
        if kind == "none":
            save_agent_selection(
                self.settings.executor_selection,
                self.settings.agent_preference,
                scope=self._scope(),
                judge=None,
                llm_critic_enabled=False,
            )
            self.query_one("#judgestatus", Static).update("saved: Tier-1 only (no advisory judge)")
        elif kind == "cli":
            save_agent_selection(
                self.settings.executor_selection,
                self.settings.agent_preference,
                scope=self._scope(),
                judge=str(meta["judge"]),
                llm_critic_enabled=True,
            )
            self.query_one("#judgestatus", Static).update(f"saved: {meta['judge']}")
        else:
            self.query_one("#judgestatus", Static).update("validating + saving key…")
            self._save_judge_litellm(meta)

    @work(thread=True, exclusive=True)
    def _save_judge_litellm(self, meta: dict[str, Any]) -> None:
        model = self.query_one("#litemodel", Input).value.strip() or str(meta.get("model") or "")
        api_base = self.query_one("#apibase", Input).value.strip() or None
        key = self.query_one("#apikey", Input).value.strip()
        if not model:
            self.app.call_from_thread(
                self._judge_status, "give a model id (e.g. gemini/gemini-2.5-pro)"
            )
            return
        provider = meta.get("provider") or _provider_from_model(model)
        if key:
            saved, msg = save_provider_key(str(provider), key, model=model, api_base=api_base)
            if not saved:
                self.app.call_from_thread(self._judge_status, f"key not saved: {msg}")
                return
        save_agent_selection(
            self.settings.executor_selection,
            self.settings.agent_preference,
            scope=self._scope(),
            judge=f"litellm:{model}",
            llm_critic_enabled=True,
            judge_api_base=api_base,
            judge_drop_params=bool(meta.get("needs_api_base")),
        )
        self.app.call_from_thread(self._judge_status, f"saved: litellm:{model}")

    def _judge_status(self, msg: str) -> None:
        self.query_one("#judgestatus", Static).update(msg)

    def _scope(self) -> Literal["global", "project"]:
        return "project" if self.query_one("#scope", RadioSet).pressed_index == 1 else "global"

    # ── buttons + install ──────────────────────────────────────────────────────
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "install":
            self.query_one("#install", Button).disabled = True
            self.query_one("#reprobe", Button).disabled = True
            self.notify("installing backends (uv sync --all-extras)…")
            self._install()
        elif bid == "reprobe":
            self._populate_agents()
        elif bid == "launchauth":
            self._launch_auth(self._highlighted_agent())
        elif bid == "save":
            self._save_agents()
        elif bid == "launchjudgeauth":
            meta = _JUDGE_RADIO.get(self._selected_judge_radio(), {})
            self._launch_auth(meta.get("profile"))
        elif bid == "savejudge":
            self._save_judge()

    @work(thread=True, exclusive=True)
    def _install(self) -> None:
        code = run_setup(self.settings)
        msg = "install complete — re-probing." if code == 0 else "install FAILED (see terminal)."
        self.app.call_from_thread(self._after_install, msg, code)

    def _after_install(self, msg: str, code: int) -> None:
        self.notify(msg)
        self.query_one("#reprobe", Button).disabled = False
        self.query_one("#install", Button).disabled = code == 0
        self._populate_agents()

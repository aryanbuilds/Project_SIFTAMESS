"""The cockpit App + home screen (Epic O)."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import DEFAULT_BASE


class HomeScreen(Screen):
    """Minimal home (opencode-style): centered New run + a left recent-runs list + visible keys."""

    BINDINGS = [
        Binding("n", "new_run", "New run"),
        Binding("enter", "attach", "Attach"),
        Binding("r", "resume", "Resume"),
        Binding("o", "agent_setup", "Agents"),
        Binding("ctrl+t", "app.toggle_theme", "Theme"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, *, settings: SiftmeshSettings) -> None:
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="homesplit"):
            with Vertical(id="homeside"):
                yield Label("Recent runs")
                yield ListView(id="runs")
                yield Static(id="rundetail", markup=False)
                yield Static(id="firstrun")
            with Vertical(id="hero"):
                yield Static("SIFTMesh", id="herotitle")
                yield Button("New run", id="new", variant="success")
                yield Button("Agent setup", id="setup")
                yield Static("n new · ↵ attach · r resume · o agents · q quit", id="herohint")
        yield Footer()

    def on_mount(self) -> None:
        self._render_firstrun()
        lv = self.query_one("#runs", ListView)
        base = Path(DEFAULT_BASE)
        runs = sorted(base.glob("RUN-*"), reverse=True) if base.is_dir() else []
        if not runs:
            lv.append(ListItem(Label("No runs yet — press n to start one.")))
            return
        from siftmesh_core.run_dir import RunPaths
        from siftmesh_core.tui.snapshot import run_badge

        for r in runs:
            try:
                badge = run_badge(RunPaths(root=r))
            except Exception:
                badge = "?"
            item = ListItem(Label(f"{r.name}  [{badge}]"))
            item.run_path = r  # type: ignore[attr-defined]
            lv.append(item)

    def _render_firstrun(self) -> None:
        """A muted one-liner when no live agent is ready (never blocks the floor)."""
        banner = self.query_one("#firstrun", Static)
        try:
            from siftmesh_core.doctor import probe_agents

            cap = probe_agents(self.settings)
        except Exception:
            banner.display = False
            return
        if cap.live_candidate:
            banner.display = False
            return
        banner.update("[dim]No live agent ready — runs use the floor (T0). Press o to onboard.[/]")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if getattr(event.item, "run_path", None) is not None:
            self.action_attach()  # Enter / click on a run = attach (opencode-style)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        path = getattr(event.item, "run_path", None)
        detail = self.query_one("#rundetail", Static)
        if path is None:
            detail.update("")
            return
        from siftmesh_core.run_dir import RunPaths
        from siftmesh_core.tui.snapshot import run_badge

        try:
            detail.update(f"{path.name} — {run_badge(RunPaths(root=path))}")
        except Exception:
            detail.update(str(path.name))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new":
            self.action_new_run()
        elif event.button.id == "setup":
            self.action_agent_setup()

    def action_new_run(self) -> None:
        from siftmesh_core.tui.wizard import RunSetupScreen

        self.app.push_screen(RunSetupScreen(settings=self.settings))

    def action_agent_setup(self) -> None:
        from siftmesh_core.tui.setup_screen import OnboardingScreen

        self.app.push_screen(OnboardingScreen(settings=self.settings))

    def _selected_run(self) -> Path | None:
        return getattr(self.query_one("#runs", ListView).highlighted_child, "run_path", None)

    def action_attach(self) -> None:
        path = self._selected_run()
        if path is None:
            self.notify("select a run to attach")
            return
        from siftmesh_core.tui.cockpit import CockpitScreen

        self.app.push_screen(CockpitScreen(path, settings=self.settings))

    def action_resume(self) -> None:
        path = self._selected_run()
        if path is None:
            self.notify("select a run to resume")
            return
        from siftmesh_core.run_dir import RunPaths
        from siftmesh_core.tui.cockpit import CockpitScreen
        from siftmesh_core.tui.snapshot import resumable

        if not resumable(RunPaths(root=path)):
            self.notify("that run is terminal / has no state — press Enter to attach")
            return
        self.app.push_screen(CockpitScreen(path, settings=self.settings, auto_resume=True))


class SiftmeshTUI(App):
    """SIFTMesh Textual cockpit application."""

    CSS_PATH = "cockpit.tcss"
    TITLE = "SIFTMesh"
    BINDINGS = [("ctrl+t", "toggle_theme", "Theme"), ("q", "quit", "Quit")]
    # Collapse the cockpit's right column under the task table on narrow terminals.
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-wide")]

    def __init__(
        self,
        *,
        settings: SiftmeshSettings,
        run_dir: Path | None = None,
        launch_params: dict | None = None,
        start: str | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._run_dir = run_dir
        self._launch_params = launch_params
        self._start = start

    def action_toggle_theme(self) -> None:
        """Toggle the two SIFTMesh themes (the ctrl+p command palette lists all themes)."""
        from siftmesh_core.tui.theme import SIFTMESH_DARK, SIFTMESH_LIGHT

        self.theme = SIFTMESH_LIGHT.name if self.theme == SIFTMESH_DARK.name else SIFTMESH_DARK.name

    def get_system_commands(self, screen):  # type: ignore[no-untyped-def]
        """Add SIFTMesh operator actions to the built-in ctrl+p command palette (opencode-style).

        Cockpit actions are offered only when a CockpitScreen is active; they dispatch to that
        screen's already-governed actions (each runs in a worker thread where needed).
        """
        from textual.app import SystemCommand

        from siftmesh_core.tui.cockpit import CockpitScreen

        yield from super().get_system_commands(screen)
        if isinstance(screen, HomeScreen):
            yield SystemCommand("New run", "Start a new investigation", screen.action_new_run)
            yield SystemCommand(
                "Agent setup", "Onboard agents + Tier-2 judge", screen.action_agent_setup
            )
            yield SystemCommand("Toggle theme", "Switch light/dark", self.action_toggle_theme)
        if isinstance(screen, CockpitScreen):
            yield SystemCommand(
                "Resolve a gate", "Approve/reject any gate", screen.action_gate_selector
            )
            yield SystemCommand(
                "Retry selected task", "Re-critique + re-dispatch", screen.action_retry_task
            )
            yield SystemCommand(
                "Resume / next step", "Drive the engine one step", screen.action_resume
            )
            yield SystemCommand("Replay", "Show the audit replay", screen.action_replay)
            yield SystemCommand("Switch run", "Pick another run", screen.action_switch_run)

    def on_mount(self) -> None:
        from siftmesh_core.secrets_env import load_secrets_into_env
        from siftmesh_core.tui.cockpit import CockpitScreen
        from siftmesh_core.tui.theme import DEFAULT_THEME, SIFTMESH_THEMES

        # Provider credentials (LiteLLM judge keys) from the 600-perm env file → os.environ, so the
        # in-process judge + child agents see them. A real shell export still wins (override=False).
        load_secrets_into_env()

        for theme in SIFTMESH_THEMES:
            self.register_theme(theme)
        self.theme = DEFAULT_THEME  # ctrl+t toggles; ctrl+p → "Change theme" lists all

        if self._start == "onboard":
            from siftmesh_core.tui.setup_screen import OnboardingScreen

            self.push_screen(OnboardingScreen(settings=self._settings))
        elif self._run_dir is not None:
            self.push_screen(CockpitScreen(self._run_dir, settings=self._settings))
        elif self._launch_params is not None:
            self.push_screen(
                CockpitScreen(None, settings=self._settings, launch_params=self._launch_params)
            )
        else:
            self.push_screen(HomeScreen(settings=self._settings))

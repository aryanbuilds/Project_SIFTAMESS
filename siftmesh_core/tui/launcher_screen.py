"""New-run launcher (Epic O) — collect run params, then drive the governed engine in the cockpit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select

from siftmesh_core.config import SiftmeshSettings

_MODES = ("manual", "review_only", "auto_human_loop", "auto")


class NewRunScreen(Screen):
    """Collect case/evidence/objective/mode/agent, then launch a live cockpit run."""

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings) -> None:
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        # agent choices = the persisted live preference (minus the floor) + the floor alias.
        agents = [p for p in self.settings.agent_preference if p != "deterministic_executor"]
        agent_opts = [("deterministic (floor)", "deterministic")] + [
            (p.removesuffix("_headless"), p.removesuffix("_headless")) for p in agents
        ]
        yield Header()
        with Vertical(id="newrun"):
            yield Label("Case directory")
            yield Input(placeholder="./case01", id="case")
            yield Label("Evidence directory (read-only)")
            yield Input(placeholder="./evidence", id="evidence")
            yield Label("Objective (or leave blank)")
            yield Input(placeholder="was host X compromised?", id="objective")
            yield Label("Mode")
            yield Select([(m, m) for m in _MODES], value="auto", id="mode", allow_blank=False)
            yield Label("Agent")
            yield Select(agent_opts, value="deterministic", id="agent", allow_blank=False)
            yield Button("Launch run", id="launch", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "launch":
            return
        case = self.query_one("#case", Input).value.strip()
        evidence = self.query_one("#evidence", Input).value.strip()
        if not case or not evidence:
            self.notify("case dir and evidence dir are required", severity="error")
            return
        objective = self.query_one("#objective", Input).value.strip() or None
        mode = self.query_one("#mode", Select).value
        agent = self.query_one("#agent", Select).value

        from siftmesh_core.cli import _agent_overrides  # lazy: avoid an import cycle
        from siftmesh_core.config import load_settings
        from siftmesh_core.tui.cockpit import CockpitScreen

        settings = load_settings(
            **_agent_overrides(None if agent == "deterministic" else str(agent))
        )
        params = {
            "case_dir": case,
            "evidence": evidence,
            "objective": objective,
            "mode": mode,
        }
        self.app.switch_screen(CockpitScreen(None, settings=settings, launch_params=params))

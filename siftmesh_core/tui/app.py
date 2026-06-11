"""The cockpit App + home screen (Epic O)."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from siftmesh_core.config import SiftmeshSettings
from siftmesh_core.run_dir import DEFAULT_BASE


class HomeScreen(Screen):
    """Run picker + entry points: new run, onboard agents, attach to an existing run."""

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, *, settings: SiftmeshSettings) -> None:
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("SIFTMesh cockpit — pick a run to attach, or start one.", id="hometitle")
        yield ListView(id="runs")
        with Horizontal(id="homebtns"):
            yield Button("New run", id="new", variant="success")
            yield Button("Attach", id="attach", variant="primary")
            yield Button("Onboard agents", id="onboard")
            yield Button("Quit", id="quit")
        yield Footer()

    def on_mount(self) -> None:
        lv = self.query_one("#runs", ListView)
        base = Path(DEFAULT_BASE)
        runs = sorted(base.glob("RUN-*"), reverse=True) if base.is_dir() else []
        if not runs:
            lv.append(ListItem(Label("(no runs under ./case_runs — start one with 'New run')")))
            return
        for r in runs:
            item = ListItem(Label(r.name))
            item.run_path = r  # type: ignore[attr-defined]
            lv.append(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new":
            from siftmesh_core.tui.launcher_screen import NewRunScreen

            self.app.push_screen(NewRunScreen(settings=self.settings))
        elif event.button.id == "onboard":
            from siftmesh_core.tui.setup_screen import OnboardingScreen

            self.app.push_screen(OnboardingScreen(settings=self.settings))
        elif event.button.id == "attach":
            self._attach_selected()
        elif event.button.id == "quit":
            self.app.exit()

    def _attach_selected(self) -> None:
        lv = self.query_one("#runs", ListView)
        item = lv.highlighted_child
        path = getattr(item, "run_path", None)
        if path is None:
            self.notify("select a run to attach")
            return
        from siftmesh_core.tui.cockpit import CockpitScreen

        self.app.push_screen(CockpitScreen(path, settings=self.settings))


class SiftmeshTUI(App):
    """SIFTMesh Textual cockpit application."""

    CSS_PATH = "cockpit.tcss"
    TITLE = "SIFTMesh"
    BINDINGS = [("q", "quit", "Quit")]
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

    def on_mount(self) -> None:
        from siftmesh_core.tui.cockpit import CockpitScreen

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

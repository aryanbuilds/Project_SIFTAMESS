"""SIFTMesh Textual cockpit (Epic O) — optional, lazily imported.

The base install stays lean; the CLI imports this only for `siftmesh tui` / `siftmesh setup`, and
`require_textual()` prints a friendly install hint if the optional `textual` extra is absent. The
cockpit is a READ-ONLY layer over the run dir (it renders `run_state.json` + the ledgers); launching
a run uses the SAME governed engine — no new write paths, evidence access, MCP tools, or raw shell.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_TEXTUAL_HINT = (
    "the Textual cockpit needs the optional 'tui' extra. Install it with one of:\n"
    "  siftmesh doctor --setup      # installs all extras (recommended)\n"
    "  uv sync --extra tui          # just the TUI"
)


class TextualMissingError(RuntimeError):
    """Raised when the cockpit is requested but the optional `textual` extra is not installed."""


def require_textual() -> None:
    """Fail closed with an actionable hint if `textual` is not importable."""
    if importlib.util.find_spec("textual") is None:
        raise TextualMissingError(_TEXTUAL_HINT)


def launch(
    run_dir: str | Path | None = None,
    *,
    settings: Any,
    launch_params: dict | None = None,
    start: str | None = None,
) -> int:
    """Run the cockpit app. `run_dir` attaches to an existing run; `launch_params` starts a new run;
    `start="onboard"` opens onboarding; otherwise the home/run-picker. Returns 0."""
    require_textual()
    from siftmesh_core.tui.app import SiftmeshTUI

    app = SiftmeshTUI(
        settings=settings,
        run_dir=Path(run_dir) if run_dir else None,
        launch_params=launch_params,
        start=start,
    )
    app.run()
    return 0

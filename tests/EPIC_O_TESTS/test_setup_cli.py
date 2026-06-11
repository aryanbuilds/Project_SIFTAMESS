"""Epic O — the `setup` and `tui` CLI commands (headless persistence + lazy-textual fallback)."""

from __future__ import annotations

from pathlib import Path

import siftmesh_core.doctor as doctor
from siftmesh_core.cli import app
from siftmesh_core.config import global_config_path, load_settings
from typer.testing import CliRunner

runner = CliRunner()


def _isolate(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(cwd)
    for var in ("SIFTMESH_AGENT_PREFERENCE", "SIFTMESH_EXECUTOR_SELECTION"):
        monkeypatch.delenv(var, raising=False)


def test_setup_headless_persists_ready_agents(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    # don't actually run `uv sync`; pretend install succeeded
    monkeypatch.setattr(doctor, "run_setup", lambda settings: 0)
    # pretend gemini is fully ready (present + auth + sandboxed)
    monkeypatch.setattr(
        __import__("shutil"), "which", lambda c: f"/usr/bin/{c}" if c == "gemini" else None
    )
    monkeypatch.setattr(doctor, "_agent_version", lambda cli: "v-test")
    monkeypatch.setenv("GEMINI_API_KEY", "x")

    result = runner.invoke(app, ["setup", "--no-tui", "--scope", "global"])
    assert result.exit_code == 0
    assert global_config_path().is_file()
    settings = load_settings()
    assert "gemini_headless" in settings.agent_preference
    assert settings.agent_preference[-1] == "deterministic_executor"
    assert settings.executor_selection == "auto"


def test_setup_headless_floor_when_nothing_ready(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "run_setup", lambda settings: 0)
    monkeypatch.setattr(__import__("shutil"), "which", lambda c: None)  # no agent CLIs
    result = runner.invoke(app, ["setup", "--yes"])
    assert result.exit_code == 0
    settings = load_settings()
    assert settings.executor_selection == "deterministic"
    assert settings.agent_preference == ["deterministic_executor"]


def test_setup_install_failure_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "run_setup", lambda settings: 1)
    result = runner.invoke(app, ["setup", "--no-tui"])
    assert result.exit_code == 1


def test_tui_friendly_error_when_textual_absent(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    import siftmesh_core.tui as tuimod

    monkeypatch.setattr(
        tuimod, "require_textual", lambda: (_ for _ in ()).throw(tuimod.TextualMissingError("nope"))
    )
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 1
    assert "nope" in result.output


def test_tui_unknown_run_dir_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    result = runner.invoke(app, ["tui", "case_runs/RUN-DOES-NOT-EXIST"])
    assert result.exit_code == 1

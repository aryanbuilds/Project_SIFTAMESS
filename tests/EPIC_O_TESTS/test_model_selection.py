"""Per-provider model selection: `agent_models` flows into adapters + judge; CLI/persist."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from siftmesh_core.adapters.headless import GeminiHeadlessAdapter
from siftmesh_core.adapters.judge import invoke_judge_text
from siftmesh_core.adapters.profiles import effective_model, load_profiles
from siftmesh_core.cli import _parse_model_overrides, app
from siftmesh_core.config import global_config_path, load_settings, save_agent_selection
from typer.testing import CliRunner

runner = CliRunner()


def test_effective_model_override_wins_else_default() -> None:
    s = load_settings(agent_models={"gemini_headless": "gemini-3-pro"})
    assert effective_model(s, "gemini_headless", None) == "gemini-3-pro"  # override (no default)
    assert effective_model(s, "codex_headless", "gpt-5.5") == "gpt-5.5"  # falls back to default
    assert effective_model(load_settings(), "gemini_headless", "x") == "x"  # no override → default


def test_parse_model_overrides_maps_aliases() -> None:
    assert _parse_model_overrides(["gemini=gemini-3-pro", "codex=gpt-5.5-mini"]) == {
        "gemini_headless": "gemini-3-pro",
        "codex_headless": "gpt-5.5-mini",
    }
    assert _parse_model_overrides(None) == {}


def test_parse_model_overrides_rejects_bad_input() -> None:
    import typer

    with pytest.raises(typer.BadParameter):
        _parse_model_overrides(["gemini"])  # no '='
    with pytest.raises(typer.BadParameter):
        _parse_model_overrides(["gemini="])  # empty model


def test_override_flows_into_headless_argv() -> None:
    adapter = GeminiHeadlessAdapter(
        settings=load_settings(agent_models={"gemini_headless": "gemini-3-pro"})
    )
    argv = adapter._build_argv(load_profiles()["gemini_headless"], "p", None)
    # gemini has NO pinned model by default — the override both enables and sets it
    assert argv[argv.index("--model") + 1] == "gemini-3-pro"


def test_override_flows_into_cli_judge(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        out = '{"response":"ok"}'
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    settings = load_settings(judge="cli:gemini", agent_models={"gemini_headless": "gemini-3-pro"})
    assert invoke_judge_text("x", settings) == "ok"
    assert "gemini-3-pro" in captured["argv"]  # the judge honors the per-provider override


def _isolate(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for v in ("SIFTMESH_AGENT_MODELS",):
        monkeypatch.delenv(v, raising=False)


def test_setup_model_persists(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import siftmesh_core.doctor as doctor

    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "run_setup", lambda settings: 0)
    monkeypatch.setattr(shutil, "which", lambda c: None)
    result = runner.invoke(app, ["setup", "--no-tui", "--model", "gemini=gemini-3-pro"])
    assert result.exit_code == 0
    assert global_config_path().is_file()
    assert load_settings().agent_models == {"gemini_headless": "gemini-3-pro"}


def test_save_agent_selection_merges_models(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _isolate(monkeypatch, tmp_path)
    save_agent_selection("auto", ["deterministic_executor"], agent_models={"gemini_headless": "g3"})
    save_agent_selection("auto", ["deterministic_executor"], agent_models={"codex_headless": "c5"})
    # second save MERGES (doesn't clobber the first provider's pin)
    assert load_settings().agent_models == {"gemini_headless": "g3", "codex_headless": "c5"}

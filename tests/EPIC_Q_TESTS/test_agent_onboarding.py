"""Epic Q round 1 — agent onboarding: `doctor --agents`, capability map, `agents` CLI (mocked)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import typer
from siftmesh_core.config import load_settings
from siftmesh_core.doctor import probe_agents, run_doctor, write_agent_capability_map
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.agent_capabilities import AgentCapabilityMap
from typer.testing import CliRunner

RealCase = Callable[..., tuple[RunPaths, Path]]


def _isolate_host(monkeypatch, present: set[str]) -> None:  # type: ignore[no-untyped-def]
    """Make the probe deterministic regardless of the real box: only ``present`` CLIs exist, no
    real `--version` subprocess, and a clean auth env."""
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}" if c in present else None)
    monkeypatch.setattr("siftmesh_core.doctor._agent_version", lambda cli: "v-test")
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CODEX_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_probe_reports_present_absent_and_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini"})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    by_id = {c.profile_id: c for c in probe_agents(load_settings()).agents}

    assert by_id["gemini_headless"].present is True
    assert by_id["gemini_headless"].auth_ok is True
    assert by_id["gemini_headless"].tool_reachable == "verify-live"
    assert by_id["codex_headless"].present is False
    assert by_id["codex_headless"].auth_ok is False
    assert by_id["opencode_headless"].tool_reachable == "no"
    assert by_id["claude_headless"].present is False
    assert by_id["deterministic_executor"].present is True
    assert by_id["deterministic_executor"].tool_reachable == "yes"


def test_default_is_floor_when_no_agent_can_reach_tools(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # gemini is present + authed, but cannot reach the typed tools yet (verify-live) → it must NOT
    # become the silent default; the deterministic real-tool floor is chosen instead.
    _isolate_host(monkeypatch, present={"gemini"})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cap = probe_agents(load_settings())
    assert cap.chosen == "deterministic_executor"
    assert next(c for c in cap.agents if c.selected).profile_id == "deterministic_executor"


def test_capability_map_sorted_and_byte_stable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini", "codex"})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    first = probe_agents(load_settings())
    second = probe_agents(load_settings())
    ids = [c.profile_id for c in first.agents]
    assert ids == sorted(ids)  # deterministic ordering
    assert first.model_dump_json(indent=2) == second.model_dump_json(indent=2)  # pure of clock/rand


def test_write_capability_map_validates_and_is_path_policed(  # type: ignore[no-untyped-def]
    real_case: RealCase, monkeypatch
) -> None:
    _isolate_host(monkeypatch, present=set())
    run, evidence = real_case()
    target = write_agent_capability_map(run.root, settings=load_settings(), evidence_root=evidence)
    assert target == run.context / "agent_capabilities.json"
    reloaded = AgentCapabilityMap.model_validate_json(target.read_text(encoding="utf-8"))
    assert reloaded.chosen == "deterministic_executor"  # nothing present → floor


def test_doctor_agents_section_prints_and_is_not_fail_closed(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present=set())
    code = run_doctor(agents=True, settings=load_settings())
    out = capsys.readouterr().out
    assert "Coding agents (onboarding)" in out
    assert "default agent:" in out
    assert code == 0  # absent agents are informational, never a fail-closed failure


def test_cli_agents_list_and_inspect(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini"})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    from siftmesh_core.cli import app

    runner = CliRunner()
    listed = runner.invoke(app, ["agents", "list"])
    assert listed.exit_code == 0
    assert "gemini_headless" in listed.stdout
    assert "default agent:" in listed.stdout

    inspected = runner.invoke(app, ["agents", "inspect", "gemini"])  # friendly alias accepted
    assert inspected.exit_code == 0
    assert "gemini_headless" in inspected.stdout
    assert "mcp_strategy" in inspected.stdout

    unknown = runner.invoke(app, ["agents", "inspect", "nope"])
    assert unknown.exit_code == 1


def test_app_has_agents_group() -> None:
    from siftmesh_core.cli import app

    assert isinstance(app, typer.Typer)
    names = {g.name for g in app.registered_groups}
    assert "agents" in names

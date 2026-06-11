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


def _isolate_host(monkeypatch, present: set[str], home: Path) -> None:  # type: ignore[no-untyped-def]
    """Make the probe deterministic regardless of the real box: only ``present`` CLIs exist, no real
    `--version` subprocess, a clean auth env, and an empty HOME (so cached ~/.gemini/~/.codex creds
    on the dev box don't leak into auth_ok)."""
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}" if c in present else None)
    monkeypatch.setattr("siftmesh_core.doctor._agent_version", lambda cli: "v-test")
    monkeypatch.setenv("HOME", str(home))
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CODEX_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_probe_reports_present_absent_auth_and_sandbox(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini"}, home=tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    by_id = {c.profile_id: c for c in probe_agents(load_settings()).agents}

    assert by_id["gemini_headless"].present is True
    assert by_id["gemini_headless"].auth_ok is True
    assert by_id["gemini_headless"].sandboxed is True  # ships native-tool deny flags
    assert by_id["gemini_headless"].tool_reachable == "verify-live"
    assert by_id["codex_headless"].present is False
    assert by_id["codex_headless"].auth_ok is False  # no CODEX_API_KEY, no ~/.codex/auth.json
    assert by_id["opencode_headless"].tool_reachable == "no"
    assert by_id["opencode_headless"].sandboxed is False  # honestly reported
    assert by_id["claude_headless"].present is False
    assert by_id["deterministic_executor"].present is True
    assert by_id["deterministic_executor"].tool_reachable == "yes"
    assert (
        "openclaw_headless" not in by_id
    )  # removed (personal-assistant gateway, not a coding agent)


def test_default_is_floor_under_deterministic_default(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # executor_selection defaults to "deterministic" → a plain `siftmesh run` uses the floor, so the
    # map's chosen MUST be the floor even though gemini is installed (matches real dispatch).
    _isolate_host(monkeypatch, present={"gemini"}, home=tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cap = probe_agents(load_settings())
    assert cap.chosen == "deterministic_executor"
    assert next(c for c in cap.agents if c.selected).profile_id == "deterministic_executor"
    # gemini is verify-live (can't reach tools) so it isn't even the opt-in live candidate.
    assert cap.live_candidate is None


def test_live_candidate_surfaced_without_becoming_default(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A ready Claude (present + authed + sandboxed + tool-reaching) is offered as the --agent opt-in
    # — but under the deterministic default it is NOT what a plain run dispatches.
    _isolate_host(monkeypatch, present={"claude"}, home=tmp_path)
    monkeypatch.setattr(
        "siftmesh_core.adapters.claude_adapter.claude_available", lambda settings: True
    )
    cap = probe_agents(load_settings())
    assert cap.chosen == "deterministic_executor"
    assert cap.live_candidate == "claude_headless"


def test_capability_map_sorted_and_byte_stable(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini", "codex"}, home=tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    first = probe_agents(load_settings())
    second = probe_agents(load_settings())
    ids = [c.profile_id for c in first.agents]
    assert ids == sorted(ids)  # deterministic ordering
    assert first.model_dump_json(indent=2) == second.model_dump_json(indent=2)  # pure of clock/rand


def test_write_capability_map_validates_and_is_path_policed(  # type: ignore[no-untyped-def]
    real_case: RealCase, monkeypatch, tmp_path
) -> None:
    _isolate_host(monkeypatch, present=set(), home=tmp_path)
    run, evidence = real_case()
    target = write_agent_capability_map(run.root, settings=load_settings(), evidence_root=evidence)
    assert target == run.context / "agent_capabilities.json"
    reloaded = AgentCapabilityMap.model_validate_json(target.read_text(encoding="utf-8"))
    assert reloaded.chosen == "deterministic_executor"  # nothing present → floor


def test_doctor_agents_section_prints_and_is_not_fail_closed(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present=set(), home=tmp_path)
    code = run_doctor(agents=True, settings=load_settings())
    out = capsys.readouterr().out
    assert "Coding agents (onboarding)" in out
    assert "default agent (this config):" in out
    assert code == 0  # absent agents are informational, never a fail-closed failure


def test_cli_agents_list_and_inspect(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _isolate_host(monkeypatch, present={"gemini"}, home=tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    from siftmesh_core.cli import app

    runner = CliRunner()
    listed = runner.invoke(app, ["agents", "list"])
    assert listed.exit_code == 0
    assert "gemini_headless" in listed.stdout
    assert "executor default (this config):" in listed.stdout
    assert "tier-2 judge:" in listed.stdout  # the judge purpose is surfaced too (Epic Q judge)

    inspected = runner.invoke(app, ["agents", "inspect", "gemini"])  # friendly alias accepted
    assert inspected.exit_code == 0
    assert "gemini_headless" in inspected.stdout
    assert "mcp_strategy" in inspected.stdout
    assert "native deny" in inspected.stdout  # the sandbox flags are surfaced

    unknown = runner.invoke(app, ["agents", "inspect", "nope"])
    assert unknown.exit_code == 1


def test_app_has_agents_group() -> None:
    from siftmesh_core.cli import app

    assert isinstance(app, typer.Typer)
    names = {g.name for g in app.registered_groups}
    assert "agents" in names

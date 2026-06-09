"""F7/F8 — generic shell + live (claude/opencode) adapters (mocked; no live run)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from siftmesh_core.adapters import get_adapter
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter, _build_claude_argv
from siftmesh_core.config import load_settings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract
from siftmesh_core.schemas.task_result import TaskResult

RealCase = Callable[..., tuple[RunPaths, Path]]


def _contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        role="evtx_security_executor",
        objective="Parse Security log",
        assigned_agent_profile="claude_headless",
        allowed_tools=["parse_evtx_security"],
        input_artifacts=[InputArtifact(path="Security.evtx", sha256="a" * 64)],
        safety_policy=SafetyPolicy(),
    )


def test_claude_argv_built_correctly(tmp_path: Path) -> None:
    argv = _build_claude_argv("claude", "do it", tmp_path / "mcp.json", ["parse_evtx_security"])
    assert argv[0] == "claude" and "-p" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--mcp-config" in argv
    assert "--permission-mode" in argv  # I6: non-interactive
    assert any("mcp__siftmesh__parse_evtx_security" in a for a in argv)


def test_claude_absent_cli_falls_to_floor(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # No claude CLI / key in CI → registry must hand back the deterministic floor.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = get_adapter("claude_headless", settings=load_settings())
    assert adapter.profile_id == "deterministic_executor"


def test_claude_adapter_unavailable_without_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ClaudeHeadlessAdapter(settings=load_settings()).available() is False


def test_claude_execute_parses_json_envelope(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        payload = json.dumps({"result": "done", "is_error": False, "session_id": "s1"})
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert isinstance(result, TaskResult)
    assert result.status == "success"


def test_generic_shell_echo_agent_roundtrip(real_case: RealCase, tmp_path: Path) -> None:
    run, evidence = real_case()
    # An "echo agent" script: reads prompt (arg1), writes a valid TaskResult to arg2.
    agent = tmp_path / "echo_agent.py"
    agent.write_text(
        "import sys, json\n"
        "open(sys.argv[2], 'w').write(json.dumps({\n"
        "  'task_id':'TASK-001','profile':'generic_shell','adapter':'generic_shell',\n"
        "  'attempt':1,'status':'success','tool_call_ids':[],'claims':[],\n"
        "  'started_utc':'2026-01-01T00:00:00Z','ended_utc':'2026-01-01T00:00:00Z'}))\n",
        encoding="utf-8",
    )
    # Our argv is [cmd, prompt, result]; wrap the python invocation in an executable shim.
    wrapper = tmp_path / "agent.sh"
    wrapper.write_text(f'#!/bin/sh\nexec "{__import__("sys").executable}" "{agent}" "$1" "$2"\n')
    wrapper.chmod(0o755)
    settings = load_settings(generic_agent_cmd=str(wrapper))
    adapter = get_adapter("generic_shell", settings=settings)
    assert adapter.profile_id == "generic_shell"  # available since wrapper exists
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=settings)
    contract = _contract().model_copy(update={"assigned_agent_profile": "generic_shell"})
    ref = adapter.run(contract, ctx)
    assert ref.status == "success"
    assert run.result_path("TASK-001").is_file()


def test_generic_shell_absent_agent_falls_to_floor() -> None:
    settings = load_settings(generic_agent_cmd=None)
    assert get_adapter("generic_shell", settings=settings).profile_id == "deterministic_executor"

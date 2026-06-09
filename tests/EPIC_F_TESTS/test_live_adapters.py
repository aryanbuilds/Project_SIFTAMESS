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


def test_mcp_config_launchable_and_absolute(real_case: RealCase) -> None:
    # The MCP server must be launchable by the agent subprocess (NOT bare 'siftmesh', which is not
    # on PATH) and the run-scoping roots must be absolute so the server resolves them from any cwd.
    import json
    import sys

    run, evidence = real_case()
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    cfg = json.loads(adapter._write_mcp_config(ctx).read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["siftmesh"]
    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "siftmesh_core.cli", "mcp-serve"]
    assert Path(server["env"]["SIFTMESH_RUN_ROOT"]).is_absolute()
    assert Path(server["env"]["SIFTMESH_EVIDENCE_ROOT"]).is_absolute()


_AUTH_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


def test_claude_absent_cli_falls_to_floor(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # No claude auth (env or logged-in CLI) → registry must hand back the deterministic floor.
    for var in _AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("siftmesh_core.adapters.claude_adapter._claude_logged_in", lambda: False)
    adapter = get_adapter("claude_headless", settings=load_settings())
    assert adapter.profile_id == "deterministic_executor"


def test_claude_adapter_unavailable_without_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for var in _AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("siftmesh_core.adapters.claude_adapter._claude_logged_in", lambda: False)
    assert ClaudeHeadlessAdapter(settings=load_settings()).available() is False


def test_claude_available_when_cli_logged_in(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # No env var, but the CLI is logged in (credentials.json) -> usable (claude -p reads it).
    monkeypatch.setattr(
        "siftmesh_core.adapters.claude_adapter.shutil.which", lambda p: "/usr/bin/claude"
    )
    for var in _AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("siftmesh_core.adapters.claude_adapter._claude_logged_in", lambda: True)
    assert ClaudeHeadlessAdapter(settings=load_settings()).available() is True


def test_claude_execute_captures_anchored_claims(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sub-token")  # subscription auth path
    claims_payload = json.dumps(
        {
            "claims": [
                {
                    "claim": "PowerShell EncodedCommand executed",
                    "status": "confirmed",
                    "confidence": 0.9,
                    "evidence_type": "evtx",
                    "source_artifact": "Security.evtx",
                    "source_sha256": "a" * 64,
                    "tool_name": "parse_evtx_security",
                    "tool_call_id": "TOOL-001",
                    "supporting_evidence_refs": ["TOOL-001"],
                }
            ]
        }
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        payload = json.dumps({"result": claims_payload, "is_error": False, "session_id": "s1"})
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert isinstance(result, TaskResult)
    assert result.status == "success"
    assert len(result.claims) == 1
    assert result.claims[0].status == "confirmed"
    assert result.claims[0].tool_call_id == "TOOL-001"  # the real anchor the tool returned


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


def test_generic_shell_absent_agent_falls_to_floor(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Force the live adapters unavailable so the chain resolves to the floor regardless of the box
    # (a logged-in claude CLI would otherwise be a valid earlier link in the preference chain).
    from siftmesh_core.adapters.opencode_adapter import OpenCodeHeadlessAdapter

    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(OpenCodeHeadlessAdapter, "available", lambda self: False)
    settings = load_settings(generic_agent_cmd=None)
    assert get_adapter("generic_shell", settings=settings).profile_id == "deterministic_executor"

"""L5f — bypass test: live-agent harness sandbox (threat T2/T5 · OWASP LLM06 · ASI03/ASI05).

Pure-function inspection of the argv/config the adapter WOULD launch — NO subprocess, NO live agent
(CLAUDE §2B): the sandbox is an architectural constraint, so we assert the constraint, not a live
run. Encodes the four REAL bugs as permanent regression scenarios: 5dh9 (agent had Edit/Write and
edited source), 8tcx (bare 'siftmesh' not on PATH -> zero tools), bhyv (derived artifact
unreadable when evidence_root!=run_root), 95q9 (available() rejected a logged-in CLI). Unlike CAO,
no '--yolo' turns the sandbox off. Plus operational edge cases (timeout / bad-JSON fail closed).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.claude_adapter import (
    _DISALLOWED_TOOLS,
    ClaudeHeadlessAdapter,
    _build_claude_argv,
    _claude_logged_in,
)
from siftmesh_core.config import load_settings
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.task import InputArtifact, SafetyPolicy, TaskContract

DispatchedCase = Callable[..., tuple[RunPaths, Path]]
_AUTH_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


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


def _argv() -> list[str]:
    return _build_claude_argv(
        "claude", "investigate", Path("/tmp/mcp.json"), ["parse_evtx_security"]
    )


# ── 5dh9: the agent can never edit SIFTMesh source / run shell / reach the web ─


def test_5dh9_file_mutation_tools_denied() -> None:
    # The rogue-edit incident: the agent had Edit/Write. Every file-mutating built-in is denied.
    for builtin in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        assert builtin in _DISALLOWED_TOOLS
        assert builtin in _argv()


def test_5dh9_shell_and_web_and_spawn_denied() -> None:
    for builtin in ("Bash", "BashOutput", "KillShell", "WebFetch", "WebSearch", "Task", "Agent"):
        assert builtin in _argv()


def test_allowedtools_contains_only_mcp_siftmesh() -> None:
    argv = _argv()
    allowed_value = argv[argv.index("--allowedTools") + 1]
    entries = allowed_value.split(",")
    assert entries  # non-empty
    assert all(e.startswith("mcp__siftmesh__") for e in entries), entries  # zero built-ins leak in


def test_sandbox_flags_present() -> None:
    argv = _argv()
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--disallowedTools" in argv


def test_executor_never_zeroes_the_tool_universe() -> None:
    # Regression (Project_SIFTAMESS, claude v2.1.177): the executor passed `--tools ""`, which sets
    # the AVAILABLE tool universe to empty and disables the typed mcp__siftmesh__* tools as well.
    # The agent then got zero tools, emitted `<invoke name="Bash">` as text, never called a tool,
    # and the critic looped on empty results. The executor must never emit an empty `--tools`.
    argv = _argv()
    if "--tools" in argv:  # if ever reintroduced, it must NOT be empty
        assert argv[argv.index("--tools") + 1] != "", "empty --tools zeroes the MCP tool universe"
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert any(e.startswith("mcp__siftmesh__") for e in allowed)  # typed tools still exposed


def test_gssw_ambient_hooks_disabled() -> None:
    # gssw: the user's ambient ~/.claude lifecycle hooks must NOT fire during the governed run —
    # `--settings {"disableAllHooks": true}` suppresses them while preserving subscription auth.
    import json

    argv = _argv()
    assert "--settings" in argv
    settings_value = argv[argv.index("--settings") + 1]
    assert json.loads(settings_value).get("disableAllHooks") is True
    assert "--bare" not in argv  # --bare would break subscription auth (our hard constraint)


def test_gssw_advisory_call_also_disables_hooks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # The tool-less advisory call (Tier-2 judge / synthesis) is also a headless `claude -p`,
    # so it must likewise suppress ambient hooks.
    import json
    import subprocess as _sp

    from siftmesh_core.adapters.claude_adapter import invoke_claude_text

    captured: dict[str, object] = {}

    def _fake(argv, **_k):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return _sp.CompletedProcess(args=argv, returncode=0, stdout='{"result": "ok"}', stderr="")

    monkeypatch.setattr(
        "siftmesh_core.adapters.claude_adapter.shutil.which", lambda _p: "/bin/claude"
    )
    monkeypatch.setattr(_sp, "run", _fake)
    invoke_claude_text("judge this", load_settings())
    argv = captured["argv"]
    assert "--settings" in argv  # type: ignore[operator]
    val = argv[argv.index("--settings") + 1]  # type: ignore[union-attr]
    assert json.loads(val).get("disableAllHooks") is True


# ── 8tcx + bhyv: MCP launch + dual-root scoping ──────────────────────────────


def test_8tcx_mcp_launch_is_module_not_bare_siftmesh(dispatched_case: DispatchedCase) -> None:
    import json
    import sys

    run, evidence = dispatched_case(dispatch=False)
    assert Path(evidence).resolve() != Path(run.root).resolve()  # evidence_root != run_root
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    cfg = json.loads(adapter._write_mcp_config(ctx).read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["siftmesh"]
    assert server["command"] == sys.executable  # NOT bare 'siftmesh' (not on PATH)
    assert server["args"] == ["-m", "siftmesh_core.cli", "mcp-serve"]
    run_env = Path(server["env"]["SIFTMESH_RUN_ROOT"])
    evi_env = Path(server["env"]["SIFTMESH_EVIDENCE_ROOT"])
    assert run_env.is_absolute() and evi_env.is_absolute()
    assert run_env == Path(run.root).resolve()
    assert evi_env == Path(evidence).resolve()  # distinct roots both passed correctly (bhyv)


# ── 95q9: a logged-in CLI is usable (no env var required) ─────────────────────


def test_95q9_available_with_credentials_file_only(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))  # Path.home() reads $HOME on POSIX
    monkeypatch.setattr(
        "siftmesh_core.adapters.claude_adapter.shutil.which", lambda _p: "/usr/bin/claude"
    )
    for var in _AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    assert _claude_logged_in() is True  # the REAL credential-store check
    assert ClaudeHeadlessAdapter(settings=load_settings()).available() is True


def test_available_false_when_cli_absent(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("siftmesh_core.adapters.claude_adapter.shutil.which", lambda _p: None)
    for var in _AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    assert ClaudeHeadlessAdapter(settings=load_settings()).available() is False  # fails closed


# ── operational edge cases (fail closed, never crash) ────────────────────────


def test_timeout_returns_error_result(dispatched_case: DispatchedCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_case(dispatch=False)

    def _raise(*_a: object, **_k: object) -> object:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(subprocess, "run", _raise)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert result.status == "error"
    assert "agent_failed_or_timeout" in result.errors


def test_bad_json_returns_error_and_persists_raw(
    dispatched_case: DispatchedCase, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_case(dispatch=False)

    def _fake(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="not json{", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert result.status == "error"
    assert "agent_bad_json" in result.errors
    # the raw envelope is still persisted for audit even on a parse failure
    assert (run.root / "results" / "TASK-001.agent_raw.json").is_file()


def test_execute_persists_stderr_for_debugging(
    dispatched_case: DispatchedCase, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # MCP connection/startup errors go to stderr; the adapter used to discard it, which hid the
    # root cause of the no-tools failure. Non-empty stderr must be persisted for audit/debugging.
    run, evidence = dispatched_case(dispatch=False)

    def _fake(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        envelope = {"is_error": False, "subtype": "success", "result": json.dumps({"claims": []})}
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(envelope), stderr="MCP server failed: boom"
        )

    monkeypatch.setattr(subprocess, "run", _fake)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    adapter._execute(_contract(), ctx)
    stderr_path = run.root / "results" / "TASK-001.agent_stderr.txt"
    assert stderr_path.is_file() and "MCP server failed" in stderr_path.read_text(encoding="utf-8")


# ── session isolation: a headless run never bleeds an ambient/concurrent Claude session ──


def test_argv_pins_fresh_isolated_session() -> None:
    # The live-run contamination bug: a headless run returned an interactive transcript. Each
    # dispatch must pin a BRAND-NEW session id and never persist it to the on-disk cache.
    a1, a2 = _argv(), _argv()
    for argv in (a1, a2):
        assert "--session-id" in argv
        assert "--no-session-persistence" in argv
        assert "--bare" not in argv  # --bare would break subscription auth
    sid1 = a1[a1.index("--session-id") + 1]
    sid2 = a2[a2.index("--session-id") + 1]
    assert sid1 != sid2 and len(sid1) == 36  # a fresh uuid4 per call


def test_execute_minimal_env_drops_foreign_secrets(
    dispatched_case: DispatchedCase, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    run, evidence = dispatched_case(dispatch=False)
    captured: dict[str, object] = {}

    def _fake(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        envelope = {"is_error": False, "subtype": "success", "result": json.dumps({"claims": []})}
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=json.dumps(envelope), stderr=""
        )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")  # auth: must survive
    monkeypatch.setenv("OPENAI_API_KEY", "leak-me")  # foreign secret: must be dropped
    monkeypatch.setattr(subprocess, "run", _fake)
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    adapter._execute(_contract(), ctx)

    env = captured["env"]
    assert isinstance(env, dict)
    assert env.get("ANTHROPIC_API_KEY") == "sk-test"  # Claude auth kept
    assert "OPENAI_API_KEY" not in env  # other-provider secret never inherited
    assert "PATH" in env and "HOME" in env  # base env + ~/.claude creds path kept
    argv = captured["argv"]
    assert "--session-id" in argv and "--no-session-persistence" in argv  # fresh isolated session

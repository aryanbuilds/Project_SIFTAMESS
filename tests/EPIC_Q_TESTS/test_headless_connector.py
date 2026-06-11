"""Epic Q round 1 — the config-driven, agent-NEUTRAL headless connector (mocked; no live run)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from siftmesh_core.adapters import get_adapter
from siftmesh_core.adapters.base import AdapterContext
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter
from siftmesh_core.adapters.headless import (
    CodexHeadlessAdapter,
    GeminiHeadlessAdapter,
    HeadlessAdapter,
    extract_agent_text,
)
from siftmesh_core.adapters.opencode_adapter import OpenCodeHeadlessAdapter
from siftmesh_core.adapters.profiles import load_profiles
from siftmesh_core.cli import _agent_overrides
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
        assigned_agent_profile="gemini_headless",
        allowed_tools=["parse_evtx_security"],
        input_artifacts=[InputArtifact(path="Security.evtx", sha256="a" * 64)],
        safety_policy=SafetyPolicy(),
    )


def _anchored_payload() -> str:
    return json.dumps(
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


# ---- argv built from the profile recipe (one adapter, many agents) ----


def test_gemini_argv_carries_prompt_and_deny_flags() -> None:
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    prof = load_profiles()["gemini_headless"]
    argv = adapter._build_argv(prof, "do it", None)
    # launch prefix + prompt + extra_argv + native-tool deny flags (no model pinned → auto-route).
    assert argv == [
        "gemini",
        "-p",
        "do it",
        "--output-format",
        "json",
        "--approval-mode",
        "default",
    ]


def test_codex_argv_pins_model_and_sandbox_flags() -> None:
    adapter = CodexHeadlessAdapter(settings=load_settings())
    prof = load_profiles()["codex_headless"]
    argv = adapter._build_argv(prof, "go", None)
    assert argv[:3] == ["codex", "exec", "go"]
    assert argv[3:5] == ["--model", "gpt-5.5"]  # model now actually sent (was silently dropped)
    assert "--skip-git-repo-check" in argv  # mandatory: run dirs are not git repos
    assert (
        argv[-4:] == ["--sandbox", "read-only", "--ask-for-approval", "never"]
        or "--ephemeral" in argv
    )
    assert "--sandbox" in argv and "read-only" in argv  # OS-enforced no-write/no-net sandbox


# ---- tolerant output extraction (robust to per-CLI JSON shape drift) ----


def test_extract_agent_text_envelope_result() -> None:
    inner = _anchored_payload()
    assert extract_agent_text(json.dumps({"result": inner}), "agent_json") == inner


def test_extract_agent_text_envelope_response_key() -> None:
    assert extract_agent_text(json.dumps({"response": "hello"}), "agent_json") == "hello"


def test_extract_agent_text_raw_passthrough() -> None:
    raw = _anchored_payload()  # agent printed the claims JSON directly, no envelope
    assert extract_agent_text(raw, "agent_json") == raw


def test_extract_agent_text_ndjson_concat() -> None:
    stream = '{"text": "Power"}\n{"part": {"text": "Shell"}}\n'
    assert extract_agent_text(stream, "opencode_json") == "PowerShell"


# ---- _execute: capture anchored claims; honest downgrade/retry; fail-soft ----


def test_gemini_execute_captures_anchored_claims(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()

    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        envelope = json.dumps({"result": _anchored_payload(), "is_error": False})
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert isinstance(result, TaskResult)
    assert result.status == "success"
    assert len(result.claims) == 1
    assert result.claims[0].status == "confirmed"
    assert result.claims[0].tool_call_id == "TOOL-001"


def test_headless_unanchored_claim_becomes_unsupported(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # A non-Claude agent cannot smuggle an unanchored 'fact' past the firewall: a confirmed claim
    # with no source hash / tool_call_id is normalized to 'unsupported' (never promoted).
    run, evidence = real_case()
    unanchored = json.dumps(
        {"claims": [{"claim": "host was compromised", "status": "confirmed", "confidence": 0.99}]}
    )

    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"result": unanchored}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert [c.status for c in result.claims] == ["unsupported"]


def test_headless_unparseable_output_triggers_retry(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()

    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="I cannot help.", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert result.status == "retry_required"


def test_headless_timeout_returns_error(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()

    def boom(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="gemini", timeout=1)

    monkeypatch.setattr(subprocess, "run", boom)
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert result.status == "error"
    assert result.errors == ["agent_failed_or_timeout"]


# ---- availability + registry fallback ------------------------------------------------------------


def test_available_requires_cli_auth_and_sandbox(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setenv("HOME", str(tmp_path))  # no cached ~/.gemini creds
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert adapter.available() is True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert adapter.available() is False  # CLI present but no auth env / cached creds
    monkeypatch.setattr(shutil, "which", lambda c: None)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert adapter.available() is False  # auth present but no CLI


def test_unsandboxed_profile_fails_closed(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A headless recipe with NO native-tool deny flags must never be dispatchable (evidence safety).
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    prof = load_profiles()["gemini_headless"].model_copy(update={"native_tool_argv": []})
    monkeypatch.setattr(adapter, "profile", lambda: prof)
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "x")  # present + authed, but unsandboxed
    assert adapter.available() is False


def test_gemini_unavailable_falls_through_chain_to_floor(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Requested gemini + every live agent down → the registry hands back the deterministic floor.
    monkeypatch.setattr(HeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(OpenCodeHeadlessAdapter, "available", lambda self: False)
    adapter = get_adapter("gemini_headless", settings=load_settings())
    assert adapter.profile_id == "deterministic_executor"


def test_agent_override_falls_back_only_to_floor() -> None:
    # An operator who picks one agent is NEVER silently downgraded to a DIFFERENT live agent —
    # the only fallback is the deterministic floor.
    ov = _agent_overrides("gemini")
    assert ov["executor_selection"] == "auto"
    assert ov["agent_preference"] == ["gemini_headless", "deterministic_executor"]


def test_agent_override_rejects_unknown_agent() -> None:
    import typer

    with pytest.raises(typer.BadParameter):
        _agent_overrides("gemeni")  # typo must error, not silently dispatch a different agent


# ---- correctness: codex JSONL stream + nested envelope recovery ----


def test_codex_jsonl_stream_yields_claims(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # `codex exec --json` is a JSONL EVENT STREAM with the final message escaped inside an event;
    # the extractor must recover the {claims} payload (else every codex run is retry_required).
    run, evidence = real_case()
    inner = _anchored_payload()
    stream = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {"type": "item.completed", "item": {"type": "agent_message", "text": inner}}
            ),
            json.dumps({"type": "turn.completed"}),
        ]
    )

    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stream, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = CodexHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    result = adapter._execute(_contract(), ctx)
    assert result.status == "success"
    assert result.claims[0].tool_call_id == "TOOL-001"


def test_extract_recovers_nested_claims_envelope() -> None:
    # A structured result that nests claims under an unknown key must still be recovered.
    nested = json.dumps({"data": {"claims": [{"claim": "z", "status": "unsupported"}]}})
    out = extract_agent_text(nested, "agent_json")
    assert json.loads(out)["claims"][0]["claim"] == "z"


# ---- evidence safety: minimized env + run-scoped cwd ----


def test_execute_minimizes_env_and_pins_cwd(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, evidence = real_case()
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-secret")  # must NOT reach the gemini child
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "cloud-secret")  # must NOT reach the child
    captured: dict[str, object] = {}

    def fake_run(*_a: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"result": _anchored_payload()}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    ctx = AdapterContext(run=run, evidence_root=evidence, settings=load_settings())
    adapter._execute(_contract(), ctx)

    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert child_env.get("GEMINI_API_KEY") == "gem-key"  # its own credential passes through
    assert "ANTHROPIC_API_KEY" not in child_env  # other providers' secrets are stripped
    assert "AWS_SECRET_ACCESS_KEY" not in child_env
    cwd = Path(str(captured["cwd"])).resolve()
    assert cwd.is_relative_to(run.root.resolve())  # never the operator CWD; bounded to the run dir

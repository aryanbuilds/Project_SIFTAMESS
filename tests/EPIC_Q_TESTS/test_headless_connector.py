"""Epic Q round 1 — the config-driven, agent-NEUTRAL headless connector (mocked; no live run)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

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


def test_gemini_argv_built_from_profile() -> None:
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    prof = load_profiles()["gemini_headless"]
    argv = adapter._build_argv(prof, "do it", None)
    # launch_argv prefix + prompt + model_flag/model + extra_argv, in order.
    assert argv == ["gemini", "-p", "do it", "--model", "gemini-2.5-pro", "--output-format", "json"]


def test_codex_argv_omits_model_without_model_flag() -> None:
    adapter = CodexHeadlessAdapter(settings=load_settings())
    prof = load_profiles()["codex_headless"]
    argv = adapter._build_argv(prof, "go", None)
    # codex has a model but NO model_flag → the model id must not be injected blindly.
    assert argv == ["codex", "exec", "go", "--json"]
    assert "gpt-5-codex" not in argv


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


def test_available_requires_cli_and_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    adapter = GeminiHeadlessAdapter(settings=load_settings())
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert adapter.available() is True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert adapter.available() is False  # CLI present but no auth env
    monkeypatch.setattr(shutil, "which", lambda c: None)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert adapter.available() is False  # auth present but no CLI


def test_gemini_unavailable_falls_through_chain_to_floor(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Requested gemini + every live agent down → the registry hands back the deterministic floor.
    monkeypatch.setattr(HeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(OpenCodeHeadlessAdapter, "available", lambda self: False)
    adapter = get_adapter("gemini_headless", settings=load_settings())
    assert adapter.profile_id == "deterministic_executor"


def test_agent_override_reorders_chain_neutrally() -> None:
    ov = _agent_overrides("gemini")
    assert ov["executor_selection"] == "auto"
    pref = ov["agent_preference"]
    assert pref[0] == "gemini_headless"  # selected agent leads
    assert pref[-1] == "deterministic_executor"  # floor always last
    assert set(pref) == {
        "gemini_headless",
        "claude_headless",
        "opencode_headless",
        "codex_headless",
        "openclaw_headless",
        "deterministic_executor",
    }

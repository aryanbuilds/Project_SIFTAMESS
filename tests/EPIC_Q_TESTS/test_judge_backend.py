"""Provider-flexible Tier-2 judge backend (advisory; fail-soft; never promotes). Mocked, no LLM."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import siftmesh_core.adapters.judge as judge_mod
from siftmesh_core.adapters.judge import invoke_judge_text, judge_ready, parse_judge
from siftmesh_core.cli import _judge_overrides
from siftmesh_core.config import global_config_path, load_settings, save_agent_selection

# ---- parse + readiness ----


def test_parse_judge_forms() -> None:
    assert parse_judge(None) == ("cli", "claude")
    assert parse_judge("gemini") == ("cli", "gemini")
    assert parse_judge("cli:codex") == ("cli", "codex")
    assert parse_judge("litellm:gemini/gemini-2.5-pro") == ("litellm", "gemini/gemini-2.5-pro")


def test_judge_ready_litellm_absent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(judge_mod.importlib.util, "find_spec", lambda name: None)
    ready, label = judge_ready(load_settings(judge="litellm:openai/gpt-5.5"))
    assert ready is False
    assert "llm` extra" in label


# ---- dispatch ----


def test_default_routes_to_claude(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(judge_mod, "invoke_claude_text", lambda p, s, timeout=None: "CLAUDE-OUT")
    assert invoke_judge_text("hi", load_settings()) == "CLAUDE-OUT"  # judge=None → claude


def test_cli_judge_builds_tool_less_argv(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=json.dumps({"response": "GEMINI-JUDGE"}), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = invoke_judge_text("judge this", load_settings(judge="cli:gemini"))
    assert out == "GEMINI-JUDGE"
    argv = captured["argv"]
    assert argv[:3] == ["gemini", "-p", "judge this"]
    assert "--mcp-config" not in argv  # tool-less: never wires the typed tools
    assert "--approval-mode" in argv and "default" in argv  # native-tool deny still applied


def test_litellm_judge_routes_via_sdk(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import litellm

    def fake_completion(model, messages, timeout=None):  # type: ignore[no-untyped-def]
        assert model == "openai/gpt-5.5"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="LITELLM-JUDGE"))]
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    out = invoke_judge_text("x", load_settings(judge="litellm:openai/gpt-5.5"))
    assert out == "LITELLM-JUDGE"


def test_litellm_judge_fail_soft_on_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import litellm

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise RuntimeError("no API key / provider down")

    monkeypatch.setattr(litellm, "completion", boom)
    assert invoke_judge_text("x", load_settings(judge="litellm:openai/gpt-5.5")) is None


def test_cli_judge_fail_soft_when_cli_absent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(shutil, "which", lambda c: None)
    assert invoke_judge_text("x", load_settings(judge="cli:gemini")) is None


def test_opencode_judge_ready_and_argv(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Regression (live 2026-06-11): opencode's profile has empty launch_argv (its executor builds
    # argv specially), so the generic path mis-reported it unavailable + never invoked it. The judge
    # must probe the opencode CLI directly and use `opencode run … --format json`.
    import json as _json

    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        out = _json.dumps({"type": "text", "part": {"text": "OPENCODE-JUDGE"}})
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    s = load_settings(
        judge="cli:opencode", agent_models={"opencode_headless": "opencode-go/glm-5.1"}
    )
    assert judge_ready(s) == (True, "cli:opencode")  # no longer mis-reported as unavailable
    assert invoke_judge_text("judge this", s) == "OPENCODE-JUDGE"
    argv = captured["argv"]
    assert "run" in argv and "judge this" in argv
    assert argv[argv.index("--model") + 1] == "opencode-go/glm-5.1"  # per-provider model honored
    assert "--format" in argv and "json" in argv
    assert "--mcp-config" not in argv  # tool-less


# ---- run_tier2_judge: fail-SOFT skip (logs, never fails, never promotes) ----


def test_tier2_judge_skips_and_logs_when_unavailable(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import shutil as _sh

    import siftmesh_core.orchestrator.critic as critic_mod
    from siftmesh_core.ledgers.audit_log import open_orchestration_log
    from siftmesh_core.ledgers.claim_ledger import read_claims
    from siftmesh_core.orchestrator.critic import run_tier2_judge
    from siftmesh_core.run_dir import RunPaths

    golden = Path(__file__).resolve().parents[1] / "golden" / "recorded_run" / "RUN-GOLDEN"
    run = RunPaths(root=tmp_path / "RUN-LIVE")
    _sh.copytree(golden, run.root)
    before = list(read_claims(run.root))  # promoted claims exist in the golden run

    monkeypatch.setattr(critic_mod, "invoke_judge_text", lambda *a, **k: None)  # judge unavailable
    audit = open_orchestration_log(run.orchestration_events, run.run_id)
    acted = run_tier2_judge(run, settings=load_settings(), evidence_root=None, audit=audit)

    assert acted == 0  # nothing acted on
    assert (
        list(read_claims(run.root)) == before
    )  # Tier-1 promotions untouched (never demoted/changed)
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "tier2_judge_skipped" in events  # logged the skip, did not raise / fail the run


# ---- per-purpose selection + persistence ----


def test_judge_overrides() -> None:
    assert _judge_overrides(None) == {}
    assert _judge_overrides("gemini") == {"judge": "cli:gemini", "llm_critic_enabled": True}
    assert _judge_overrides("litellm:openai/gpt-5.5") == {
        "judge": "litellm:openai/gpt-5.5",
        "llm_critic_enabled": True,
    }
    assert _judge_overrides("off") == {"llm_critic_enabled": False}


def test_judge_persists_to_config(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(cwd)
    for var in ("SIFTMESH_JUDGE", "SIFTMESH_LLM_CRITIC_ENABLED"):
        monkeypatch.delenv(var, raising=False)

    path = save_agent_selection(
        "auto",
        ["gemini_headless", "deterministic_executor"],
        scope="global",
        judge="litellm:gemini/gemini-2.5-pro",
        llm_critic_enabled=True,
    )
    assert path == global_config_path()
    s = load_settings()
    assert s.judge == "litellm:gemini/gemini-2.5-pro"
    assert s.llm_critic_enabled is True

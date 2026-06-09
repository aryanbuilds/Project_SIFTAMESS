"""Epic I multi-agent layer — profile resolution, fallback chain, per-agent model, dual auth."""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.adapters.base import get_adapter, resolve_profile
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter, _build_claude_argv
from siftmesh_core.adapters.opencode_adapter import OpenCodeHeadlessAdapter, _build_opencode_argv
from siftmesh_core.cli import _agent_overrides
from siftmesh_core.config import load_settings
from siftmesh_core.run_dir import new_run_dir


def test_resolve_profile_precedence() -> None:
    det = load_settings()  # default executor_selection == "deterministic"
    assert resolve_profile("x", settings=det) == "deterministic_executor"
    assert resolve_profile("x", settings=det, cli_override="claude_headless") == "claude_headless"
    live = load_settings(executor_selection="auto")
    assert resolve_profile("x", settings=live) == "claude_headless"  # head of preference chain
    pinned = load_settings(executor_selection="auto", role_profiles={"critic": "opencode_headless"})
    assert resolve_profile("critic", settings=pinned) == "opencode_headless"  # per-role pin


def test_fallback_chain_walks_to_floor_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(OpenCodeHeadlessAdapter, "available", lambda self: False)
    run = new_run_dir(base=tmp_path / "case_runs")
    adapter = get_adapter("claude_headless", settings=load_settings(), run=run)
    assert adapter.profile_id == "deterministic_executor"  # claude→opencode→floor
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert events.count("adapter_unavailable") >= 2  # claude + opencode skips audited


def test_claude_dual_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "siftmesh_core.adapters.claude_adapter.shutil.which", lambda p: "/usr/bin/claude"
    )
    adapter = ClaudeHeadlessAdapter(settings=load_settings())
    for var in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert not adapter.available()  # CLI present but no auth
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sub-token")  # subscription token alone
    assert adapter.available()
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-key")  # API key alone
    assert adapter.available()


def test_per_agent_model_in_argv(tmp_path: Path) -> None:
    claude = _build_claude_argv(
        "claude", "go", tmp_path / "mcp.json", ["parse_evtx_security"], model="claude-opus-4-8"
    )
    assert "--model" in claude and "claude-opus-4-8" in claude
    opencode = _build_opencode_argv("opencode", "go", "anthropic/claude-sonnet-4-6")
    assert opencode[:2] == ["opencode", "run"]
    assert "--model" in opencode and "anthropic/claude-sonnet-4-6" in opencode
    assert "--format" in opencode and "json" in opencode  # I6: not --output-format


def test_agent_overrides_cli() -> None:
    assert _agent_overrides(None) == {}
    claude = _agent_overrides("claude")
    assert claude["executor_selection"] == "auto"
    assert claude["agent_preference"][0] == "claude_headless"  # type: ignore[index]
    assert _agent_overrides("opencode")["agent_preference"][0] == "opencode_headless"  # type: ignore[index]
    assert _agent_overrides("deterministic") == {"executor_selection": "deterministic"}

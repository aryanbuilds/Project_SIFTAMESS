"""I2 — registry resolution falls closed to the deterministic floor + audits adapter_unavailable."""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.adapters.base import get_adapter
from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter
from siftmesh_core.adapters.opencode_adapter import OpenCodeHeadlessAdapter
from siftmesh_core.config import load_settings
from siftmesh_core.run_dir import new_run_dir


def _no_live_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force both live adapters unavailable so the test is independent of ambient CLI/login."""
    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    monkeypatch.setattr(OpenCodeHeadlessAdapter, "available", lambda self: False)


def test_unknown_profile_falls_back_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_live_agents(monkeypatch)
    run = new_run_dir(base=tmp_path / "case_runs")
    adapter = get_adapter("does_not_exist", settings=load_settings(), run=run)
    assert adapter.profile_id == "deterministic_executor"
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "adapter_unavailable" in events and "unknown_profile" in events


def test_unavailable_cli_falls_back_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeHeadlessAdapter, "available", lambda self: False)
    run = new_run_dir(base=tmp_path / "case_runs")
    adapter = get_adapter("claude_headless", settings=load_settings(), run=run)
    assert adapter.profile_id == "deterministic_executor"  # fell closed (no CLI/key)
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "adapter_unavailable" in events and "cli_or_key_absent" in events


def test_default_profile_does_not_audit(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    adapter = get_adapter("deterministic_executor", settings=load_settings(), run=run)
    assert adapter.profile_id == "deterministic_executor"
    assert not run.orchestration_events.is_file()  # the floor is no fall-back; nothing logged

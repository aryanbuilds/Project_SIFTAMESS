"""Tier-2 judge extras: judge_remediation + _litellm_text api_base/drop_params passthrough."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from siftmesh_core.adapters import judge as judge_mod
from siftmesh_core.adapters.judge import invoke_judge_text, judge_remediation


def _settings(**kw: object) -> SimpleNamespace:
    base = {"judge": None, "judge_api_base": None, "judge_drop_params": False}
    base.update(kw)
    return SimpleNamespace(**base)


def test_remediation_empty_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge_mod, "judge_ready", lambda s: (True, "ok"))
    assert judge_remediation(_settings(judge="litellm:openai/x")) == []


def test_remediation_cli_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge_mod, "judge_ready", lambda s: (False, "x"))
    assert "claude setup-token" in " ".join(judge_remediation(_settings(judge="cli:claude")))
    assert "opencode auth login" in " ".join(judge_remediation(_settings(judge="cli:opencode")))
    assert "codex login" in " ".join(judge_remediation(_settings(judge="cli:codex")))


def test_remediation_litellm_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge_mod, "judge_ready", lambda s: (False, "x"))
    monkeypatch.setattr(judge_mod.importlib.util, "find_spec", lambda name: None)
    hints = judge_remediation(_settings(judge="litellm:gemini/gemini-pro"))
    assert any("uv sync --extra llm" in h for h in hints)


def test_remediation_litellm_key_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge_mod, "judge_ready", lambda s: (False, "x"))
    monkeypatch.setattr(
        judge_mod.importlib.util, "find_spec", lambda name: object()
    )  # litellm present
    hints = judge_remediation(_settings(judge="litellm:gemini/gemini-pro"))
    assert any("GEMINI_API_KEY" in h for h in hints)


def test_litellm_passthrough_api_base_and_drop_params(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> object:
        captured.update(kwargs)
        msg = SimpleNamespace(content="verdict text")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    settings = _settings(
        judge="litellm:openai/glm-4.6",
        judge_api_base="https://api.opencode.ai/zen/v1",
        judge_drop_params=True,
    )
    out = invoke_judge_text("hello", settings)
    assert out == "verdict text"
    assert captured["model"] == "openai/glm-4.6"
    assert captured["api_base"] == "https://api.opencode.ai/zen/v1"
    assert captured["drop_params"] is True


def test_litellm_no_extras_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    invoke_judge_text("hi", _settings(judge="litellm:gemini/gemini-2.5-pro"))
    assert "api_base" not in captured
    assert "drop_params" not in captured

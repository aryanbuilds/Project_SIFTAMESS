"""Auth helpers: vendor-login command map + LiteLLM key validate/save (validated-before-persist)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from siftmesh_core.secrets_env import read_secrets
from siftmesh_core.tui.auth_actions import (
    auth_command,
    known_providers,
    provider_env_var,
    save_provider_key,
    validate_provider_key,
)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))


def test_auth_command_map() -> None:
    assert auth_command("claude_headless") == ["claude", "setup-token"]
    assert auth_command("opencode_headless") == ["opencode", "auth", "login"]
    assert auth_command("codex_headless") == ["codex", "login"]
    assert auth_command("gemini_headless") is None  # API-key only
    assert auth_command("nope") is None


def test_provider_metadata() -> None:
    assert provider_env_var("gemini") == "GEMINI_API_KEY"
    assert provider_env_var("zen") == "OPENAI_API_KEY"
    assert provider_env_var("unknown") is None
    assert "gemini" in known_providers() and "zen" in known_providers()


def test_validate_unknown_and_empty() -> None:
    assert validate_provider_key("nope", "k")[0] is False
    assert validate_provider_key("gemini", "  ")[0] is False


def test_validate_litellm_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "litellm", None)  # makes `import litellm` raise ImportError
    valid, msg = validate_provider_key("gemini", "sk-x")
    assert valid is None
    assert "llm" in msg


def test_validate_valid_via_models(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    monkeypatch.setattr(litellm, "get_valid_models", lambda **kw: ["m1", "m2", "m3"])
    valid, msg = validate_provider_key("gemini", "sk-good")
    assert valid is True
    assert "3 models" in msg


def test_validate_fallback_check_valid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")

    def boom(**kw: object) -> list[str]:
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(litellm, "get_valid_models", boom)
    monkeypatch.setattr(litellm, "check_valid_key", lambda model, api_key: True)
    valid, _msg = validate_provider_key("openai", "sk-good")
    assert valid is True


def test_validate_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    monkeypatch.setattr(litellm, "get_valid_models", lambda **kw: [])
    monkeypatch.setattr(litellm, "check_valid_key", lambda model, api_key: False)
    valid, msg = validate_provider_key("anthropic", "sk-bad")
    assert valid is False
    assert "rejected" in msg


def test_save_persists_only_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    # valid → persisted + os.environ set
    monkeypatch.setattr(litellm, "get_valid_models", lambda **kw: ["m"])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    saved, _msg = save_provider_key("gemini", "sk-valid")
    assert saved is True
    assert read_secrets().get("GEMINI_API_KEY") == "sk-valid"
    assert "GEMINI_API_KEY" in __import__("os").environ


def test_save_skips_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    litellm = pytest.importorskip("litellm")
    monkeypatch.setattr(litellm, "get_valid_models", lambda **kw: [])
    monkeypatch.setattr(litellm, "check_valid_key", lambda model, api_key: False)
    saved, _msg = save_provider_key("openai", "sk-bad")
    assert saved is False
    assert read_secrets() == {}  # nothing persisted


def test_save_persists_unvalidatable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "litellm", None)
    saved, msg = save_provider_key("gemini", "sk-cannot-check")
    assert saved is True  # persisted even though we couldn't validate
    assert read_secrets().get("GEMINI_API_KEY") == "sk-cannot-check"
    assert "llm" in msg

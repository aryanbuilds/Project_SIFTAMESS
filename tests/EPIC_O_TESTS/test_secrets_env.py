"""Provider-credential env file: 600-perm round-trip + os.environ loading (no-clobber/override)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from siftmesh_core.secrets_env import (
    load_secrets_into_env,
    read_secrets,
    save_secret,
    secrets_env_path,
)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the env file under a temp XDG_CONFIG_HOME so we never touch the real ~/.config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))


def test_path_uses_xdg(tmp_path: Path) -> None:
    assert secrets_env_path() == tmp_path / "cfg" / "siftmesh" / ".env"


def test_save_then_read_round_trip() -> None:
    save_secret("GEMINI_API_KEY", "sk-abc123")
    save_secret("OPENAI_API_KEY", "sk-def456")
    assert read_secrets() == {"GEMINI_API_KEY": "sk-abc123", "OPENAI_API_KEY": "sk-def456"}


def test_file_is_600() -> None:
    path = save_secret("GEMINI_API_KEY", "sk-xyz")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected 600, got {oct(mode)}"


def test_save_merges_not_clobbers() -> None:
    save_secret("GEMINI_API_KEY", "one")
    save_secret("OPENAI_API_KEY", "two")  # must not drop the first
    assert read_secrets() == {"GEMINI_API_KEY": "one", "OPENAI_API_KEY": "two"}
    save_secret("GEMINI_API_KEY", "updated")  # update in place
    assert read_secrets()["GEMINI_API_KEY"] == "updated"


def test_invalid_var_name_rejected() -> None:
    with pytest.raises(ValueError):
        save_secret("BAD=NAME", "x")
    with pytest.raises(ValueError):
        save_secret("", "x")


def test_load_does_not_override_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    save_secret("GEMINI_API_KEY", "from-file")
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")
    loaded = load_secrets_into_env()  # default override=False
    assert "GEMINI_API_KEY" not in loaded
    assert os.environ["GEMINI_API_KEY"] == "from-shell"


def test_load_sets_missing_and_can_override(monkeypatch: pytest.MonkeyPatch) -> None:
    save_secret("OPENAI_API_KEY", "from-file")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    loaded = load_secrets_into_env()
    assert "OPENAI_API_KEY" in loaded
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    # override=True replaces an existing value
    monkeypatch.setenv("OPENAI_API_KEY", "stale")
    load_secrets_into_env(override=True)
    assert os.environ["OPENAI_API_KEY"] == "from-file"


def test_missing_file_is_empty() -> None:
    assert read_secrets() == {}
    assert load_secrets_into_env() == []

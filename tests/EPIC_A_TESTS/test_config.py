"""A3: config loader - precedence (init > env > toml > defaults) + fail-closed."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from siftmesh_core.config import CONFIG_FILENAME, SiftmeshSettings, load_settings


@pytest.fixture(autouse=True)
def clear_siftmesh_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("SIFTMESH_"):
            monkeypatch.delenv(key, raising=False)


def test_defaults() -> None:
    s = load_settings()
    assert s.backend_mode == "real"
    assert s.evidence_mode == "read_only"
    assert s.raw_shell is False
    assert s.allow_destructive_tools is False
    assert s.caps.max_iterations == 3
    assert s.caps.max_tool_runtime_seconds == 300


def test_init_args_override() -> None:
    assert load_settings(backend_mode="sift_lane").backend_mode == "sift_lane"


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIFTMESH_CAPS__MAX_ITERATIONS", "7")
    assert SiftmeshSettings().caps.max_iterations == 7


def test_toml_file_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        'backend_mode = "sift_lane"\n[caps]\nmax_parallel_tasks = 2\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = SiftmeshSettings()

    assert settings.backend_mode == "sift_lane"
    assert settings.caps.max_parallel_tasks == 2


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        'backend_mode = "sift_lane"\n[caps]\nmax_iterations = 4\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIFTMESH_BACKEND_MODE", "auto")
    monkeypatch.setenv("SIFTMESH_CAPS__MAX_ITERATIONS", "9")

    settings = SiftmeshSettings()

    assert settings.backend_mode == "auto"
    assert settings.caps.max_iterations == 9


def test_invalid_backend_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        load_settings(backend_mode="bogus")


def test_unknown_key_rejected_fail_closed() -> None:
    with pytest.raises(ValidationError):
        load_settings(definitely_not_a_field=True)


def test_json_schema_exportable() -> None:
    schema = SiftmeshSettings.model_json_schema()
    assert "backend_mode" in schema["properties"]
    assert "caps" in schema["properties"]

"""A8: doctor checks (fail-closed) + protocol-sift detection (env-only) + one-command --setup."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from siftmesh_core import doctor as doctor_mod
from siftmesh_core.config import load_settings
from siftmesh_core.doctor import FAIL, collect_checks, run_doctor, run_setup
from siftmesh_core.protocol_sift import detect_protocol_sift


def test_core_checks_pass_exit_zero() -> None:
    assert run_doctor() == 0


def test_no_required_failures_in_dev_env() -> None:
    checks = collect_checks()
    names = {c.name for c in checks}
    assert "python >= 3.11" in names
    assert "raw_shell disabled" in names
    assert [c for c in checks if c.status == FAIL] == []


def test_protocol_sift_flag_runs() -> None:
    assert run_doctor(protocol_sift=True) == 0


def test_setup_runs_uv_all_extras_and_creates_symbol_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache" / "vol_symbols"
    settings = load_settings(vol_symbol_dirs=str(cache))
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_setup(settings) == 0
    assert calls == [["/usr/bin/uv", "sync", "--all-extras"]]  # exact, fixed argv
    assert cache.is_dir()  # symbol cache created


def test_setup_fails_closed_without_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: None)
    assert run_setup(load_settings(vol_symbol_dirs=str(tmp_path / "c"))) == 1  # no pip fallback


def test_detect_protocol_sift_absent(tmp_path: Path) -> None:
    status = detect_protocol_sift(home=tmp_path)
    assert status.protocol_sift_installed is False
    assert isinstance(status.claude_code_installed, bool)
    assert status.skills_present == []
    assert len(status.skills_missing) == 5
    assert status.to_dict()["protocol_sift_installed"] is False

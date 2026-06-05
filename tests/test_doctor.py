"""A8: doctor checks (fail-closed) + protocol-sift detection (env-only)."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.doctor import FAIL, collect_checks, run_doctor
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


def test_detect_protocol_sift_absent(tmp_path: Path) -> None:
    status = detect_protocol_sift(home=tmp_path)
    assert status.protocol_sift_installed is False
    assert isinstance(status.claude_code_installed, bool)
    assert status.skills_present == []
    assert len(status.skills_missing) == 5
    assert status.to_dict()["protocol_sift_installed"] is False

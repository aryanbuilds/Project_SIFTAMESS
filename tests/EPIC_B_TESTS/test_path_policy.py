"""B2: write-gate allows in-run writes and rejects every escape."""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core.evidence.path_policy import (
    PathPolicyViolation,
    assert_run_outside_evidence,
    safe_write_path,
)


def test_in_run_path_allowed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    target = safe_write_path(run, "evidence/manifest.json")
    assert target == (run / "evidence" / "manifest.json").resolve()


def test_dotdot_traversal_blocked(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(PathPolicyViolation):
        safe_write_path(run, "../escape.txt")


def test_absolute_escape_blocked(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(PathPolicyViolation):
        safe_write_path(run, str(outside.resolve()))


def test_evidence_path_blocked(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    evidence = run / "orig_evidence"  # evidence nested under run → exercises the exclusion
    evidence.mkdir()
    with pytest.raises(PathPolicyViolation):
        safe_write_path(run, "orig_evidence/x.txt", evidence_root=evidence)


def test_symlink_to_outside_blocked(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = run / "sneaky"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this host")
    with pytest.raises(PathPolicyViolation):
        safe_write_path(run, "sneaky/evil.txt")


def test_run_inside_evidence_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "evi"
    evidence.mkdir()
    run = evidence / "run"
    run.mkdir()
    with pytest.raises(PathPolicyViolation):
        assert_run_outside_evidence(run, evidence)


def test_run_outside_evidence_ok(tmp_path: Path) -> None:
    evidence = tmp_path / "evi"
    evidence.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    assert_run_outside_evidence(run, evidence)  # must not raise


@pytest.mark.parametrize(
    "rel",
    ["../escape.txt", "../../etc/passwd", "/etc/passwd", "a/b/../../../../out", "foo\x00bar"],
)
def test_write_paths_restricted_to_run_directory(tmp_path: Path, rel: str) -> None:
    # CLAUDE §14 umbrella: every escape vector is rejected, a legit in-run path is contained.
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(PathPolicyViolation):
        safe_write_path(run, rel)
    allowed = safe_write_path(run, "results/TASK-001.result.json")
    assert allowed.is_relative_to(run.resolve())

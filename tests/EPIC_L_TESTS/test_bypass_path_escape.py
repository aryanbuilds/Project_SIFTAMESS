"""L5a — bypass test: run-dir write boundary (threat T3 · OWASP LLM06 · CWE-22).

Asserts the EFFECT of ``safe_write_path`` / ``resolved_source``: every traversal/escape vector is
rejected with ``PathPolicyViolation`` (writes) or ``ValueError`` (reads), and legitimate in-run
paths return a contained target — the LangGraph CVE-2026-34070 / zip-slip class, foreclosed in code.
Includes the Step-1 regressions (NUL byte, target==run) and a Hypothesis property: no input ever
yields a returned path outside the run dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from siftmesh_core.evidence.path_policy import (
    PathPolicyViolation,
    assert_run_outside_evidence,
    safe_write_path,
)
from siftmesh_core.mcp_gateway.tools._common import resolved_source

# (rel, expected-message-fragment) — each MUST raise PathPolicyViolation.
_ESCAPES: list[tuple[str, str]] = [
    ("..", "escapes run dir"),
    ("../..", "escapes run dir"),
    ("../escape.txt", "escapes run dir"),
    ("../../etc/passwd", "escapes run dir"),
    ("a/b/../../../../etc/passwd", "escapes run dir"),  # '..' nested AFTER a valid prefix
    ("sub/../../../x", "escapes run dir"),
    ("/etc/passwd", "escapes run dir"),  # absolute path as rel (truediv discards left operand)
    ("foo\x00bar", "cannot resolve"),  # embedded NUL byte -> fail closed (regression, Step 1)
    (".", "run dir itself"),  # target == run dir (regression, Step 1)
    ("", "run dir itself"),
    ("a/..", "run dir itself"),
]


def _run(tmp_path: Path) -> Path:
    run = tmp_path / "case_runs" / "RUN-X"
    run.mkdir(parents=True)
    return run


@pytest.mark.parametrize(("rel", "msg"), _ESCAPES)
def test_escape_vectors_rejected(tmp_path: Path, rel: str, msg: str) -> None:
    run = _run(tmp_path)
    with pytest.raises(PathPolicyViolation, match=msg):
        safe_write_path(run, rel)


def test_absolute_path_as_path_object_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)
    with pytest.raises(PathPolicyViolation, match="escapes run dir"):
        safe_write_path(run, Path("/etc/shadow"))


def test_symlink_inside_run_pointing_out_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = run / "sneaky"
    try:
        link.symlink_to(outside)
    except OSError:  # platforms without symlink permission
        pytest.skip("symlinks unsupported here")
    with pytest.raises(PathPolicyViolation, match="escapes run dir"):
        safe_write_path(run, "sneaky/evil.txt")


def test_symlink_loop_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)
    a, b = run / "loopA", run / "loopB"
    try:
        a.symlink_to(b)
        b.symlink_to(a)
    except OSError:
        pytest.skip("symlinks unsupported here")
    with pytest.raises(PathPolicyViolation, match="cannot resolve"):
        safe_write_path(run, "loopA/x")


def test_prefix_collision_sibling_rejected(tmp_path: Path) -> None:
    # The #1 real-world zip-slip bug: a sibling dir sharing a name-prefix must NOT pass.
    # is_relative_to is component-wise (not str.startswith), so 'run_evil' is correctly rejected.
    run = tmp_path / "run"
    run.mkdir()
    (tmp_path / "run_evil").mkdir()
    with pytest.raises(PathPolicyViolation, match="escapes run dir"):
        safe_write_path(run, "../run_evil/x")


def test_write_under_evidence_root_rejected(tmp_path: Path) -> None:
    # evidence nested under run (a legitimate layout) — a target landing in it is still rejected.
    run = _run(tmp_path)
    evidence = run / "evidence" / "originals"
    evidence.mkdir(parents=True)
    with pytest.raises(PathPolicyViolation, match="inside original evidence"):
        safe_write_path(run, "evidence/originals/x.txt", evidence_root=evidence)


def test_assert_run_outside_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    inside = evidence / "run"
    inside.mkdir()
    with pytest.raises(PathPolicyViolation, match="must not be inside evidence"):
        assert_run_outside_evidence(inside, evidence)
    # a sibling run is fine
    sibling = tmp_path / "run"
    sibling.mkdir()
    assert_run_outside_evidence(sibling, evidence)  # no raise


# ── positive controls (the gate is not just deny-all) ────────────────────────


def test_legit_in_run_path_allowed(tmp_path: Path) -> None:
    run = _run(tmp_path)
    target = safe_write_path(run, "results/TASK-001.result.json")
    assert target.is_relative_to(run.resolve())
    assert target == (run / "results" / "TASK-001.result.json").resolve()


def test_dot_segments_normalized_in_run(tmp_path: Path) -> None:
    run = _run(tmp_path)
    target = safe_write_path(run, "a/./b/../c.txt")
    assert target == (run / "a" / "c.txt").resolve()


def test_in_run_symlink_followed_not_lexical(tmp_path: Path) -> None:
    # Proves resolve() (symlink-following) is used, not lexical normpath: an in-run symlink to an
    # in-run dir resolves inside and is allowed.
    run = _run(tmp_path)
    real = run / "real_sub"
    real.mkdir()
    link = run / "link_sub"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks unsupported here")
    target = safe_write_path(run, "link_sub/x.txt")
    assert target.is_relative_to(run.resolve())


# ── reader-side containment (resolved_source dual-root) ──────────────────────


def test_resolved_source_rejects_escape_all_roots(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    run = tmp_path / "run"
    evidence.mkdir()
    run.mkdir()
    with pytest.raises(ValueError, match="escapes evidence root"):
        resolved_source(evidence, "../../etc/passwd", run_root=run)


def test_resolved_source_admits_dual_root(tmp_path: Path) -> None:
    # bhyv: a derived artifact under the RUN root (evidence_root != run_root) is readable.
    evidence = tmp_path / "evidence"
    run = tmp_path / "run"
    evidence.mkdir()
    (run / "evidence" / "extracted").mkdir(parents=True)
    derived = run / "evidence" / "extracted" / "hive.dat"
    derived.write_bytes(b"derived bytes")
    path, sha = resolved_source(evidence, "evidence/extracted/hive.dat", run_root=run)
    assert path == derived.resolve()
    assert len(sha) == 64


# ── property: no input ever yields a returned path outside the run dir ────────

_SEG = st.sampled_from(["..", ".", "a", "b", "x", "", "foo", "%2e%2e", "....", "etc", "sub"])


@settings(
    derandomize=True, max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(segments=st.lists(_SEG, max_size=8))
def test_property_never_escapes_run(tmp_path: Path, segments: list[str]) -> None:
    run = (tmp_path / "case_runs" / "RUN-P").resolve()
    run.mkdir(parents=True, exist_ok=True)
    rel = "/".join(segments)
    try:
        target = safe_write_path(run, rel)
    except PathPolicyViolation:
        return  # rejected — the safe outcome
    # if it returned, the target is ALWAYS contained and is never the run dir itself
    assert target.is_relative_to(run)
    assert target != run

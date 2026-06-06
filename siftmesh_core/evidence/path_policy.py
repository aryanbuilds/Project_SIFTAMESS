"""Central filesystem write-gate (B2 / design rule D3).

Every SIFTMesh-controlled write routes through :func:`safe_write_path`, which
resolves the real target and refuses anything that escapes the run directory
(``..`` traversal, absolute paths, a symlink inside the run dir pointing out —
``resolve()`` follows symlinks) or lands under the original evidence tree.

Scope (no overclaim): this governs *SIFTMesh's own* code paths. Combined with
read-only opens at ingest and no raw-shell/destructive tools (CLAUDE.md §6) it
upholds the "originals untouched" boundary — but it is not OS-level prevention
of an external process, and later tool wrappers must keep routing through it.
"""

from __future__ import annotations

from pathlib import Path


class PathPolicyViolation(Exception):
    """Raised when a requested write path escapes the run-directory policy."""


def assert_run_outside_evidence(run_root: Path | str, evidence_root: Path | str) -> None:
    """Guard: the run dir must not live inside the evidence tree.

    Otherwise the evidence-exclusion rule in :func:`safe_write_path` would
    reject every legitimate run-dir write.
    """
    run = Path(run_root).resolve()
    evidence = Path(evidence_root).resolve()
    if run == evidence or run.is_relative_to(evidence):
        raise PathPolicyViolation(f"run dir {run} must not be inside evidence dir {evidence}")


def safe_write_path(
    run_root: Path | str,
    rel: str | Path,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Return the resolved write target under ``run_root``, or raise.

    Rejects ``..`` traversal, absolute-path escape, symlink-to-outside, and —
    when ``evidence_root`` is given — any path under the original evidence tree.
    """
    run = Path(run_root).resolve()
    try:
        target = (run / Path(rel)).resolve()
    except (OSError, RuntimeError) as exc:  # symlink loops, etc.
        raise PathPolicyViolation(f"cannot resolve {rel!r} under {run}: {exc}") from exc

    if not target.is_relative_to(run):
        raise PathPolicyViolation(f"{target} escapes run dir {run}")

    if evidence_root is not None:
        evidence = Path(evidence_root).resolve()
        if target == evidence or target.is_relative_to(evidence):
            raise PathPolicyViolation(f"{target} is inside original evidence {evidence}")

    return target

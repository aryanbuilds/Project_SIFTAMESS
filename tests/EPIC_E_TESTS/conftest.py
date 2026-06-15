"""Epic E shared fixtures - synthetic run dirs with a hand-built manifest.

The planner reads only manifest metadata, so these tests need NO real artifact
bytes: each fixture writes a valid ``EvidenceManifest`` with deterministic 64-hex
shas. CI-safe; no SANS evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from siftmesh_core.run_dir import RunPaths, new_run_dir
from siftmesh_core.schemas.evidence import EvidenceFile, EvidenceManifest

# A representative Windows triage set (covers every actionable + context-only family).
TRIAGE_FILES: tuple[str, ...] = (
    "Security.evtx",
    "Microsoft-Windows-PowerShell%4Operational.evtx",
    "CMD.EXE-12345678.pf",
    "Users/alice/NTUSER.DAT",
    "Users/bob/NTUSER.DAT",
    "$MFT",
    "System.evtx",
)


def _sha(i: int) -> str:
    """A valid distinct lowercase-hex sha256 for the i-th file."""
    return f"{i:064x}"


SyntheticRun = Callable[..., RunPaths]


@pytest.fixture
def synthetic_run(tmp_path: Path) -> SyntheticRun:
    """Return a factory: ``make(paths, case_id=...) -> RunPaths`` with a written manifest."""

    def _make(paths: Sequence[str] = TRIAGE_FILES, *, case_id: str = "case01") -> RunPaths:
        run = new_run_dir(base=tmp_path / "case_runs")
        files = [
            EvidenceFile(
                path=p,
                sha256=_sha(i),
                size_bytes=1024 + i,
                mtime_utc=datetime(2026, 1, 1, tzinfo=UTC),
                evidence_type="unknown",
            )
            for i, p in enumerate(paths)
        ]
        manifest = EvidenceManifest(
            case_id=case_id,
            run_id=run.run_id,
            created_utc=datetime(2026, 1, 1, tzinfo=UTC),
            tool_version="0.1.0",
            files=files,
        )
        run.evidence_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return run

    return _make

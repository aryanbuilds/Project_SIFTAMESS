"""Run-aware memory-archive decompression (GAP 1, Epic D-H hardening).

The pure mechanics live in :mod:`siftmesh_core.evidence.memory_access` (unzip + ``7z x``,
magic detection, zip-slip guard, fail-closed on missing ``7z``). This module wraps them with
run-dir bookkeeping so a compressed memory capture (``Rocba-Memory.zip`` → ``.7z`` → image)
becomes a first-class, auditable derived artifact that the ``analyze-memory`` tool can consume:

* the decompressed image is written under ``run/evidence/extracted/`` (path-policed);
* it is registered as a :class:`DerivedArtifact` (provenance: source archive + its SHA-256);
* a ``derived_written`` custody event is recorded; and
* ``decompress_start`` / ``decompress_done`` orchestration events are logged.

Decompression is *evidence preparation*, not forensic analysis — so it is a CLI primitive, not
an MCP tool. It never enters the typed-tool allowlist and never writes to ``tool_calls.jsonl``;
its operation id uses a distinct ``DECOMP-NNN`` namespace. The original archive is read-only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core import __version__
from siftmesh_core.evidence import memory_access
from siftmesh_core.evidence.derived import DerivedArtifact, append_derived
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.ledgers.custody_ledger import append_event
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.custody import CustodyEvent

# Decompressed images land here under the run dir (matches the disk-image extraction convention).
_EXTRACT_SUBDIR = Path("evidence") / "extracted"
_DECOMP_ID_RE = re.compile(r"^DECOMP-(\d+)$")


@dataclass(frozen=True)
class DecompressOutcome:
    """The decompressed image plus its provenance back to the source archive."""

    decomp_id: str  # DECOMP-NNN
    source_artifact: str  # evidence-relative archive path
    source_sha256: str
    derived_path: str  # run-relative POSIX path to the decompressed image
    image_format: str
    size_bytes: int
    sha256: str


def _next_decomp_id(run: RunPaths) -> str:
    """Mint the next ``DECOMP-NNN`` id by scanning the derived registry (deterministic)."""
    highest = 0
    registry = run.derived_artifacts
    if registry.is_file():
        data = json.loads(registry.read_text(encoding="utf-8"))
        for record in data.get("derived", []):
            match = _DECOMP_ID_RE.match(str(record.get("tool_call_id", "")))
            if match:
                highest = max(highest, int(match.group(1)))
    return f"DECOMP-{highest + 1:03d}"


def decompress_archive(
    run: RunPaths,
    *,
    archive: str,
    evidence_root: Path | str,
) -> DecompressOutcome:
    """Decompress ``archive`` (evidence-relative) into ``run/evidence/extracted/``.

    Returns the :class:`DecompressOutcome` for the decompressed image and records the
    derived-artifact, custody, and orchestration entries. Raises (fail-closed) on a missing
    ``7z`` backend (:class:`BackendUnavailableError`), a path escape (``ValueError`` /
    :class:`PathPolicyViolation`), or a decompression failure (``RuntimeError``).
    """
    archive_path, archive_sha = resolved_source(evidence_root, archive)
    dest = safe_write_path(run.root, _EXTRACT_SUBDIR, evidence_root=evidence_root)
    dest.mkdir(parents=True, exist_ok=True)

    decomp_id = _next_decomp_id(run)
    audit = open_orchestration_log(run.orchestration_events, run.run_id)
    log_event(audit, "decompress_start", archive=archive, decomp_id=decomp_id)

    started = datetime.now(UTC)
    image = memory_access.decompress(archive_path, dest)
    ended = datetime.now(UTC)

    derived_path = image.path.resolve().relative_to(run.root.resolve()).as_posix()
    append_derived(
        run.root,
        DerivedArtifact(
            derived_path=derived_path,
            source_artifact=archive,
            source_sha256=archive_sha,
            tool_call_id=decomp_id,
            derived_sha256=image.sha256,
        ),
        evidence_root=evidence_root,
    )
    append_event(
        run.root,
        CustodyEvent(
            event_type="derived_written",
            run_id=run.run_id,
            artifact=derived_path,
            source_sha256=archive_sha,
            action="decompress",
            actor="siftmesh",
            tool_name="memory_access.decompress",
            tool_version=__version__,
            start_time_utc=started,
            end_time_utc=ended,
            result="ok",
        ),
        evidence_root=evidence_root,
    )
    log_event(
        audit,
        "decompress_done",
        decomp_id=decomp_id,
        derived_path=derived_path,
        image_format=image.image_format,
        size_bytes=image.size_bytes,
        sha256=image.sha256,
    )
    return DecompressOutcome(
        decomp_id=decomp_id,
        source_artifact=archive,
        source_sha256=archive_sha,
        derived_path=derived_path,
        image_format=image.image_format,
        size_bytes=image.size_bytes,
        sha256=image.sha256,
    )

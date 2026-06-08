"""Evidence manifest + sha256sum-compatible checksum writer (B4).

Serializes the C6 :class:`EvidenceManifest` to ``evidence/evidence_manifest.json``
and writes ``evidence/hashes.sha256`` in GNU coreutils text format
(``<hex><SPACE><SPACE><relpath>\\n``) so ``sha256sum -c hashes.sha256`` verifies
on Linux from the evidence root. All writes route through the path policy (D3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core import __version__
from siftmesh_core.evidence.hash_utils import FileFact, walk_files
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.schemas.evidence import EvidenceFile, EvidenceManifest

# Suffix → coarse evidence_type label (a guess for triage; not authoritative).
_TYPE_BY_SUFFIX = {
    ".evtx": "evtx",
    ".evt": "evt",
    ".pf": "prefetch",
    ".dat": "registry",
    ".hve": "registry",
    ".log": "log",
    ".csv": "csv",
    ".json": "json",
    ".txt": "text",
    ".zip": "archive",
    ".gz": "archive",
    ".7z": "archive",
    ".tar": "archive",
    ".e01": "disk_image",
    ".raw": "disk_image",
    ".dd": "disk_image",
    ".img": "disk_image",
    ".vmdk": "disk_image",
    ".mem": "memory_image",
    ".vmem": "memory_image",
}
# Windows registry hive basenames (lowercased). Public so the planner's artifact
# router (Epic E) shares one source of truth and never drifts from triage typing.
REGISTRY_HIVE_NAMES = frozenset(
    {"ntuser.dat", "usrclass.dat", "system", "software", "sam", "security"}
)


def guess_evidence_type(rel_path: str) -> str:
    """Best-effort evidence-type label from name/extension (string only)."""
    name = Path(rel_path).name.lower()
    if name in REGISTRY_HIVE_NAMES:
        return "registry"
    return _TYPE_BY_SUFFIX.get(Path(rel_path).suffix.lower(), "unknown")


def build_manifest(
    *,
    case_id: str,
    run_id: str,
    facts: list[FileFact],
    created_utc: datetime | None = None,
) -> EvidenceManifest:
    """Construct a validated :class:`EvidenceManifest` from walk facts."""
    return EvidenceManifest(
        case_id=case_id,
        run_id=run_id,
        created_utc=created_utc or datetime.now(UTC),
        tool_version=__version__,
        files=[
            EvidenceFile(
                path=fact.rel_path,
                sha256=fact.sha256,
                size_bytes=fact.size_bytes,
                mtime_utc=fact.mtime_utc,
                evidence_type=guess_evidence_type(fact.rel_path),
            )
            for fact in facts
        ],
    )


def build_manifest_from_dir(
    evidence_root: Path | str,
    *,
    case_id: str,
    run_id: str,
    created_utc: datetime | None = None,
) -> EvidenceManifest:
    """Hash every file under ``evidence_root`` and build the manifest."""
    return build_manifest(
        case_id=case_id,
        run_id=run_id,
        facts=walk_files(evidence_root),
        created_utc=created_utc,
    )


def write_manifest(
    manifest: EvidenceManifest,
    run_root: Path | str,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Write ``evidence/evidence_manifest.json`` (deterministic UTC-Z JSON)."""
    target = safe_write_path(
        run_root, Path("evidence") / "evidence_manifest.json", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def write_hashes_sha256(
    manifest: EvidenceManifest,
    run_root: Path | str,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Write ``evidence/hashes.sha256`` in ``sha256sum -c`` text format."""
    target = safe_write_path(
        run_root, Path("evidence") / "hashes.sha256", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(f"{f.sha256}  {f.path}\n" for f in manifest.files)
    # newline="\n" prevents CRLF translation on Windows so sha256sum -c works on Linux.
    with target.open("w", encoding="utf-8", newline="\n") as out:
        out.write(lines)
    return target

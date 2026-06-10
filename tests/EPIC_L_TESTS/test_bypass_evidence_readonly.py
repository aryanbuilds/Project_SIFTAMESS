"""L5d — bypass test: evidence-vault boundary (threat T4 · OWASP LLM06 · chain of custody).

Asserts the EFFECT: after a REAL run (manifest + readonly vault + plan + dispatch of real Epic-D
tools over real fixtures), every original is BYTE-IDENTICAL to its ingest-time sha256 baseline, and
no original is added or removed — the Sleuth-Kit "open O_RDONLY, write outputs elsewhere" invariant
(honestly posture-level: safe_write_path + read-only opens, not an OS `mount -o ro` — deferred, §7).
Satisfies CLAUDE §14 test_original_evidence_not_modified.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.evidence import EvidenceManifest

DispatchedCase = Callable[..., tuple[RunPaths, Path]]


def test_originals_byte_identical_after_real_run(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()  # builds evidence, then runs real tools over it
    manifest = EvidenceManifest.model_validate_json(run.evidence_manifest.read_text())
    assert manifest.files  # the baseline exists
    for f in manifest.files:
        original = evidence / f.path
        assert original.is_file(), f"original vanished: {f.path}"
        assert sha256_file(original) == f.sha256, f"original modified: {f.path}"


def test_no_original_added_or_removed(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    manifest = EvidenceManifest.model_validate_json(run.evidence_manifest.read_text())
    on_disk = {p.relative_to(evidence).as_posix() for p in evidence.rglob("*") if p.is_file()}
    in_manifest = {f.path for f in manifest.files}
    assert on_disk == in_manifest  # tools wrote nothing into the evidence tree


def test_derived_artifacts_land_in_run_not_evidence(dispatched_case: DispatchedCase) -> None:
    run, evidence = dispatched_case()
    # Any artifact SIFTMesh produced lives under the run dir; evidence holds only originals.
    produced = [p for p in run.root.rglob("*") if p.is_file()]
    assert produced  # the run wrote results/claims/audit under the run dir
    for p in produced:
        assert p.resolve().is_relative_to(run.root.resolve())
        assert not p.resolve().is_relative_to(evidence.resolve())

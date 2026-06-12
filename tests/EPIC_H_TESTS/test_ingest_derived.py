"""hth.2 — re-ingest extracted/decompressed derived artifacts into the plannable set.

CI-safe: a real EVTX fixture is placed under the run's ``evidence/extracted/`` and registered as a
derived artifact; ingest makes it a *derived* task that dispatch resolves against the run dir and
the real parser analyses. No keys, no Volatility (the memory case is routing-only).
"""

from __future__ import annotations

import json
import lzma
import shutil
from collections.abc import Callable
from pathlib import Path

import typer
from siftmesh_core.config import load_settings
from siftmesh_core.evidence.derived import DerivedArtifact, append_derived
from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.ledgers.followups import read_followups
from siftmesh_core.orchestrator.critic import critique_run, detect_derived_gaps, ingest_derived
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.plan import InvestigationPlan
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.yaml_io import read_yaml_model
from typer.testing import CliRunner

BuiltRun = Callable[..., tuple[RunPaths, Path]]
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forensic"
_DERIVED_EVTX = "evidence/extracted/Security.evtx"


def _prepared(built_run: BuiltRun) -> tuple[RunPaths, Path]:
    """A built run that has been planned (manifest covered; investigation_plan written)."""
    run, evidence = built_run(mode="manual")
    generate_plan(run, settings=load_settings())
    return run, evidence


def _add_derived_evtx(run: RunPaths) -> str:
    """Place a real EVTX under evidence/extracted/ + register it as a carved derived artifact."""
    extracted = run.evidence / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    dest = extracted / "Security.evtx"
    shutil.copy(_FIXTURES / "security_short.evtx", dest)
    append_derived(
        run.root,
        DerivedArtifact(
            derived_path=_DERIVED_EVTX,
            source_artifact="disk.E01",
            source_sha256="b" * 64,
            tool_call_id="TOOL-001",
            derived_sha256=sha256_file(dest),
            extraction_source_path=r"C:\Windows\System32\winevt\Logs\Security.evtx",
            extraction_inode="65-128-1",
            extraction_method="sleuthkit_icat",
        ),
    )
    return _DERIVED_EVTX


def test_ingest_derived_creates_derived_task(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)
    derived_path = _add_derived_evtx(run)
    created = ingest_derived(run, evidence_root=evidence)
    assert len(created) == 1
    contract = read_yaml_model(TaskContract, created[0])
    assert contract.allowed_tools == ["parse_evtx_security"]
    assert contract.input_artifacts[0].path == derived_path
    assert contract.input_artifacts[0].origin == "derived"


def test_dispatch_derived_task_runs_real_tool(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)
    _add_derived_evtx(run)
    task_id = ingest_derived(run, evidence_root=evidence)[0].stem
    refs = dispatch_run(run, settings=load_settings(), task_id=task_id)
    assert len(refs) == 1 and refs[0].status == "success"
    result = json.loads(run.result_path(task_id).read_text(encoding="utf-8"))
    assert result["claims"]  # real EVTX claims, anchored to the derived file
    assert result["claims"][0]["source_artifact"] == _DERIVED_EVTX


def test_g9_flags_derived_gap_and_creates_followup(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)
    _add_derived_evtx(run)
    assert detect_derived_gaps(run)  # an uncovered actionable derived artifact
    critique_run(run, settings=load_settings(), evidence_root=evidence)
    fups = read_followups(run.root)
    assert any(f.reason == "derived_gap" and f.artifact == _DERIVED_EVTX for f in fups)


def _add_derived_ntuser(run: RunPaths) -> str:
    """Place a carved NTUSER.DAT under evidence/extracted/ + register it as a derived artifact."""
    extracted = run.evidence / "extracted" / "user_hives"
    extracted.mkdir(parents=True, exist_ok=True)
    dest = extracted / "fredr_NTUSER.DAT"  # the disk-image extractor renames per-user hives
    dest.write_bytes(lzma.decompress((_FIXTURES / "ntuser.dat.xz").read_bytes()))
    rel = "evidence/extracted/user_hives/fredr_NTUSER.DAT"
    append_derived(
        run.root,
        DerivedArtifact(
            derived_path=rel,
            source_artifact="disk.E01",
            source_sha256="b" * 64,
            tool_call_id="TOOL-001",
            derived_sha256=sha256_file(dest),
        ),
    )
    return rel


def test_derived_ntuser_emits_extra_tool_followups(built_run: BuiltRun) -> None:
    # A carved NTUSER must yield its multi-tool-per-hive EXTRAS, not just the primary run-keys —
    # the gap that silently dropped recentdocs/usb/shellbags on the --auto disk path.
    run, evidence = _prepared(built_run)
    rel = _add_derived_ntuser(run)
    created = ingest_derived(run, evidence_root=evidence)
    tools = {read_yaml_model(TaskContract, p).allowed_tools[0] for p in created}
    assert {
        "extract_registry_run_keys",  # primary
        "parse_recentdocs_mru",
        "parse_usb_registry",
        "parse_shellbags",
    } <= tools
    for p in created:  # every task binds to the derived hive, origin=derived
        c = read_yaml_model(TaskContract, p)
        assert c.input_artifacts[0].path == rel and c.input_artifacts[0].origin == "derived"
    assert ingest_derived(run, evidence_root=evidence) == []  # idempotent (all tools covered)


def test_ingest_derived_idempotent(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)
    _add_derived_evtx(run)
    assert len(ingest_derived(run, evidence_root=evidence)) == 1
    assert ingest_derived(run, evidence_root=evidence) == []  # gap now covered
    assert detect_derived_gaps(run) == []


def test_evidence_manifest_unchanged(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)
    before = run.evidence_manifest.read_bytes()
    _add_derived_evtx(run)
    ingest_derived(run, evidence_root=evidence)
    assert run.evidence_manifest.read_bytes() == before  # the intake seal is never mutated


def test_decompress_derived_routes_as_memory(built_run: BuiltRun) -> None:
    run, _ = _prepared(built_run)
    extracted = run.evidence / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    image = extracted / "mem.raw"  # a .raw suffix would route to disk_image without the DECOMP fix
    image.write_bytes(b"PAGEDU64" + b"\x00" * 64)
    append_derived(
        run.root,
        DerivedArtifact(
            derived_path="evidence/extracted/mem.raw",
            source_artifact="mem.zip",
            source_sha256="a" * 64,
            tool_call_id="DECOMP-001",
            derived_sha256=sha256_file(image),
        ),
    )
    gaps = detect_derived_gaps(run)
    assert len(gaps) == 1
    assert gaps[0].family == "memory_image"
    assert gaps[0].tool == "analyze_memory"


def test_ingest_derived_writes_plan_when_absent(built_run: BuiltRun) -> None:
    # Staged manual flow (no `plan` run): ingest-derived writes a minimal plan so dispatch works.
    run, evidence = built_run(mode="manual")
    assert not run.investigation_plan.exists()
    _add_derived_evtx(run)
    created = ingest_derived(run, evidence_root=evidence)
    assert len(created) == 1
    assert run.investigation_plan.exists()  # the fix wrote a dispatchable plan
    plan = read_yaml_model(InvestigationPlan, run.investigation_plan)
    assert plan.review_only is False and plan.steps == []
    # dispatch previously failed closed ('No such file: investigation_plan.yaml'); now it runs.
    refs = dispatch_run(run, settings=load_settings(), task_id=created[0].stem)
    assert len(refs) == 1 and refs[0].status == "success"


def test_ingest_derived_preserves_existing_plan(built_run: BuiltRun) -> None:
    run, evidence = _prepared(built_run)  # a real plan already exists
    before = run.investigation_plan.read_bytes()
    _add_derived_evtx(run)
    ingest_derived(run, evidence_root=evidence)
    assert run.investigation_plan.read_bytes() == before  # never clobbers the planner's plan


def test_ingest_derived_cli(built_run: BuiltRun, runner: CliRunner, cli_app: typer.Typer) -> None:
    run, evidence = _prepared(built_run)
    _add_derived_evtx(run)
    result = runner.invoke(cli_app, ["ingest-derived", str(run.root), "--evidence", str(evidence)])
    assert result.exit_code == 0, result.output
    assert "1 derived task(s) created" in result.output

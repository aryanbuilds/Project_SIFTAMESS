"""J8 — wiring: `siftmesh report`/`replay` CLI + the engine REPORT state (auto writes reports)."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.cli import app
from siftmesh_core.config import load_settings
from siftmesh_core.ledgers.claim_ledger import append_claim
from siftmesh_core.orchestrator.run_state_store import write_run_state
from siftmesh_core.orchestrator.workflow_runner import run_engine
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.claim import Claim
from siftmesh_core.schemas.run import RunState
from typer.testing import CliRunner

runner = CliRunner()

_REPORT_FILES = (
    "final_report.md",
    "accuracy_report.md",
    "dataset_documentation.md",
    "architecture_notes.md",
    "replay.html",
)


def _claim(cid: str) -> Claim:
    return Claim.model_validate(
        {
            "claim_id": cid,
            "task_id": cid.split("-CLAIM")[0],
            "status": "confirmed",
            "claim": f"finding {cid}",
            "confidence": 0.9,
            "evidence_type": "windows_event_log",
            "source_artifact": "evidence/extracted/Security.evtx",
            "source_sha256": "a" * 64,
            "tool_name": "parse_evtx_security",
            "tool_call_id": "TOOL-001",
            "supporting_evidence_refs": ["TOOL-001"],
        }
    )


def test_report_cli_writes_all(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, _ = dispatched_run()
    result = runner.invoke(app, ["report", str(run.root)])
    assert result.exit_code == 0, result.output
    for name in _REPORT_FILES:
        assert (run.reports / name).is_file(), name


def test_report_cli_corrupt_fails_strict_recovers_tolerant(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    append_claim(run.root, _claim("TASK-001-CLAIM-001"))
    with run.claim_ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"claim_id":"TASK-001-CLAIM-002","tas')  # truncated trailing line
    strict = runner.invoke(app, ["report", str(run.root)])
    assert strict.exit_code == 1
    tolerant = runner.invoke(app, ["report", str(run.root), "--tolerant"])
    assert tolerant.exit_code == 0, tolerant.output
    assert (run.reports / "final_report.md").is_file()


def test_report_cli_rejects_non_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "not a run directory" in result.output


def test_replay_cli_text_and_html(dispatched_run) -> None:  # type: ignore[no-untyped-def]
    run, _ = dispatched_run()
    text = runner.invoke(app, ["replay", str(run.root)])
    assert text.exit_code == 0 and "orchestration events" in text.output
    html = runner.invoke(app, ["replay", str(run.root), "--html"])
    assert html.exit_code == 0 and (run.reports / "replay.html").is_file()


def test_engine_auto_generates_reports(planned_run) -> None:  # type: ignore[no-untyped-def]
    run, evidence = planned_run()
    write_run_state(run, RunState(run_id=run.run_id, mode="auto", max_iterations=2))
    final = run_engine(run, settings=load_settings(), evidence_root=evidence)
    assert final.state == "done"
    for name in _REPORT_FILES:
        assert (run.reports / name).is_file(), name
    events = run.orchestration_events.read_text(encoding="utf-8")
    assert "reports_generated" in events

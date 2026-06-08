"""B8: orchestration audit log — ordered, UTC, replayable JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from siftmesh_core.ledgers.audit_log import log_event, open_orchestration_log
from siftmesh_core.run_dir import new_run_dir


def test_orchestration_events_appended(tmp_path: Path) -> None:
    rp = new_run_dir(base=tmp_path / "runs")
    logger = open_orchestration_log(rp.orchestration_events, rp.run_id)
    log_event(logger, "init_case_start", case="case01")
    log_event(logger, "init_case_done", run=rp.run_id)

    assert rp.orchestration_events.exists()
    records = [
        json.loads(line)
        for line in rp.orchestration_events.read_text(encoding="utf-8").splitlines()
    ]
    assert [r["event"] for r in records] == ["init_case_start", "init_case_done"]
    assert all(r["run_id"] == rp.run_id for r in records)
    assert all(r["timestamp"].endswith("Z") for r in records)  # UTC
    assert all(r["level"] == "info" for r in records)

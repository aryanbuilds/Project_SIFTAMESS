"""A5: append-only JSONL logger — round-trips one valid JSON line per event."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from siftmesh_core.logging import bind_run, configure_jsonl_logging


def test_jsonl_round_trip(tmp_path: Path) -> None:
    log_path = tmp_path / "audit" / "agent_calls.jsonl"
    log = configure_jsonl_logging(log_path)
    bind_run(log, "RUN-001").info("agent_dispatched", task_id="TASK-001")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "agent_dispatched"
    assert record["level"] == "info"
    assert record["run_id"] == "RUN-001"
    assert record["task_id"] == "TASK-001"
    assert record["timestamp"].endswith("Z")


def test_appends_not_truncates(tmp_path: Path) -> None:
    log_path = tmp_path / "audit" / "events.jsonl"
    log = configure_jsonl_logging(log_path)
    log.info("first")
    configure_jsonl_logging(log_path).info("second")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["event"] for line in lines] == ["first", "second"]


def test_concurrent_writes_preserve_jsonl_records(tmp_path: Path) -> None:
    log_path = tmp_path / "audit" / "concurrent.jsonl"
    log = configure_jsonl_logging(log_path)

    def write_event(index: int) -> None:
        log.info("concurrent", index=index)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write_event, range(20)))

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 20
    assert sorted(record["index"] for record in records) == list(range(20))

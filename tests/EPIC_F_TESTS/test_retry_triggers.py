"""F9 — genuine retry-trigger recording (no scripted failures).

A recoverable tool error (the real tool returns status="error") is *recorded* as
``retry_required`` + ``retry_cause``; a missing backend fails closed as ``error``.
The retry DECISION is Epic G — Epic F only records the genuine cause. Here the tool
is swapped for a stub that *returns* an error / *raises* BackendUnavailableError,
exercising the executor's handling — not faking forensic output.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.adapters import deterministic_executor as de
from siftmesh_core.config import load_settings
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.orchestrator.scheduler import dispatch_run
from siftmesh_core.run_dir import RunPaths
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult
from siftmesh_core.schemas.tool_result import ToolResult
from siftmesh_core.schemas.yaml_io import read_yaml_model

RealCase = Callable[..., tuple[RunPaths, Path]]


def _task_for_tool(run: RunPaths, tool: str) -> str:
    """Return the task_id whose contract uses *tool* (task numbering is manifest-order)."""
    for path in sorted(run.tasks.glob("TASK-*.yaml")):
        contract = read_yaml_model(TaskContract, path)
        if tool in contract.allowed_tools:
            return contract.task_id
    raise AssertionError(f"no task uses {tool}")


def _error_result() -> ToolResult:
    now = datetime.now(UTC)
    return ToolResult(
        tool_call_id="TOOL-999",
        tool_name="parse_evtx_security",
        source_artifact="Security.evtx",
        source_sha256="a" * 64,
        start_time_utc=now,
        end_time_utc=now,
        status="error",
        backend="real",
        tool_version="0.1.0",
        error_code="lznt1_decompress_failed",
    )


def test_recoverable_tool_error_records_retry_required(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, _ = real_case()
    tid = _task_for_tool(run, "parse_evtx_security")
    _fn, kwargs, claimer = de._DISPATCH["parse_evtx_security"]
    monkeypatch.setitem(
        de._DISPATCH, "parse_evtx_security", (lambda *a, **k: _error_result(), kwargs, claimer)
    )
    refs = dispatch_run(run, settings=load_settings(), task_id=tid)
    tr = TaskResult.model_validate_json(run.result_path(tid).read_text(encoding="utf-8"))
    assert tr.status == "retry_required"
    assert tr.retry_cause == "recoverable_tool_error"
    assert tr.claims == []
    assert refs[0].status == "retry_required"


def test_backend_unavailable_fails_closed_as_error(real_case: RealCase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run, _ = real_case()
    tid = _task_for_tool(run, "parse_evtx_security")
    _fn, kwargs, claimer = de._DISPATCH["parse_evtx_security"]

    def _raise(*_a: object, **_k: object) -> ToolResult:
        raise BackendUnavailableError("evtx backend missing")

    monkeypatch.setitem(de._DISPATCH, "parse_evtx_security", (_raise, kwargs, claimer))
    refs = dispatch_run(run, settings=load_settings(), task_id=tid)
    assert refs[0].status == "error"  # missing backend is NOT retryable
    tr = TaskResult.model_validate_json(run.result_path(tid).read_text(encoding="utf-8"))
    assert tr.status == "error"

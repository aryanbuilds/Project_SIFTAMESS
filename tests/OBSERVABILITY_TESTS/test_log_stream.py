"""Real-time log stream (observability) — unit tests, no TTY required.

Covers the load-bearing determinism invariant (the chokepoint edits never mutate run-dir
bytes), tag classification, progress math, TTY gating, sink-exception swallowing, hostile
markup escaping, parallel-dispatch staging filtering, and the CLI flag (no stdout change).
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from rich.console import Console
from siftmesh_core.ledgers.jsonl_ledger import append_record
from siftmesh_core.observability import sinks, stream
from siftmesh_core.observability.events import classify_event, classify_record
from siftmesh_core.observability.stream import LogStreamer, install_stream_if_enabled, stream_logs
from siftmesh_core.schemas.agent_call import AgentCall
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """No sink may leak between tests (the registry is module-global by design)."""
    sinks._SINKS.clear()
    yield
    sinks._SINKS.clear()


def _capture() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=200, highlight=False, markup=True), buf


def _agent_call() -> AgentCall:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    return AgentCall(
        agent_call_id="AGENT-001",
        task_id="TASK-001",
        profile="deterministic_executor",
        adapter="DeterministicExecutor",
        backend="real",
        start_time_utc=ts,
        end_time_utc=ts,
        status="success",
    )


# ---- determinism: the chokepoint must never change a run-dir byte -----------------------------
def test_append_record_noop_invariant(tmp_path: Path) -> None:
    rec = _agent_call()
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"
    # (1) no sink registered
    p_a = append_record(run_a, "audit/agent_calls.jsonl", rec)
    # (2) a capturing sink registered — the file output must be byte-identical
    captured: list[tuple[str, str]] = []
    sinks.register(
        SimpleNamespace(  # type: ignore[arg-type]
            on_event=lambda e, f: None,
            on_record=lambda rr, rel, r: captured.append((rel, type(r).__name__)),
        )
    )
    p_b = append_record(run_b, "audit/agent_calls.jsonl", rec)
    assert p_a.read_bytes() == p_b.read_bytes()  # the determinism guarantee
    assert captured == [("audit/agent_calls.jsonl", "AgentCall")]  # but the sink still saw it


def test_sink_exception_never_breaks_the_write(tmp_path: Path) -> None:
    def boom(*_: object) -> None:
        raise RuntimeError("sink blew up")

    sinks.register(SimpleNamespace(on_event=boom, on_record=boom))  # type: ignore[arg-type]
    # append_record + emit_record must still write the line despite the raising sink.
    p = append_record(tmp_path / "r", "audit/agent_calls.jsonl", _agent_call())
    assert p.read_text(encoding="utf-8").count("\n") == 1
    sinks.emit_event("transition", {"from_state": "plan", "to_state": "dispatch"})  # no raise


# ---- tag classification ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("event", "fields", "tag", "needle"),
    [
        (
            "transition",
            {"from_state": "plan", "to_state": "dispatch", "iteration": 0},
            "tasks",
            "→",
        ),
        (
            "task_dispatched",
            {"task_id": "TASK-003", "profile": "claude", "status": "success"},
            "tasks",
            "TASK-003",
        ),
        ("decision", {"action": "retry", "reason": "malformed"}, "tasks", "retry"),
        ("gate_rejected", {"gate": "plan", "state": "halt"}, "alert", "gate plan"),
        (
            "critic_verdict",
            {"task_id": "TASK-002", "verdict": "retry_required"},
            "result",
            "retry_required",
        ),
        ("reports_generated", {"count": 5}, "output", "5"),
        ("run_complete", {"run": "RUN-X"}, "output", "run complete"),
        ("budget_routed", {"task_id": "TASK-007"}, "info", "budget_routed"),
    ],
)
def test_classify_event(event: str, fields: dict, tag: str, needle: str) -> None:
    got_tag, summary = classify_event(event, fields)
    assert got_tag == tag
    assert needle in summary


@pytest.mark.parametrize(
    ("rel", "attrs", "tag", "task", "needle"),
    [
        (
            "audit/agent_calls.jsonl",
            {
                "agent_call_id": "AGENT-1",
                "task_id": "TASK-1",
                "profile": "claude",
                "status": "success",
            },
            "agent",
            "TASK-1",
            "claude",
        ),
        (
            "audit/tool_calls.jsonl",
            {
                "tool_call_id": "TOOL-1",
                "tool_name": "parse_evtx_security",
                "status": "success",
                "source_artifact": "/x/Security.evtx",
            },
            "tool_log",
            None,
            "parse_evtx_security",
        ),
        (
            "claims/injection_alerts.jsonl",
            {"task_id": "TASK-1", "severity": "low", "description": "ignore previous"},
            "alert",
            "TASK-1",
            "injection?",
        ),
        (
            "claims/claim_ledger.jsonl",
            {
                "claim_id": "C-1",
                "task_id": "TASK-1",
                "status": "confirmed",
                "confidence": 0.9,
                "claim": "host SRL-FORGE",
            },
            "result",
            "TASK-1",
            "C-1",
        ),
        (
            "audit/critic_verdicts.jsonl",
            {"task_id": "TASK-9", "verdict": "accepted"},
            "result",
            "TASK-9",
            "accepted",
        ),
        (
            "audit/retries.jsonl",
            {"task_id": "TASK-2", "attempt": 2, "retry_cause": "recoverable"},
            "alert",
            "TASK-2",
            "retry",
        ),
    ],
)
def test_classify_record(rel: str, attrs: dict, tag: str, task: str | None, needle: str) -> None:
    got_tag, summary, task_id = classify_record(rel, SimpleNamespace(**attrs))
    assert got_tag == tag
    assert task_id == task
    assert needle in summary


# ---- rendering: hostile markup is escaped, staging is filtered, progress math -----------------
def test_markup_escape_of_hostile_evidence() -> None:
    console, buf = _capture()
    streamer = LogStreamer(console=console)
    rec = SimpleNamespace(
        claim_id="C-1",
        task_id="TASK-1",
        status="unsupported",
        confidence=0.5,
        claim="[red]evil[/]\nSECOND-LINE-INJECT",
    )
    streamer.on_record(Path("/run"), "claims/claim_ledger.jsonl", rec)
    out = buf.getvalue()
    # brackets survive as LITERAL text (markup not interpreted) and the newline was stripped,
    # so the injected second line can't start its own log line.
    assert "[red]evil[/]" in out
    assert "SECOND-LINE-INJECT" in out
    assert "\nSECOND-LINE-INJECT" not in out


def test_staging_writes_are_filtered() -> None:
    console, buf = _capture()
    streamer = LogStreamer(console=console)
    rec = SimpleNamespace(agent_call_id="A-1", task_id="TASK-1", profile="claude", status="success")
    streamer.on_record(Path("/run/.staging/TASK-1/RUN-X"), "audit/agent_calls.jsonl", rec)
    assert buf.getvalue() == ""  # worker staging write ignored (re-emitted at commit)
    streamer.on_record(Path("/run"), "audit/agent_calls.jsonl", rec)
    assert "A-1" in buf.getvalue()  # real run-dir write streams


def test_progress_math(tmp_path: Path) -> None:
    (tmp_path / "tasks").mkdir()
    (tmp_path / "results").mkdir()
    for i in range(3):
        (tmp_path / "tasks" / f"TASK-00{i}.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "results" / "TASK-000.result.json").write_text("{}", encoding="utf-8")
    console, buf = _capture()
    streamer = LogStreamer(console=console, run_root=tmp_path)
    streamer.on_event("transition", {"from_state": "plan", "to_state": "dispatch", "iteration": 0})
    assert "1/3 (33%)" in buf.getvalue()


def test_progress_no_zero_division() -> None:
    console, buf = _capture()
    LogStreamer(console=console)._progress()  # run_root None → 0/0, must not raise
    assert "0/0" in buf.getvalue()


def test_task_separator_once_per_task() -> None:
    console, buf = _capture()
    streamer = LogStreamer(console=console)
    rec = SimpleNamespace(agent_call_id="A-1", task_id="TASK-1", profile="claude", status="success")
    streamer.on_record(Path("/run"), "audit/agent_calls.jsonl", rec)
    streamer.on_record(Path("/run"), "audit/agent_calls.jsonl", rec)
    assert buf.getvalue().count("TASK-1") >= 2  # separator + line(s), but only one rule
    assert streamer._seen_task == {"TASK-1"}


# ---- gating + registration symmetry ----------------------------------------------------------
def test_stream_logs_gating_and_symmetry() -> None:
    with stream_logs(force=False) as s:
        assert s is None
        assert not sinks.active()
    with stream_logs(force=True) as s:
        assert isinstance(s, LogStreamer)
        assert sinks.active()
    assert not sinks.active()  # unregistered on exit


def test_install_stream_if_enabled() -> None:
    install_stream_if_enabled("run", stream=True, quiet=False)
    assert sinks.active()
    sinks._SINKS.clear()
    install_stream_if_enabled("tui", stream=True, quiet=False)  # excluded command
    assert not sinks.active()
    install_stream_if_enabled("run", stream=True, quiet=True)  # quiet forces off
    assert not sinks.active()
    install_stream_if_enabled("run", stream=None, quiet=False)  # default + no TTY (pytest) → off
    assert not sinks.active()


def test_enabled_handles_stubbed_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream.sys, "stderr", object())  # no .isatty attribute
    assert stream._enabled(None) is False  # never crashes, defaults off


# ---- CLI: streaming is stderr-only + TTY-gated, so stdout is unchanged ------------------------
def test_cli_no_stream_flag_leaves_stdout_identical(
    make_real_run, runner: CliRunner, cli_app: typer.Typer
) -> None:
    run, _ = make_real_run(dispatch=True, critique=True)
    r_default = runner.invoke(cli_app, ["report", str(run.root)])
    r_quiet = runner.invoke(cli_app, ["--no-stream", "report", str(run.root)])
    r_stream = runner.invoke(cli_app, ["--stream", "report", str(run.root)])
    assert r_default.exit_code == 0
    assert r_quiet.exit_code == 0
    assert r_stream.exit_code == 0
    # CliRunner is non-TTY and streaming is stderr-only → stdout is byte-identical regardless.
    assert r_default.output == r_quiet.output == r_stream.output

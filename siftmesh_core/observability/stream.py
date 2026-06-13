"""Rich terminal log streamer: scrolling tagged lines + per-task separators + % complete.

Writes ONLY to stderr (never a run-dir file), so it cannot affect golden bytes. It is NOT a
full-screen ``Live`` — the Textual cockpit is the full TUI; this is the lightweight,
scrollback-friendly "simple realtime logs" experience for the plain CLI. Streaming is on by
default when stderr is a TTY; ``--quiet``/``--no-stream`` forces it off, ``--stream`` forces
it on (e.g. for a piped demo recording).
"""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from siftmesh_core.observability import sinks
from siftmesh_core.observability.events import TAG_STYLE, classify_event, classify_record

# Events after which we refresh the one-line progress summary (not every line — keeps it cheap).
_PROGRESS_EVENTS = frozenset(
    {
        "transition",
        "task_dispatched",
        "result_collected",
        "decision",
        "cap_reached",
        "plan_complete",
    }
)
# Orchestration events that merely duplicate a ledger record we already stream — suppress the
# event so each fact appears once (critic_verdict↔critic_verdicts.jsonl,
# claim_promoted↔claim_ledger.jsonl, critic_injection_detected↔injection_alerts.jsonl). The last
# matters at scale: the ROCBA run logs ~3,949 injection alerts — double-printing would flood.
_SUPPRESS_EVENTS = frozenset({"critic_verdict", "claim_promoted", "critic_injection_detected"})
# Commands that get a streamer by default; excludes the TUI (owns the terminal) and the MCP
# server (a stdio protocol subprocess). Read-only/inspection commands simply emit nothing.
_STREAM_COMMANDS = frozenset(
    {
        "run",
        "resume",
        "dispatch",
        "collect",
        "critique",
        "report",
        "replay",
        "retry",
        "merge",
        "init-case",
        "plan",
        "evidence",
        "prune",
    }
)


@dataclass
class LogStreamer:
    """A :class:`sinks.Sink` that renders tagged log lines to a Rich console (stderr)."""

    console: Any
    run_root: Path | None = None
    _t0: float = field(default_factory=time.monotonic)
    _seen_task: set[str] = field(default_factory=set)
    _task_t0: dict[str, float] = field(default_factory=dict)
    _last_counts: tuple[int, int] | None = None

    # ---- Sink protocol -------------------------------------------------------------------
    def on_event(self, event: str, fields: dict[str, Any]) -> None:
        if event in _SUPPRESS_EVENTS:  # the matching ledger record already streams this fact
            return
        tag, summary = classify_event(event, fields)
        self._task_header(fields.get("task_id") or fields.get("task"))
        self._line(tag, summary)
        if event in _PROGRESS_EVENTS:
            self._progress()

    def on_record(self, run_root: Path, rel: str, record: Any) -> None:
        if ".staging" in run_root.parts:  # parallel-dispatch worker write — re-emitted at commit
            return
        if self.run_root is None:
            self.run_root = run_root  # latch the real run dir for the progress %
        tag, summary, task_id = classify_record(rel, record)
        self._task_header(task_id)
        self._line(tag, summary)

    # ---- rendering -----------------------------------------------------------------------
    def _task_header(self, task_id: str | None) -> None:
        if task_id and task_id not in self._seen_task:
            self._seen_task.add(task_id)
            self._task_t0[task_id] = time.monotonic()
            with contextlib.suppress(Exception):
                self.console.rule(f"[bold cyan]{task_id}[/]", style="cyan")

    def _line(self, tag: str, summary: str) -> None:
        style = TAG_STYLE.get(tag, "white")
        with contextlib.suppress(Exception):
            # `\[tag]` renders a literal "[tag]"; `summary` is already markup-escaped.
            self.console.print(rf"[{style}]\[{tag}][/] {summary}", markup=True, highlight=False)

    def _progress(self) -> None:
        from siftmesh_core.tui.widgets import fmt_duration

        done, total = self._counts()
        if (done, total) == self._last_counts:  # only reprint when the N/M actually moved
            return
        self._last_counts = (done, total)
        pct = int(100 * done / total) if total else 0
        elapsed = fmt_duration(time.monotonic() - self._t0)
        with contextlib.suppress(Exception):
            self.console.print(
                rf"[bold cyan]\[tasks][/] ▸ {done}/{total} ({pct}%) · {elapsed} elapsed",
                markup=True,
                highlight=False,
            )

    def _counts(self) -> tuple[int, int]:
        if self.run_root is None:
            return 0, 0
        try:
            total = sum(1 for _ in (self.run_root / "tasks").glob("TASK-*.yaml"))
            done = sum(1 for _ in (self.run_root / "results").glob("TASK-*.result.json"))
        except OSError:
            return 0, 0
        return done, total


def _enabled(force: bool | None) -> bool:
    """Resolve the on/off decision: explicit force wins, else require an interactive stderr."""
    if force is not None:
        return force
    try:
        return bool(sys.stderr.isatty())
    except Exception:
        return False


def _new_console() -> Any:
    from rich.console import Console

    return Console(file=sys.stderr, stderr=True, highlight=False, soft_wrap=False)


@contextlib.contextmanager
def stream_logs(*, run_root: Path | None = None, force: bool | None = None) -> Iterator[Any]:
    """Register a :class:`LogStreamer` for the duration of the block (or ``None`` if off)."""
    if not _enabled(force):
        yield None
        return
    streamer = LogStreamer(console=_new_console(), run_root=run_root)
    sinks.register(streamer)
    try:
        yield streamer
    finally:
        sinks.unregister(streamer)


def install_stream_if_enabled(command: str | None, *, stream: bool | None, quiet: bool) -> None:
    """CLI hook: register a streamer for a long-running command (no unregister — process-scoped).

    ``stream``/``quiet`` come from the global flags: ``--quiet``/``--no-stream`` → off,
    ``--stream`` → on, default (``None``) → on iff stderr is a TTY (so CliRunner/pipes get
    nothing and tests are unaffected).
    """
    if command not in _STREAM_COMMANDS:
        return
    force = False if quiet else stream
    if not _enabled(force):
        return
    sinks.register(LogStreamer(console=_new_console()))

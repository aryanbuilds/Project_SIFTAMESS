"""Real-time observability: stream the run's ledger writes as tagged terminal logs.

The two universal ledger chokepoints (``ledgers.audit_log.log_event`` and
``ledgers.jsonl_ledger.append_record``) call :func:`sinks.emit_event` /
:func:`sinks.emit_record` *after* their durable write. With no sink registered both are a
single empty-list check — files (and the golden bytes) are never touched. The CLI registers
a :class:`stream.LogStreamer` (Rich, stderr-only, TTY-gated) so any command streams a
scrolling tagged log with per-task separators and a completion percentage. The Textual TUI
reads the same files by polling and never registers a sink (no conflict).
"""

from __future__ import annotations

from siftmesh_core.observability.sinks import (
    Sink,
    emit_event,
    emit_record,
    register,
    unregister,
)
from siftmesh_core.observability.stream import (
    LogStreamer,
    install_stream_if_enabled,
    stream_logs,
)

__all__ = [
    "LogStreamer",
    "Sink",
    "emit_event",
    "emit_record",
    "install_stream_if_enabled",
    "register",
    "stream_logs",
    "unregister",
]

"""Sink registry + dispatch for real-time observability.

Dependency-light by design (stdlib only): this module is imported by the two ledger
chokepoints, so the no-sink hot path must be a single empty-list check and add no import
cost. Sinks are stored in a module-global list under a lock — NOT contextvars — because
``parallel_dispatch`` worker threads (which do not inherit contextvars) also call the
chokepoints; the lock keeps iteration safe and the :class:`Sink` filters their staging
writes out by ``run_root`` (see ``stream.LogStreamer``).

A sink must NEVER crash the run: every callback is wrapped in ``try/except`` and the
durable file write always precedes the emit, so a misbehaving sink cannot affect the
ledger contents or their ordering.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Sink(Protocol):
    """Receives ledger writes as they happen. Implementations must not raise."""

    def on_event(self, event: str, fields: dict[str, Any]) -> None:
        """An orchestration event (``log_event``)."""

    def on_record(self, run_root: Path, rel: str, record: Any) -> None:
        """A typed ledger record (``append_record``); ``rel`` identifies the ledger."""


_SINKS: list[Sink] = []
_LOCK = threading.Lock()


def register(sink: Sink) -> None:
    """Add a sink. Idempotent-safe; callers normally pair with :func:`unregister`."""
    with _LOCK:
        _SINKS.append(sink)


def unregister(sink: Sink) -> None:
    """Remove a previously registered sink (no-op if absent)."""
    with _LOCK, contextlib.suppress(ValueError):
        _SINKS.remove(sink)


def active() -> bool:
    """True if at least one sink is registered (for cheap external short-circuits)."""
    return bool(_SINKS)


def emit_event(event: str, fields: dict[str, Any]) -> None:
    """Dispatch an orchestration event to all sinks (near-noop when none registered)."""
    if not _SINKS:  # hot path: one list-truthiness check, no lock, no allocation
        return
    with _LOCK:
        sinks = tuple(_SINKS)
    for sink in sinks:
        try:
            sink.on_event(event, fields)
        except Exception:  # a sink must never crash the run
            continue


def emit_record(run_root: Path | str, rel: str | Path, record: Any) -> None:
    """Dispatch a typed ledger record to all sinks (near-noop when none registered)."""
    if not _SINKS:
        return
    with _LOCK:
        sinks = tuple(_SINKS)
    rr = Path(run_root)
    rel_s = str(rel)
    for sink in sinks:
        try:
            sink.on_record(rr, rel_s, record)
        except Exception:
            continue

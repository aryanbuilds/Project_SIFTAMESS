"""Orchestration audit log (B8): init-case state transitions.

Thin wrapper over the base JSONL logger (A5) that appends one structured event
per init-case transition to ``audit/orchestration_events.jsonl`` — UTC, ordered,
replayable. The event vocabulary is kept fixed so the audit trail stays greppable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from siftmesh_core.logging import bind_run, configure_jsonl_logging


def open_orchestration_log(events_path: Path, run_id: str) -> structlog.typing.FilteringBoundLogger:
    """Return a run-bound JSONL logger writing to ``events_path``."""
    return bind_run(configure_jsonl_logging(events_path), run_id)


def log_event(logger: structlog.typing.FilteringBoundLogger, event: str, **fields: Any) -> None:
    """Append one orchestration event at info level."""
    logger.info(event, **fields)

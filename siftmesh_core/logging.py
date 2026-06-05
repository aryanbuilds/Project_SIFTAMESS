"""Append-only JSONL logging for SIFTMesh audit/claim ledgers (structlog 25.5.x).

Each line is one valid JSON object: UTC ISO-8601 `timestamp` (...Z) + `level` +
bound context (e.g. run_id) + `event`. WriteLoggerFactory writes the JSON string
from JSONRenderer directly to the file and flushes after every record, so there
is no buffered loss. The file is opened once in append mode ('a' -> O_APPEND) so
single sub-PIPE_BUF line writes do not interleave/corrupt on Linux.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

import structlog

INFO = 20  # logging.INFO numeric level (avoid importing stdlib logging)


def configure_jsonl_logging(log_path: Path) -> structlog.typing.FilteringBoundLogger:
    """Configure structlog to APPEND one JSON object per line to *log_path*.

    Returns a bound logger. Call this once before any ``structlog.get_logger()``
    because ``cache_logger_on_first_use=True`` freezes config on first use.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 'a' => O_APPEND: kernel seeks to EOF before each write; encoding hygiene.
    # WriteLogger flushes every record itself, so line_buffering is unnecessary.
    file_handle: TextIO = log_path.open("a", encoding="utf-8")

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,  # generic, NOT stdlib -> "level"
            structlog.processors.TimeStamper(fmt="iso", utc=True),  # -> "...Z"
            structlog.processors.JSONRenderer(),  # -> one JSON object (str)
        ],
        logger_factory=structlog.WriteLoggerFactory(file=file_handle),
        wrapper_class=structlog.make_filtering_bound_logger(INFO),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


def bind_run(
    logger: structlog.typing.FilteringBoundLogger, run_id: str
) -> structlog.typing.FilteringBoundLogger:
    """Bind a run_id onto every subsequent record from the returned logger."""
    return logger.bind(run_id=run_id)

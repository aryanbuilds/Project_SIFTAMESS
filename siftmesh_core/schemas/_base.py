"""Shared schema primitives (Epic C foundation, used by the B pull-forward).

``UtcDateTime`` forces JSON serialization to UTC ISO-8601 with a ``Z`` suffix
(D4 — UTC everywhere) regardless of the input timezone, while keeping the
in-memory value a real ``datetime``. ``StrictModel`` fails closed on unknown
fields (D5 — a model that fails validation is never written to disk).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def _iso_utc(value: datetime) -> str:
    """Serialize a datetime as UTC ISO-8601 with a ``Z`` suffix.

    Naive datetimes are assumed to already be UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_iso_utc, return_type=str, when_used="json"),
]


class StrictModel(BaseModel):
    """Base model: reject unknown fields (fail-closed)."""

    model_config = ConfigDict(extra="forbid")

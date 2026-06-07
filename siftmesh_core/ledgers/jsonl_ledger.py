"""Generic typed JSONL ledger (C7): validate-before-write, validate-on-read.

Append one validated Pydantic model per line through the path policy, and stream
records back as typed objects. A model is constructed (validated) before it can be
written, so a malformed record can never reach disk; a corrupt line on read raises
a clear error rather than being silently skipped (audit integrity, criterion 5).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.schemas._base import StrictModel

ModelT = TypeVar("ModelT", bound=StrictModel)


class LedgerCorruptionError(Exception):
    """A ledger line failed to parse/validate (never silently skipped)."""


def append_record(
    run_root: Path | str,
    rel: str | Path,
    record: StrictModel,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one validated model as a JSONL line (UTC-Z JSON) via the path policy."""
    target = safe_write_path(run_root, rel, evidence_root=evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as out:
        out.write(record.model_dump_json() + "\n")
    return target


def read_records(path: Path | str, model_cls: type[ModelT]) -> Iterator[ModelT]:
    """Yield typed records from a JSONL ledger; raise on the first corrupt line."""
    source = Path(path)
    if not source.exists():
        return
    with source.open(encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield model_cls.model_validate_json(line)
            except ValidationError as exc:
                raise LedgerCorruptionError(f"{source}:{lineno}: {exc}") from exc

"""Timeline tool (D8) — deterministic merge of real rows into one ordered timeline.

``build_timeline`` parses each input artifact via the real backend (EVTX events,
prefetch last-run times, ``$MFT`` standard-information times) and merges them into a
single chronologically-sorted list of ``{timestamp_utc, source_kind, source_artifact,
detail}`` rows. Own deterministic code — no external timeline engine (Plaso
enrichment is out of scope for the MVP). Logs a provenance line.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import Backend, BackendUnavailableError, get_backend
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult

# Supported input kinds -> the backend extraction they drive.
TIMELINE_KINDS: frozenset[str] = frozenset({"evtx", "prefetch", "mft"})


class TimelineResult(ToolResult):
    """A merged, chronologically-sorted timeline over several artifacts."""

    event_count: int = 0
    sources: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


def _rows_for(backend: Backend, kind: str, path: Path, artifact: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if kind == "evtx":
        for event in backend.parse_evtx(path):
            rows.append(
                {
                    "timestamp_utc": event.get("timestamp_utc"),
                    "source_kind": "evtx",
                    "source_artifact": artifact,
                    "detail": f"EventID {event.get('event_id')} ({event.get('channel')})",
                }
            )
    elif kind == "prefetch":
        info = backend.analyze_prefetch(path)
        for run_time in info.get("last_run_times", []):
            rows.append(
                {
                    "timestamp_utc": run_time,
                    "source_kind": "prefetch",
                    "source_artifact": artifact,
                    "detail": f"ran {info.get('executable_filename')}",
                }
            )
    elif kind == "mft":
        for entry in backend.parse_mft(path):
            rows.append(
                {
                    "timestamp_utc": entry.get("si_modified"),
                    "source_kind": "mft",
                    "source_artifact": artifact,
                    "detail": f"$MFT modified: {entry.get('name')}",
                }
            )
    return rows


def build_timeline(
    run_root: Path | str,
    *,
    inputs: list[dict[str, str]],
    evidence_root: Path | str,
    backend_mode: str = "real",
) -> TimelineResult:
    """Merge EVTX / prefetch / ``$MFT`` rows from ``inputs`` into one sorted timeline.

    ``inputs`` is a list of ``{"artifact": <evidence-rel path>, "kind": <evtx|prefetch|mft>}``.
    """
    backend = get_backend(backend_mode)
    resolved: list[tuple[str, str, Path, str]] = []
    for item in inputs:
        kind = item["kind"]
        if kind not in TIMELINE_KINDS:
            raise ValueError(f"unsupported timeline kind: {kind!r}")
        path, sha = resolved_source(evidence_root, item["artifact"])
        resolved.append((kind, item["artifact"], path, sha))
    digest = hashlib.sha256(
        "".join(sorted(sha for *_, sha in resolved)).encode("utf-8")
    ).hexdigest()

    def produce() -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        try:
            for kind, artifact, path, _sha in resolved:
                rows.extend(_rows_for(backend, kind, path, artifact))
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real parse failure -> recoverable (logged status=error)
            raise RecoverableToolError(f"timeline build failed: {exc}", code="parse_error") from exc
        # Sort chronologically; rows with no timestamp sort last (None -> True).
        rows.sort(key=lambda row: (row["timestamp_utc"] is None, row["timestamp_utc"] or ""))
        return {
            "event_count": len(rows),
            "sources": [artifact for _, artifact, _, _ in resolved],
            "events": rows,
        }

    return run_tool(
        run_root,
        result_cls=TimelineResult,
        tool_name="build_timeline",
        source_artifact="timeline",
        source_sha256=digest,
        backend=backend.name,
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )

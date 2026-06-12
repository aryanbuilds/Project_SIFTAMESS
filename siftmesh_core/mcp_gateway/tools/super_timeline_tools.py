"""Super-timeline tool (Epic C) — a whole-image Plaso chronology (subprocess-only, gated).

``build_super_timeline`` runs Plaso (``log2timeline.py`` + ``psort.py``) over a disk image and
returns a normalised, capped event list (the full ``.plaso`` + ``json_line`` output stay on disk
under the run dir). It consolidates every parser Plaso supports into one timeline (Q5). Heavy +
opt-in: only the ``enable_super_timeline`` planner path emits it, and it runs on the deterministic
floor. A missing Plaso binary fails closed. Logs provenance to ``audit/tool_calls.jsonl``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.evidence.super_timeline import build_plaso_timeline
from siftmesh_core.mcp_gateway.audit_exec import RecoverableToolError, run_tool
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult

# Cap the events embedded in the structured result; the full timeline stays on disk under the run.
_MAX_EVENTS = 200_000


class SuperTimelineResult(ToolResult):
    """A Plaso super-timeline over one disk image (capped events; full output on disk)."""

    event_count: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)
    timeline_path: str | None = None


def build_super_timeline(
    run_root: Path | str,
    *,
    image_artifact: str,
    evidence_root: Path | str,
    log2timeline_path: str | None = None,
    psort_path: str | None = None,
    timeout: int = 3600,
    max_events: int = _MAX_EVENTS,
    backend_mode: str = "sift_lane",
) -> SuperTimelineResult:
    """Build a Plaso super-timeline across a disk image (opt-in/gated; host-validated)."""
    image_path, image_sha = resolved_source(evidence_root, image_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        work_dir = Path(run_root) / "evidence" / "extracted" / "super_timeline"
        try:
            events, total, jsonl = build_plaso_timeline(
                image_path,
                work_dir=work_dir,
                log2timeline_path=log2timeline_path,
                psort_path=psort_path,
                timeout=timeout,
                max_events=max_events,
            )
        except BackendUnavailableError:
            raise
        except Exception as exc:  # real Plaso failure -> recoverable (logged status=error)
            raise RecoverableToolError(
                f"super-timeline build failed: {exc}", code="plaso_error"
            ) from exc
        return {"event_count": total, "events": events, "timeline_path": str(jsonl)}

    return run_tool(
        run_root,
        result_cls=SuperTimelineResult,
        tool_name="build_super_timeline",
        source_artifact=image_artifact,
        source_sha256=image_sha,
        backend="sift_lane",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )

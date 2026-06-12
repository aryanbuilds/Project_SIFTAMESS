"""Super-timeline tool for building a Plaso chronology."""

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

_MAX_EVENTS = 200_000


class SuperTimelineResult(ToolResult):
    """Plaso super-timeline result."""

    event_count: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)
    timeline_path: str | None = None
    timeline_source: str | None = None


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
    image_path, image_sha = resolved_source(evidence_root, image_artifact, run_root=run_root)

    def produce() -> dict[str, Any]:
        work_dir = Path(run_root) / "super_timeline"
        extracted = Path(run_root) / "evidence" / "extracted"

        def _run(src: Path, *, is_dir: bool) -> tuple[list[dict[str, Any]], int, Any]:
            return build_plaso_timeline(
                src,
                work_dir=work_dir,
                is_directory=is_dir,
                log2timeline_path=log2timeline_path,
                psort_path=psort_path,
                timeout=timeout,
                max_events=max_events,
            )

        try:
            events, total, jsonl = _run(image_path, is_dir=False)
            source = "disk_image"
        except BackendUnavailableError:
            raise
        except Exception as exc_image:
            if not (extracted.is_dir() and any(extracted.rglob("*"))):
                raise RecoverableToolError(
                    f"super-timeline build failed: {exc_image}", code="plaso_error"
                ) from exc_image
            try:
                events, total, jsonl = _run(extracted, is_dir=True)
                source = "extracted_artifacts"
            except Exception as exc_dir:
                raise RecoverableToolError(
                    f"super-timeline build failed (image + extracted): {exc_dir}",
                    code="plaso_error",
                ) from exc_dir
        return {
            "event_count": total,
            "events": events,
            "timeline_path": str(jsonl),
            "timeline_source": source,
        }

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

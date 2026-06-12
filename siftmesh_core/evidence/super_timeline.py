"""Plaso super-timeline (host tool, subprocess-only) — ``log2timeline.py`` + ``psort.py``.

Builds a whole-image super-timeline by running Plaso as an **external fixed-argv subprocess**
(``shell=False``): ``log2timeline.py`` ingests the disk image into a run-scoped ``.plaso`` store,
then ``psort.py -o json_line`` exports newline-delimited JSON events, which are normalised into
typed rows. Plaso is Apache-2.0 but is invoked as a subprocess (never imported), consistent with
the Volatility lane. A missing binary **fails closed** (:class:`BackendUnavailableError`); a
non-zero exit raises (the tool layer records ``status=error``). Heavy (10-60 min, GBs RAM) and
host-gated — only the opt-in ``enable_super_timeline`` planner path emits it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_LOG2TIMELINE = "log2timeline.py"
_PSORT = "psort.py"


def _require(tool: str, override: str | None = None) -> str:
    """Resolve a Plaso binary (explicit override path, else PATH) or fail closed."""
    if override and Path(override).exists():
        return override
    found = shutil.which(override or tool)
    if found:
        return found
    raise BackendUnavailableError(f"Plaso tool {tool!r} not found (install plaso); fails closed")


def _norm_event(ev: dict[str, object]) -> dict[str, object]:
    """Normalise one psort ``json_line`` event to a stable row (graceful on key drift)."""
    return {
        "timestamp_utc": ev.get("datetime") or ev.get("timestamp"),
        "timestamp_desc": ev.get("timestamp_desc"),
        "message": ev.get("message"),
        "source_short": ev.get("source_short"),
        "source_long": ev.get("source_long"),
        "parser": ev.get("parser"),
        "data_type": ev.get("data_type"),
        "display_name": ev.get("display_name"),
    }


def parse_psort_jsonl(
    path: Path, *, max_events: int | None = None
) -> tuple[list[dict[str, object]], int]:
    """Parse a psort ``json_line`` file -> (first ``max_events`` rows, total event count)."""
    events: list[dict[str, object]] = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                ev = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            total += 1
            if max_events is None or len(events) < max_events:
                events.append(_norm_event(ev))
    return events, total


def build_plaso_timeline(
    image: Path,
    *,
    work_dir: Path,
    log2timeline_path: str | None = None,
    psort_path: str | None = None,
    timeout: int = 3600,
    max_events: int | None = None,
) -> tuple[list[dict[str, object]], int, Path]:
    """Run ``log2timeline.py`` then ``psort.py`` over ``image`` -> (events, total, jsonl_path)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    storage = work_dir / "timeline.plaso"
    out = work_dir / "timeline.jsonl"
    l2t = _require(_LOG2TIMELINE, log2timeline_path)
    psort = _require(_PSORT, psort_path)

    ingest = subprocess.run(  # fixed argv, shell=False, validated image path
        [
            l2t,
            "--status_view",
            "none",
            "--partitions",
            "all",
            "--storage_file",
            str(storage),
            str(image),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if ingest.returncode != 0:
        raise RuntimeError(f"log2timeline failed: {ingest.stderr.strip()[:500] or 'non-zero exit'}")

    export = subprocess.run(  # fixed argv, shell=False
        [psort, "-o", "json_line", "-w", str(out), str(storage)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if export.returncode != 0:
        raise RuntimeError(f"psort failed: {export.stderr.strip()[:500] or 'non-zero exit'}")

    events, total = parse_psort_jsonl(out, max_events=max_events)
    return events, total, out

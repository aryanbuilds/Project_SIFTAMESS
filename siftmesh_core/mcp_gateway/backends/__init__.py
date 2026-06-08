"""Forensic backend abstraction (D3) — real (in-process) vs SIFT-lane (host).

Two backend modes behind one typed interface, selected by config — no placeholder,
no fake fallback (REAL-ONLY, CLAUDE.md §2B):

* :class:`~siftmesh_core.mcp_gateway.backends.real.RealBackend` — in-process Python
  library calls (evtx / regipy / pyscca / mft), zero subprocess. Default; the demo
  path.
* :class:`~siftmesh_core.mcp_gateway.backends.sift_lane.SiftLaneBackend` — a gated
  seam for fixed-argv SANS-SIFT host CLIs (wired in D12); fails closed until then.

A missing library/backend raises :class:`BackendUnavailableError` (fail closed); it
is never silently replaced by synthetic output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class BackendUnavailableError(RuntimeError):
    """Raised when a required backend/library is unavailable (fails closed)."""


@runtime_checkable
class Backend(Protocol):
    """The forensic extraction primitives the typed tools delegate to."""

    name: str

    def parse_evtx(
        self,
        path: Path,
        *,
        event_id_filter: frozenset[int] | None = None,
        channel_filter: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def analyze_prefetch(self, path: Path) -> dict[str, Any]: ...

    def extract_run_keys(self, path: Path) -> list[dict[str, Any]]: ...

    def parse_mft(self, path: Path) -> list[dict[str, Any]]: ...


def get_backend(mode: str | None = None) -> Backend:
    """Return the configured backend (the ``real`` ↔ ``sift_lane`` config flip, D12).

    ``None`` resolves from ``SiftmeshSettings.backend_mode`` (env/toml/default), so a single
    config knob switches every typed tool between in-process libs and the SIFT-host EZ Tools.
    ``auto`` resolves to the in-process real backend.
    """
    if mode is None:
        from siftmesh_core.config import load_settings

        mode = load_settings().backend_mode
    if mode in ("real", "auto"):
        from siftmesh_core.mcp_gateway.backends.real import RealBackend

        return RealBackend()
    if mode == "sift_lane":
        from siftmesh_core.mcp_gateway.backends.sift_lane import SiftLaneBackend

        return SiftLaneBackend()
    raise ValueError(f"unknown backend mode: {mode!r}")

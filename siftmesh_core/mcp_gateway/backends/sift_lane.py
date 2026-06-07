"""SIFT-lane backend seam (D3) — gated host CLIs, wired in D12.

Mirrors :class:`RealBackend` so SIFT-host execution is a config switch, not a fork.
Every method **fails closed** (:class:`BackendUnavailableError`) until D12 maps each
call to a fixed-argv (``shell=False``) Protocol-SIFT tool on the SANS host. No fake
output is ever emitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

from siftmesh_core.mcp_gateway.backends import BackendUnavailableError


class SiftLaneBackend:
    """Gated SANS-SIFT host backend; not wired until D12 (fails closed)."""

    name = "sift_lane"

    def _unavailable(self, op: str) -> NoReturn:
        raise BackendUnavailableError(
            f"sift_lane backend not wired yet (D12): {op}. Use backend_mode='real'."
        )

    def parse_evtx(
        self, path: Path, *, event_id_filter: frozenset[int] | None = None
    ) -> list[dict[str, Any]]:
        self._unavailable("parse_evtx")

    def analyze_prefetch(self, path: Path) -> dict[str, Any]:
        self._unavailable("analyze_prefetch")

    def extract_run_keys(self, path: Path) -> list[dict[str, Any]]:
        self._unavailable("extract_run_keys")

    def parse_mft(self, path: Path) -> list[dict[str, Any]]:
        self._unavailable("parse_mft")

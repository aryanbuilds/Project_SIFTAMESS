"""Protocol SIFT capability-map schema (D11).

The typed, validated map that ``siftmesh protocol-sift inspect --run-dir`` writes to
``context/protocol_sift_capabilities.json``. It is an honest, env-only snapshot: which
Protocol SIFT skill-layer pieces and which underlying forensic tools are present on this
host (with resolved paths), plus a per-check pass/fail list. A model that fails validation
is never written (``StrictModel`` - fail closed).
"""

from __future__ import annotations

from pydantic import Field

from siftmesh_core.schemas._base import StrictModel, UtcDateTime


class CapabilityCheck(StrictModel):
    """One inspection check (mirrors the doctor ok/warn/fail style)."""

    name: str
    status: str  # "ok" | "absent" | "warn"
    detail: str


class ProtocolSiftCapabilityMap(StrictModel):
    """Validated capability map for the Protocol SIFT layer + SIFT-host tools."""

    run_id: str
    generated_utc: UtcDateTime
    claude_home: str
    claude_code_installed: bool
    protocol_sift_installed: bool
    settings_present: bool
    case_template_present: bool
    analysis_scripts_present: bool
    skills_present: list[str] = Field(default_factory=list)
    skills_missing: list[str] = Field(default_factory=list)
    tools_present: list[str] = Field(default_factory=list)
    tools_absent: list[str] = Field(default_factory=list)
    tool_paths: dict[str, str] = Field(default_factory=dict)
    checks: list[CapabilityCheck] = Field(default_factory=list)

"""Protocol SIFT inspection (A8 / D11-basic).

Protocol SIFT is a **Claude Code config + skill layer** installed under
``~/.claude`` - *not* an MCP server (PLAN/09). SIFTMesh inspects and governs it.
These are read-only filesystem/``PATH`` checks: they need **no forensic
evidence** and are safe to run anywhere. The full capability-map-to-run-dir
version is D11; this module is the detection primitive used by both
``siftmesh doctor --protocol-sift`` and ``siftmesh protocol-sift inspect``.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.schemas.protocol_sift import CapabilityCheck, ProtocolSiftCapabilityMap

# The five Protocol SIFT skills (PLAN/09 §1).
PROTOCOL_SIFT_SKILLS: tuple[str, ...] = (
    "memory-analysis",
    "plaso-timeline",
    "sleuthkit",
    "windows-artifacts",
    "yara-hunting",
)

# Forensic tools a SIFT host exposes, each as ordered candidate absolute paths.
# If no candidate exists, fall back to a PATH lookup (``which``) per SIFT_TOOL_WHICH.
# Re-confirmed on the live SANS SIFT host (PLAN/09 §1 listed stale guesses: vol is at
# /opt/volatility3/bin/vol, NOT /opt/volatility3-2.20.0/vol.py; yara is absent here).
SIFT_TOOL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "volatility3": ("/opt/volatility3/bin/vol", "/opt/volatility3-2.20.0/vol.py"),
    "ez_tools": ("/opt/zimmermantools",),
    "yara": ("/usr/local/bin/yara",),
}

# PATH-lookup fallback binary when no candidate path for a tool exists.
SIFT_TOOL_WHICH: dict[str, str] = {
    "volatility3": "vol",
    "yara": "yara",
}

# Tools resolved purely via ``PATH`` on a SIFT host.
SIFT_PATH_TOOLS: tuple[str, ...] = (
    "log2timeline.py",
    "psort.py",
    "fls",
    "icat",
    "bulk_extractor",
    "dotnet",  # EZ Tools runtime (D12)
)


def resolve_tool(name: str) -> str | None:
    """Resolve a SIFT tool to an absolute path: candidate paths first, then ``which``."""
    for candidate in SIFT_TOOL_CANDIDATES.get(name, ()):
        if Path(candidate).exists():
            return candidate
    which_name = SIFT_TOOL_WHICH.get(name)
    if which_name:
        return shutil.which(which_name)
    return None


ORCHESTRATOR_MARKER = "Principal DFIR Orchestrator"


@dataclass
class ProtocolSiftStatus:
    """Detection result for the Protocol SIFT environment."""

    claude_home: str
    claude_code_installed: bool
    protocol_sift_installed: bool
    settings_present: bool
    case_template_present: bool
    analysis_scripts_present: bool
    skills_present: list[str] = field(default_factory=list)
    skills_missing: list[str] = field(default_factory=list)
    tools_present: list[str] = field(default_factory=list)
    tools_absent: list[str] = field(default_factory=list)
    tool_paths: dict[str, str] = field(default_factory=dict)  # resolved name -> abs path

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains(path: Path, marker: str) -> bool:
    """True if *path* is a readable file containing *marker* (never raises)."""
    try:
        return path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def detect_protocol_sift(home: Path | None = None) -> ProtocolSiftStatus:
    """Inspect the ``~/.claude`` Protocol SIFT layer (read-only, env-only)."""
    claude_home = (home or Path.home()) / ".claude"

    skills_present: list[str] = []
    skills_missing: list[str] = []
    for skill in PROTOCOL_SIFT_SKILLS:
        if (claude_home / "skills" / skill / "SKILL.md").is_file():
            skills_present.append(skill)
        else:
            skills_missing.append(skill)

    tools_present: list[str] = []
    tools_absent: list[str] = []
    tool_paths: dict[str, str] = {}
    for name in SIFT_TOOL_CANDIDATES:
        resolved = resolve_tool(name)
        if resolved:
            tools_present.append(name)
            tool_paths[name] = resolved
        else:
            tools_absent.append(name)
    for tool in SIFT_PATH_TOOLS:
        found = shutil.which(tool)
        if found:
            tools_present.append(tool)
            tool_paths[tool] = found
        else:
            tools_absent.append(tool)

    return ProtocolSiftStatus(
        claude_home=str(claude_home),
        claude_code_installed=shutil.which("claude") is not None,
        protocol_sift_installed=_contains(claude_home / "CLAUDE.md", ORCHESTRATOR_MARKER),
        settings_present=(claude_home / "settings.json").is_file(),
        case_template_present=(claude_home / "case-templates" / "CLAUDE.md").is_file(),
        analysis_scripts_present=(
            claude_home / "analysis-scripts" / "generate_pdf_report.py"
        ).is_file(),
        skills_present=skills_present,
        skills_missing=skills_missing,
        tools_present=tools_present,
        tools_absent=tools_absent,
        tool_paths=tool_paths,
    )


def _ok(present: bool) -> str:
    return "ok" if present else "absent"


def build_capability_map(run_id: str, *, home: Path | None = None) -> ProtocolSiftCapabilityMap:
    """Build the typed, validated Protocol SIFT capability map (env-only, read-only)."""
    s = detect_protocol_sift(home=home)
    checks: list[CapabilityCheck] = [
        CapabilityCheck(
            name="claude_code", status=_ok(s.claude_code_installed), detail=s.claude_home
        ),
        CapabilityCheck(
            name="protocol_sift_core",
            status=_ok(s.protocol_sift_installed),
            detail=f"CLAUDE.md '{ORCHESTRATOR_MARKER}'",
        ),
        CapabilityCheck(
            name="settings.json", status=_ok(s.settings_present), detail="permission posture"
        ),
        CapabilityCheck(
            name="case_template", status=_ok(s.case_template_present), detail="case-templates/"
        ),
        CapabilityCheck(
            name="analysis_scripts",
            status=_ok(s.analysis_scripts_present),
            detail="analysis-scripts/generate_pdf_report.py",
        ),
    ]
    for skill in PROTOCOL_SIFT_SKILLS:
        present = skill in s.skills_present
        checks.append(
            CapabilityCheck(name=f"skill:{skill}", status=_ok(present), detail="SKILL.md")
        )
    for tool in (*SIFT_TOOL_CANDIDATES, *SIFT_PATH_TOOLS):
        present = tool in s.tools_present
        checks.append(
            CapabilityCheck(
                name=f"tool:{tool}", status=_ok(present), detail=s.tool_paths.get(tool, "not found")
            )
        )
    return ProtocolSiftCapabilityMap(
        run_id=run_id,
        generated_utc=datetime.now(UTC),
        claude_home=s.claude_home,
        claude_code_installed=s.claude_code_installed,
        protocol_sift_installed=s.protocol_sift_installed,
        settings_present=s.settings_present,
        case_template_present=s.case_template_present,
        analysis_scripts_present=s.analysis_scripts_present,
        skills_present=s.skills_present,
        skills_missing=s.skills_missing,
        tools_present=s.tools_present,
        tools_absent=s.tools_absent,
        tool_paths=s.tool_paths,
        checks=checks,
    )


def write_protocol_sift_capability_map(
    run_root: Path | str,
    *,
    evidence_root: Path | str | None = None,
    home: Path | None = None,
) -> Path:
    """Write the capability map to ``context/protocol_sift_capabilities.json`` (path-policed)."""
    run_id = Path(run_root).resolve().name
    cap = build_capability_map(run_id, home=home)
    target = safe_write_path(
        run_root, Path("context") / "protocol_sift_capabilities.json", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cap.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target

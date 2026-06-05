"""Protocol SIFT inspection (A8 / D11-basic).

Protocol SIFT is a **Claude Code config + skill layer** installed under
``~/.claude`` — *not* an MCP server (PLAN/09). SIFTMesh inspects and governs it.
These are read-only filesystem/``PATH`` checks: they need **no forensic
evidence** and are safe to run anywhere. The full capability-map-to-run-dir
version is D11; this module is the detection primitive used by both
``siftmesh doctor --protocol-sift`` and ``siftmesh protocol-sift inspect``.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# The five Protocol SIFT skills (PLAN/09 §1).
PROTOCOL_SIFT_SKILLS: tuple[str, ...] = (
    "memory-analysis",
    "plaso-timeline",
    "sleuthkit",
    "windows-artifacts",
    "yara-hunting",
)

# Absolute tool paths Protocol SIFT expects on a SANS SIFT host (PLAN/09 §1).
SIFT_TOOL_PATHS: dict[str, str] = {
    "volatility3": "/opt/volatility3-2.20.0/vol.py",
    "ez_tools": "/opt/zimmermantools",
    "yara": "/usr/local/bin/yara",
}

# Tools resolved via ``PATH`` on a SIFT host.
SIFT_PATH_TOOLS: tuple[str, ...] = (
    "log2timeline.py",
    "psort.py",
    "fls",
    "icat",
    "bulk_extractor",
)

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
    for name, path in SIFT_TOOL_PATHS.items():
        (tools_present if Path(path).exists() else tools_absent).append(name)
    for tool in SIFT_PATH_TOOLS:
        (tools_present if shutil.which(tool) else tools_absent).append(tool)

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
    )

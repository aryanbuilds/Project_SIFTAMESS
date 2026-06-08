"""``siftmesh doctor`` (A8).

Verify the host + each backend and **fail closed** on a missing *required*
dependency — never a fake fallback (*missing = OK; fake = not OK*). Optional
forensic backends (the ``sift`` extra) are **reported, not required**: a missing
one is fine here; it only fails closed when the corresponding tool is actually
*used* (Epic D). Env-only — needs no forensic evidence.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.config import SiftmeshSettings, load_settings
from siftmesh_core.protocol_sift import ProtocolSiftStatus, detect_protocol_sift

OK = "ok"
FAIL = "fail"
WARN = "warn"
_MARK = {OK: "[ ok ]", FAIL: "[FAIL]", WARN: "[warn]"}

# Required runtime deps (the chassis). Missing one => fail closed.
CORE_DEPS: tuple[tuple[str, str], ...] = (
    ("typer", "Typer CLI"),
    ("pydantic", "Pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("structlog", "structlog"),
    ("mcp", "MCP SDK"),
    ("yaml", "PyYAML"),
    ("jinja2", "Jinja2"),
    ("regipy", "regipy (registry)"),
)

# Optional forensic backends (`sift` extra). Missing => reported, not a failure.
FORENSIC_DEPS: tuple[tuple[str, str], ...] = (
    ("evtx", "EVTX (pyevtx-rs)"),
    ("pyscca", "Prefetch (libscca)"),
    ("mft", "MFT (pymft-rs)"),
)

# Optional SIFT-lane host CLIs (Epic D deepening: disk-image extraction + memory
# triage). Missing => WARN, not a failure; the tool that needs one fails closed.
SIFT_LANE_TOOLS: tuple[tuple[str, str], ...] = (
    ("mmls", "Sleuthkit mmls (partitions)"),
    ("fls", "Sleuthkit fls (dir walk)"),
    ("icat", "Sleuthkit icat (file extract)"),
    ("ifind", "Sleuthkit ifind (path→inode)"),
    ("7z", "7-Zip (memory decompress)"),
)


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _cwd_writable() -> bool:
    """True if a directory can be created in the CWD (no artifacts left behind)."""
    try:
        with tempfile.TemporaryDirectory(dir=Path.cwd()):
            return True
    except OSError:
        return False


def collect_checks(settings: SiftmeshSettings | None = None) -> list[Check]:
    """Run every host/dependency/safety check and return the results."""
    settings = settings or load_settings()
    checks: list[Check] = [
        Check(
            OK if sys.version_info >= (3, 11) else FAIL,
            "python >= 3.11",
            platform.python_version(),
        ),
        # Linux-first: a non-Linux host is a warning (the chassis is portable),
        # not a failure. Real forensic execution targets Linux/SANS SIFT.
        Check(
            OK if platform.system() == "Linux" else WARN,
            "linux target",
            platform.system() or "unknown",
        ),
    ]
    for mod, human in CORE_DEPS:
        ok = _module_available(mod)
        checks.append(Check(OK if ok else FAIL, f"dep: {human}", mod if ok else f"MISSING ({mod})"))
    for mod, human in FORENSIC_DEPS:
        ok = _module_available(mod)
        checks.append(
            Check(
                OK if ok else WARN,
                f"forensic: {human}",
                "installed" if ok else "absent: uv sync --extra sift",
            )
        )
    checks.append(Check(OK if _cwd_writable() else FAIL, "run-dir writable", "case_runs/ (cwd)"))
    # Gateway tool surface (criterion 4): exactly the 8 §7 tools, none forbidden.
    from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS

    allowlist_ok = len(ALLOWED_TOOLS) == 10 and ALLOWED_TOOLS.isdisjoint(FORBIDDEN_TOOLS)
    checks.append(
        Check(
            OK if allowlist_ok else FAIL,
            "gateway tool allowlist",
            f"{len(ALLOWED_TOOLS)} tools, no forbidden",
        )
    )
    # SIFT-lane host CLIs (WARN-only): present on a SANS SIFT host, absent on a clean
    # dev/CI box. The image/memory tools fail closed if one is actually missing.
    for binary, human in SIFT_LANE_TOOLS:
        present = shutil.which(binary) is not None
        checks.append(
            Check(OK if present else WARN, f"sift-lane: {human}", binary if present else "absent")
        )
    vol_present = shutil.which("vol") is not None or Path(settings.vol_path).exists()
    checks.append(
        Check(
            OK if vol_present else WARN,
            "sift-lane: Volatility 3 (vol)",
            settings.vol_path if vol_present else "absent (subprocess-only, never imported)",
        )
    )
    # Safety posture (CLAUDE.md §11) read from config.
    checks.append(
        Check(
            OK if settings.raw_shell is False else FAIL,
            "raw_shell disabled",
            str(settings.raw_shell),
        )
    )
    checks.append(
        Check(
            OK if settings.evidence_mode == "read_only" else FAIL,
            "evidence read-only",
            settings.evidence_mode,
        )
    )
    checks.append(
        Check(
            OK if settings.allow_destructive_tools is False else FAIL,
            "destructive tools disabled",
            str(settings.allow_destructive_tools),
        )
    )
    return checks


def _format_protocol_sift(status: ProtocolSiftStatus) -> list[str]:
    skills = ", ".join(status.skills_present) or "none"
    tools = ", ".join(status.tools_present) or "none"
    return [
        "",
        "-- Protocol SIFT (~/.claude) --",
        f"  claude home          : {status.claude_home}",
        f"  Claude Code installed: {status.claude_code_installed}",
        f"  Protocol SIFT present: {status.protocol_sift_installed}",
        f"  settings.json        : {status.settings_present}",
        f"  case template        : {status.case_template_present}",
        f"  analysis scripts     : {status.analysis_scripts_present}",
        f"  skills present       : {skills}",
        f"  SIFT tools present   : {tools}",
    ]


def run_doctor(*, protocol_sift: bool = False, settings: SiftmeshSettings | None = None) -> int:
    """Run all checks, print a report, return an exit code (0 = ok, 1 = fail-closed)."""
    checks = collect_checks(settings)
    for c in checks:
        print(f"{_MARK[c.status]} {c.name}: {c.detail}")

    if protocol_sift:
        for line in _format_protocol_sift(detect_protocol_sift()):
            print(line)

    failures = [c for c in checks if c.status == FAIL]
    if failures:
        print(f"\ndoctor: FAIL — {len(failures)} required check(s) failed (fails closed).")
        return 1
    print("\ndoctor: ok.")
    return 0

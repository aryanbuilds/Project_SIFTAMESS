"""Memory analysis tool (Epic D deepening) — Volatility 3 triage (subprocess-only).

``analyze_memory`` runs a curated set of Volatility 3 Windows plugins over a decompressed
memory image and normalises the JSON output into typed rows. Volatility 3 is **VSL-licensed**,
so it is invoked **only as an external fixed-argv subprocess** (``shell=False``) and is
**never imported** into this Apache-2.0 project (a guard test enforces this). A missing ``vol``
binary or unresolved symbol tables **fails closed** (no fabricated result). The call is audited
via ``run_tool``: the raw Volatility JSON is preserved as the tool's ``raw_output_path``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import Field

from siftmesh_core import __version__
from siftmesh_core.evidence.memory_access import detect_format
from siftmesh_core.mcp_gateway.audit_exec import (
    _RAW_OUTPUT_KEY,
    RecoverableToolError,
    run_tool,
)
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.mcp_gateway.tools._common import resolved_source
from siftmesh_core.schemas.tool_result import ToolResult

# Friendly name -> Volatility 3 plugin. Qualified names ("windows.pslist") pass through.
_PLUGIN_ALIASES: dict[str, str] = {
    "pslist": "windows.pslist",
    "pstree": "windows.pstree",
    "psscan": "windows.psscan",
    "netscan": "windows.netscan",
    "netstat": "windows.netstat",
    "cmdline": "windows.cmdline",
    "malfind": "windows.malfind",
    "dlllist": "windows.dlllist",
    "info": "windows.info",
}

DEFAULT_PLUGINS: tuple[str, ...] = (
    "windows.pslist",
    "windows.pstree",
    "windows.netscan",
    "windows.cmdline",
    "windows.malfind",
)

_DEFAULT_TIMEOUT = 900  # seconds per plugin (netscan/malfind are slow on large images)


class MemoryAnalysisResult(ToolResult):
    """Normalised Volatility 3 triage over one memory image."""

    memory_format: str | None = None
    plugins_ran: list[str] = Field(default_factory=list)
    plugins_failed: list[str] = Field(default_factory=list)
    process_count: int = 0
    processes: list[dict[str, Any]] = Field(default_factory=list)
    process_tree: list[dict[str, Any]] = Field(default_factory=list)
    network: list[dict[str, Any]] = Field(default_factory=list)
    cmdlines: list[dict[str, Any]] = Field(default_factory=list)
    suspicious: list[dict[str, Any]] = Field(default_factory=list)


def _resolve_plugin(name: str) -> str:
    return _PLUGIN_ALIASES.get(name, name)


def _vol_binary(vol_path: str | None) -> str:
    candidate = vol_path or shutil.which("vol")
    if candidate and Path(candidate).exists():
        return candidate
    raise BackendUnavailableError(
        "Volatility 3 'vol' not found (set vol_path / install it); fails closed (never imported)"
    )


def _run_plugin(
    vol_exe: str, memory: Path, plugin: str, *, offline: bool, timeout: int
) -> tuple[list[dict[str, Any]] | None, str]:
    """Run one vol plugin with the JSON renderer → (rows, raw_stdout). rows None on failure."""
    argv = [vol_exe, "-r", "json", "-f", str(memory)]
    if offline:
        argv.append("--offline")
    argv.append(plugin)
    proc = subprocess.run(  # fixed argv, shell=False, validated path
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )
    if proc.returncode != 0:
        return None, proc.stdout + "\n" + proc.stderr
    try:
        parsed = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None, proc.stdout
    rows = parsed if isinstance(parsed, list) else parsed.get("rows", [parsed])
    return rows, proc.stdout


def _norm_proc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "pid": r.get("PID"),
            "ppid": r.get("PPID"),
            "name": r.get("ImageFileName") or r.get("Name"),
            "create_time": r.get("CreateTime"),
            "exit_time": r.get("ExitTime"),
        }
        for r in rows
    ]


def _norm_net(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "proto": r.get("Proto"),
            "local_addr": r.get("LocalAddr"),
            "local_port": r.get("LocalPort"),
            "foreign_addr": r.get("ForeignAddr"),
            "foreign_port": r.get("ForeignPort"),
            "state": r.get("State"),
            "pid": r.get("PID"),
            "owner": r.get("Owner"),
        }
        for r in rows
    ]


def _norm_cmd(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"pid": r.get("PID"), "process": r.get("Process"), "args": r.get("Args")} for r in rows]


def _norm_malfind(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "pid": r.get("PID"),
            "process": r.get("Process"),
            "protection": r.get("Protection"),
            "notes": r.get("Notes"),
        }
        for r in rows
    ]


def analyze_memory(
    run_root: Path | str,
    *,
    memory_artifact: str,
    evidence_root: Path | str,
    plugins: list[str] | None = None,
    vol_path: str | None = None,
    offline: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    backend_mode: str = "sift_lane",
) -> MemoryAnalysisResult:
    """Triage a memory image with Volatility 3 (pslist/pstree/netscan/cmdline/malfind by default).

    ``memory_artifact`` is resolved under ``evidence_root`` (typically the run's
    ``evidence/extracted`` dir where the decompressed image lives).
    """
    memory_path, memory_sha = resolved_source(evidence_root, memory_artifact)
    want = [_resolve_plugin(p) for p in (plugins or list(DEFAULT_PLUGINS))]

    def produce() -> dict[str, Any]:
        vol_exe = _vol_binary(vol_path)
        # Symbol gate: windows.info must succeed, else nothing can be analysed — fail closed.
        info_rows, _info_raw = _run_plugin(
            vol_exe, memory_path, "windows.info", offline=offline, timeout=timeout
        )
        if info_rows is None:
            raise RecoverableToolError(
                "Volatility could not resolve symbols / read the image (windows.info failed)",
                code="vol_symbol_resolution_failed",
            )

        ran: list[str] = ["windows.info"]
        failed: list[str] = []
        raw: dict[str, Any] = {"windows.info": info_rows}
        processes: list[dict[str, Any]] = []
        process_tree: list[dict[str, Any]] = []
        network: list[dict[str, Any]] = []
        cmdlines: list[dict[str, Any]] = []
        suspicious: list[dict[str, Any]] = []

        for plugin in want:
            if plugin == "windows.info":
                continue
            rows, plugin_raw = _run_plugin(
                vol_exe, memory_path, plugin, offline=offline, timeout=timeout
            )
            if rows is None:
                failed.append(plugin)
                raw[plugin] = {"error": plugin_raw[-2000:]}
                continue
            ran.append(plugin)
            raw[plugin] = rows
            if plugin in ("windows.pslist", "windows.psscan"):
                processes.extend(_norm_proc(rows))
            elif plugin == "windows.pstree":
                process_tree.extend(_norm_proc(rows))
            elif plugin in ("windows.netscan", "windows.netstat"):
                network.extend(_norm_net(rows))
            elif plugin == "windows.cmdline":
                cmdlines.extend(_norm_cmd(rows))
            elif plugin == "windows.malfind":
                suspicious.extend(_norm_malfind(rows))

        return {
            "memory_format": detect_format(memory_path),
            "plugins_ran": ran,
            "plugins_failed": failed,
            "process_count": len(processes),
            "processes": processes,
            "process_tree": process_tree,
            "network": network,
            "cmdlines": cmdlines,
            "suspicious": suspicious,
            _RAW_OUTPUT_KEY: json.dumps(raw, indent=2, default=str),
        }

    return run_tool(
        run_root,
        result_cls=MemoryAnalysisResult,
        tool_name="analyze_memory",
        source_artifact=memory_artifact,
        source_sha256=memory_sha,
        backend="sift_lane",
        tool_version=__version__,
        produce=produce,
        evidence_root=evidence_root,
    )

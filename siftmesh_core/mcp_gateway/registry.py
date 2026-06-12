"""Forensic-tool allowlist + registration guard (D1).

The gateway exposes EXACTLY the allowlisted typed forensic tools (CLAUDE.md §7) and
nothing else. A forbidden name (CLAUDE.md §6 — raw shell / destructive) can never
register, and any name outside the allowlist is rejected at registration time
(criterion 4: a constrained tool surface). This module is ``mcp``-free so the
allowlist is testable without building a server. Adding a tool is a GOVERNED change:
this set + the ``doctor`` count self-check + the per-tool tests move in lockstep.
"""

from __future__ import annotations

# The complete, fixed set of tools the gateway may expose (CLAUDE.md §7). Disk-image
# extraction + memory triage were a governed Epic-D expansion; parse_mft_filesystem (+
# the P0 deep-evidence tools) a later governed expansion — all real-tool backed,
# audited, fail-closed.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "compute_hash_manifest",
        "create_readonly_evidence_vault",
        "parse_evtx_security",
        "parse_evtx_powershell",
        "analyze_prefetch",
        "extract_registry_run_keys",
        "build_timeline",
        "validate_claim_evidence",
        "extract_artifacts_from_image",
        "analyze_memory",
        "parse_mft_filesystem",
        "parse_recentdocs_mru",
        "parse_usb_registry",
        "parse_browser_history",
    }
)

# Names that must NEVER be exposed as a tool (CLAUDE.md §6).
FORBIDDEN_TOOLS: frozenset[str] = frozenset(
    {
        "execute_shell_command",
        "arbitrary_python",
        "rm",
        "dd_write",
        "mount_rw",
        "curl_arbitrary",
        "scp_arbitrary",
    }
)


class ToolNotAllowedError(RuntimeError):
    """Raised when a tool name is forbidden or outside the allowlist."""


def assert_tool_allowed(name: str) -> None:
    """Guard a tool name at registration time; raise if it may not be exposed."""
    if name in FORBIDDEN_TOOLS:
        raise ToolNotAllowedError(f"tool {name!r} is forbidden and must never be exposed")
    if name not in ALLOWED_TOOLS:
        raise ToolNotAllowedError(f"tool {name!r} is not in the forensic allowlist")

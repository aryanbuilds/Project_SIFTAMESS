from __future__ import annotations

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
        "parse_lnk_jumplists",
        "parse_shellbags",
        "parse_amcache_shimcache",
        "parse_usnjrnl",
        "build_super_timeline",
    }
)

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
    pass


def assert_tool_allowed(name: str) -> None:
    if name in FORBIDDEN_TOOLS:
        raise ToolNotAllowedError(f"tool {name!r} is forbidden and must never be exposed")
    if name not in ALLOWED_TOOLS:
        raise ToolNotAllowedError(f"tool {name!r} is not in the forensic allowlist")

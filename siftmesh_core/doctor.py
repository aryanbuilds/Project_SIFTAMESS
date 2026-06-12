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
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.adapters.profiles import load_profiles
from siftmesh_core.config import SiftmeshSettings, load_settings
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.protocol_sift import ProtocolSiftStatus, detect_protocol_sift
from siftmesh_core.schemas.agent_capabilities import (
    SAFETY_TIER_DESC,
    AgentCapability,
    AgentCapabilityMap,
    safety_tier_label,
)
from siftmesh_core.schemas.agent_profile import AgentProfile

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
    ("LnkParse3", "LNK/JumpList (LnkParse3)"),
    ("olefile", "JumpList OLE (olefile)"),
)

# Optional incident-brief readers (`brief` extra). Missing => WARN; only fails closed when a
# brief of that format is actually passed via --brief (.txt/.md need nothing).
BRIEF_DEPS: tuple[tuple[str, str], ...] = (
    ("pptx", "Incident brief .pptx (python-pptx)"),
    ("docx", "Incident brief .docx (python-docx)"),
    ("pypdf", "Incident brief .pdf (pypdf)"),
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
    # NOTE: `uv sync --extra X` is declarative — it makes the env exactly base+X and REMOVES
    # other extras. Recommend --all-extras so installing one suite never uninstalls another.
    for mod, human in FORENSIC_DEPS:
        ok = _module_available(mod)
        checks.append(
            Check(
                OK if ok else WARN,
                f"forensic: {human}",
                "installed" if ok else "absent: uv sync --all-extras",
            )
        )
    for mod, human in BRIEF_DEPS:
        ok = _module_available(mod)
        checks.append(
            Check(
                OK if ok else WARN,
                f"brief: {human}",
                "installed" if ok else "absent: uv sync --all-extras",
            )
        )
    tui_ok = _module_available("textual")
    checks.append(
        Check(
            OK if tui_ok else WARN,
            "tui: Textual cockpit",
            "installed" if tui_ok else "absent: uv sync --extra tui (for `siftmesh tui`)",
        )
    )
    litellm_ok = _module_available("litellm")
    checks.append(
        Check(
            OK if litellm_ok else WARN,
            "judge: LiteLLM (multi-provider)",
            "installed"
            if litellm_ok
            else "absent: uv sync --extra llm (optional — for a litellm: Tier-2 judge)",
        )
    )
    checks.append(Check(OK if _cwd_writable() else FAIL, "run-dir writable", "case_runs/ (cwd)"))
    # Gateway tool surface (criterion 4): exactly the 8 §7 tools, none forbidden.
    from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS

    allowlist_ok = len(ALLOWED_TOOLS) == 15 and ALLOWED_TOOLS.isdisjoint(FORBIDDEN_TOOLS)
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
    # Live agent (loud opt-in): report whether the Claude headless agent could run here. Absent =>
    # WARN; runs fall to the deterministic floor unless `--agent claude` is used with CLI + auth.
    try:
        from siftmesh_core.adapters.claude_adapter import ClaudeHeadlessAdapter

        claude_ok = ClaudeHeadlessAdapter(settings=settings).available()
    except Exception:
        claude_ok = False
    checks.append(
        Check(
            OK if claude_ok else WARN,
            "live agent: Claude Code",
            "available — for a live objective-driven run add `--agent claude`"
            if claude_ok
            else "absent (CLI/auth) — runs use the deterministic floor",
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


def run_setup(settings: SiftmeshSettings) -> int:
    """One-command install/configure: `uv sync --all-extras` + create the vol symbol cache.

    Fails closed if `uv` is absent (never a pip fallback). Returns 0 on success, 1 on failure.
    """
    import importlib
    import subprocess

    uv = shutil.which("uv")
    if uv is None:
        print(
            f"{_MARK[FAIL]} setup: uv not found on PATH — install uv (https://docs.astral.sh/uv/)"
        )
        return 1
    print("setup: uv sync --all-extras (installs forensic + brief + a2a backends)…")
    proc = subprocess.run([uv, "sync", "--all-extras"], check=False)  # fixed argv, shell=False
    if proc.returncode != 0:
        print(f"{_MARK[FAIL]} setup: `uv sync --all-extras` failed (exit {proc.returncode})")
        return 1
    importlib.invalidate_caches()  # so the dependency checks below see freshly installed packages
    cache = Path(settings.vol_symbol_dirs)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        print(f"{_MARK[OK]} setup: Volatility symbol cache ready: {cache}")
    except OSError as exc:
        print(f"{_MARK[WARN]} setup: could not create symbol cache {cache}: {exc}")
    print()
    return 0


# ---- Agent onboarding (Epic Q) -------------------------------------------------------------------
# The connector kinds we onboard (a coding agent the operator could dispatch to). ``generic_shell``
# is operator-defined fixed-argv (not an onboarding target); ``deterministic`` is the always-present
# real-tool floor.
_LIVE_KINDS = ("claude", "opencode", "headless")
# Default pick order when no settings.agent_preference is configured (best first).
_DEFAULT_AGENT_ORDER = (
    "claude_headless",
    "opencode_headless",
    "gemini_headless",
    "codex_headless",
)


def _profile_cli(prof: AgentProfile, settings: SiftmeshSettings) -> str | None:
    """The launch binary for a dispatchable profile (None for the deterministic floor)."""
    if prof.kind == "claude":
        return settings.claude_cli_path
    if prof.kind == "opencode":
        return settings.opencode_cli_path
    if prof.kind == "headless":
        return prof.launch_argv[0] if prof.launch_argv else None
    return None


def _agent_version(cli: str) -> str:
    """Best-effort ``<cli> --version`` first line (fast, fixed-argv, abs-path, never raises)."""
    resolved = shutil.which(cli)
    if resolved is None:
        return "absent"
    try:
        proc = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    return lines[0].strip() if lines else "unknown"


def _agent_auth_ok(prof: AgentProfile, settings: SiftmeshSettings) -> bool:
    """Whether the agent is authenticated (env var / cached credentials, or none required)."""
    if prof.kind == "claude":
        try:
            from siftmesh_core.adapters.claude_adapter import claude_available

            return bool(claude_available(settings))
        except Exception:
            return False
    if (
        prof.kind == "opencode"
    ):  # OpenCode uses its own login (auth.json); presence is treated usable
        return shutil.which(settings.opencode_cli_path) is not None
    if prof.kind == "headless":
        from siftmesh_core.adapters.headless import profile_authed

        return profile_authed(prof)
    return True


def _agent_sandboxed(prof: AgentProfile) -> bool:
    """Whether the agent's native tools are denied (claude yes; opencode no; headless: recipe)."""
    if prof.kind in ("deterministic", "claude"):
        return True
    if prof.kind == "opencode":
        return False  # secondary path; no native-tool deny wired (its adapter notes this)
    if prof.kind == "headless":
        from siftmesh_core.adapters.headless import is_sandboxed

        return is_sandboxed(prof)
    return False


def _agent_tool_reach(prof: AgentProfile) -> str:
    """Can this agent reach the typed forensic tools? (honest; only Claude is verified today)."""
    if prof.kind in ("deterministic", "claude"):
        return "yes"
    if prof.kind == "opencode":
        return "no"  # OpenCode MCP wiring not done yet (round-2)
    if prof.kind == "headless":
        return "yes" if prof.mcp_strategy == "claude_flag" else "verify-live"
    return "verify-live"


def _agent_safety_tier(kind: str, sandboxed: bool, tool_reachable: str) -> str:
    """Honest containment label derived from the capability facts (labels only — never gates).

    T0 = the deterministic floor; T1 = sandboxed AND typed tools via strict-MCP (claude today);
    T2 = any other live agent (unsandboxed, or tool-reach unproven/native — explicit opt-in).
    """
    if kind == "deterministic":
        return "T0"
    if sandboxed and tool_reachable == "yes":
        return "T1"
    return "T2"


def profile_safety_tiers() -> dict[str, str]:
    """``{profile_id: tier}`` from the profiles alone — pure, NO ``--version`` subprocess.

    Cheap enough for the cockpit to call once per mount (the full ``probe_agents`` shells each
    present CLI; this only needs the static profile recipe to classify containment).
    """
    out: dict[str, str] = {}
    for pid, prof in load_profiles().items():
        out[pid] = _agent_safety_tier(prof.kind, _agent_sandboxed(prof), _agent_tool_reach(prof))
    return out


def _is_ready(c: AgentCapability) -> bool:
    """A live agent that can do forensic work: present + authed + sandboxed + tool-reaching."""
    return c.present and c.auth_ok and c.sandboxed and c.tool_reachable == "yes"


def _live_candidate(caps: list[AgentCapability], settings: SiftmeshSettings) -> str | None:
    """Best ready LIVE agent to opt into via ``--agent`` (ignores executor_selection; not floor)."""
    ready = {c.profile_id for c in caps if _is_ready(c) and c.kind != "deterministic"}
    order = settings.agent_preference or list(_DEFAULT_AGENT_ORDER)
    return next((pid for pid in order if pid in ready), None)


def _choose_default(caps: list[AgentCapability], settings: SiftmeshSettings) -> str:
    """What a plain ``siftmesh run`` dispatches IN THIS CONFIG — mirrors ``resolve_profile``.

    When ``executor_selection == "deterministic"`` (the shipped default) that is the floor, even if
    a live agent is installed — so the map never claims a live agent will run when it won't. The
    ready live agent is surfaced separately as ``live_candidate`` (the ``--agent`` opt-in).
    """
    if settings.executor_selection == "deterministic":
        return "deterministic_executor"
    return _live_candidate(caps, settings) or "deterministic_executor"


def probe_agents(settings: SiftmeshSettings | None = None) -> AgentCapabilityMap:
    """Env-only onboarding probe: which agent CLIs are installed/authed/sandboxed + the default.

    Pure function of the host + the profile registry (no agent is launched beyond ``--version``),
    so the map is fully snapshot-stable. Fails closed via ``StrictModel`` validation.
    """
    settings = settings or load_settings()
    caps: list[AgentCapability] = []
    for pid, prof in load_profiles().items():
        if prof.kind == "deterministic":
            caps.append(
                AgentCapability(
                    profile_id=pid,
                    kind="deterministic",
                    present=True,
                    version="builtin",
                    auth_ok=True,
                    sandboxed=True,
                    tool_reachable="yes",
                    safety_tier="T0",
                    selected=False,
                )
            )
            continue
        if prof.kind not in _LIVE_KINDS:
            continue  # generic_shell / future kinds are not onboarding targets
        cli = _profile_cli(prof, settings)
        present = bool(cli and shutil.which(cli))
        sandboxed = _agent_sandboxed(prof)
        tool_reachable = _agent_tool_reach(prof)
        caps.append(
            AgentCapability(
                profile_id=pid,
                kind=prof.kind,
                present=present,
                version=_agent_version(cli) if present and cli else "absent",
                auth_ok=_agent_auth_ok(prof, settings),
                sandboxed=sandboxed,
                tool_reachable=tool_reachable,
                safety_tier=_agent_safety_tier(prof.kind, sandboxed, tool_reachable),
                selected=False,
            )
        )
    chosen = _choose_default(caps, settings)
    live = _live_candidate(caps, settings)
    caps.sort(key=lambda c: c.profile_id)
    for c in caps:
        c.selected = c.profile_id == chosen
    return AgentCapabilityMap(agents=caps, chosen=chosen, live_candidate=live)


def write_agent_capability_map(
    run_root: Path | str,
    *,
    settings: SiftmeshSettings | None = None,
    evidence_root: Path | str | None = None,
) -> Path:
    """Write the onboarding map to ``context/agent_capabilities.json`` (path-policed)."""
    cap = probe_agents(settings)
    target = safe_write_path(
        run_root, Path("context") / "agent_capabilities.json", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cap.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def _format_agents(cap: AgentCapabilityMap) -> list[str]:
    lines = ["", "-- Coding agents (onboarding) --"]
    profiles = load_profiles()
    for c in cap.agents:
        mark = OK if (c.present and c.auth_ok) else WARN
        sel = "  <- default" if c.selected else ""
        auth = "auth ok" if c.auth_ok else "no auth"
        box = "sandboxed" if c.sandboxed else "UNSANDBOXED"
        present = c.version if c.present else "absent"
        lines.append(
            f"  {_MARK[mark]} {c.profile_id:<22} [{c.safety_tier}] {present:<22} "
            f"{auth:<8} {box:<11} tools:{c.tool_reachable}{sel}"
        )
        # Guided remediation: for a not-ready agent, the exact fix (data-driven from its profile).
        if not _is_ready(c) and c.kind != "deterministic":
            for hint in agent_remediation(c, profiles.get(c.profile_id)):
                lines.append(f"      → {hint}")
    lines.append(f"  default agent (this config): {cap.chosen}")
    if cap.chosen == "deterministic_executor":
        lines.append("  (a plain `siftmesh run` uses the deterministic real-tool floor — tier T0)")
    if cap.live_candidate and cap.live_candidate != cap.chosen:
        lines.append(f"  live agent ready — opt in with `--agent`: {cap.live_candidate}")
    else:
        lines.append(
            "  no live agent is ready — runs use the deterministic floor (T0); "
            "onboard one above for T1/T2."
        )
    lines += _safety_tier_legend()
    lines.append("  install/auth an absent agent, then re-run `siftmesh doctor --agents`.")
    return lines


def _safety_tier_legend() -> list[str]:
    """The shared T0-T3 legend (CLI / doctor / TUI render the same honest definitions)."""
    return ["  safety tiers:", *[f"    {safety_tier_label(t)}" for t in SAFETY_TIER_DESC]]


def _auth_hint(c: AgentCapability, prof: AgentProfile | None) -> str:
    """The exact authentication step for a present-but-unauthed agent (kind-aware, honest)."""
    if c.kind == "claude":  # subscription OR API; auth_env is empty (handled by claude_available)
        return "authenticate: `claude setup-token` (subscription) or export ANTHROPIC_API_KEY=…"
    if c.kind == "opencode":
        return "authenticate: `opencode auth login` (its own auth.json)"
    if prof and prof.auth_env:
        return f"authenticate: set one of [{', '.join(prof.auth_env)}] (or log in via the CLI)"
    return "authenticate: set the vendor's API key (or log in via the CLI)"


def agent_remediation(c: AgentCapability, prof: AgentProfile | None) -> list[str]:
    """Honest, data-driven next steps for a not-ready agent (no interactive auth driven by us)."""
    hints: list[str] = []
    if not c.present:
        hints.append(f"install the `{c.profile_id.split('_')[0]}` CLI, then re-probe")
        return hints  # nothing else is actionable until the CLI exists
    if not c.auth_ok:
        hints.append(_auth_hint(c, prof))
    if not c.sandboxed:
        hints.append(
            "tier T2 — native tools are NOT denied; it reaches tools unsandboxed "
            "(explicit `--agent` opt-in; never treated as constrained)"
        )
    elif c.tool_reachable != "yes":
        hints.append(
            f"tier T2 — typed-tool reach is `{c.tool_reachable}` (sandboxed, but MCP wiring "
            "unproven; confirm with a live run before relying on it)"
        )
    return hints


def run_doctor(
    *,
    protocol_sift: bool = False,
    agents: bool = False,
    setup: bool = False,
    settings: SiftmeshSettings | None = None,
) -> int:
    """Run all checks, print a report, return an exit code (0 = ok, 1 = fail-closed).

    With ``setup=True``, first install all extras + create the symbol cache (one-command setup),
    then run the checks (so the report proves the setup worked). With ``agents=True``, also print
    the coding-agent onboarding map (absent agents are informational, never a fail-closed failure).
    """
    settings = settings or load_settings()
    if setup and run_setup(settings) != 0:
        return 1
    checks = collect_checks(settings)
    for c in checks:
        print(f"{_MARK[c.status]} {c.name}: {c.detail}")

    if protocol_sift:
        for line in _format_protocol_sift(detect_protocol_sift()):
            print(line)

    if agents:
        for line in _format_agents(probe_agents(settings)):
            print(line)

    failures = [c for c in checks if c.status == FAIL]
    if failures:
        print(f"\ndoctor: FAIL — {len(failures)} required check(s) failed (fails closed).")
        return 1
    print("\ndoctor: ok.")
    return 0

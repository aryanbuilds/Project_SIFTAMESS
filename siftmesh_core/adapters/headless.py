"""Config-driven, agent-NEUTRAL headless connector (Epic Q, round 1).

One generic adapter launches a CLI coding agent (Gemini, Codex, …) from its profile ``launch_argv``
recipe, hands it the SAME spotlighted task prompt every executor gets, and parses its
``{claims:[…]}`` output through the same ``parse_agent_result`` — adding an agent is a YAML row.

Governance / evidence safety (Epic Q audit corrections): a headless profile is dispatchable ONLY if
its recipe carries explicit native-tool deny/sandbox flags (``native_tool_argv``) — a recipe without
them fails closed (``available()`` False → deterministic floor), since an un-denied agent could run
native shell/file/web tools. Every agent subprocess also runs with a pinned, run-scoped cwd (never
the operator's CWD — which these CLIs auto-load TRUSTED ``GEMINI.md``/``AGENTS.md`` from) and a
minimized env (only the agent's own declared credentials, not every provider's keys). The
deterministic critic still governs truth.

Honest tool-reachability: only the ``claude_flag`` MCP strategy reaches our typed tools today (it
also injects the full Claude sandbox block). Gemini/Codex are ``mcp_strategy: none`` (verify-live;
per-run MCP wiring is round-2 / ACP) — they run sandboxed but reach no typed tools yet, so their
claims go ``unsupported`` and the run falls to the floor; ``doctor --agents`` reports per agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from siftmesh_core.adapters.agent_result import parse_agent_result
from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.claude_adapter import claude_sandbox_flags
from siftmesh_core.adapters.profiles import effective_model
from siftmesh_core.adapters.prompt_builder import build_task_prompt
from siftmesh_core.adapters.sandbox import minimal_child_env, scratch_cwd
from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.schemas.agent_profile import AgentProfile
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult


def is_sandboxed(prof: AgentProfile) -> bool:
    """Whether a headless recipe denies the agent's native tools (REQUIRED to dispatch).

    True iff the profile carries explicit per-CLI deny/sandbox flags, OR it reaches the typed tools
    via the Claude sandbox (``claude_flag`` — which appends the full ``--tools ""``/deny block). A
    recipe with neither would run the agent with native shell/file/web tools enabled, so it fails
    closed (``available()`` False → the registry falls to the deterministic floor).
    """
    return bool(prof.native_tool_argv) or prof.mcp_strategy == "claude_flag"


def profile_authed(prof: AgentProfile) -> bool:
    """Whether the agent is authenticated: an ``auth_env`` var is set OR a cached-credential file
    exists. Empty auth_env AND empty auth_files ⇒ unknown ⇒ not authenticated (fail closed)."""
    if any(os.environ.get(v) for v in prof.auth_env):
        return True
    return any(Path(p).expanduser().is_file() for p in prof.auth_files)


def write_run_scoped_mcp_config(ctx: AdapterContext) -> Path:
    """Write a per-run MCP config pointing the agent at SIFTMesh's run-scoped stdio MCP server.

    Same shape the Claude adapter uses: launched as ``<interpreter> -m siftmesh_core.cli mcp-serve``
    with absolute SIFTMESH_RUN_ROOT/SIFTMESH_EVIDENCE_ROOT in the env (the agent cannot choose a
    root; the server fails closed if they are unset).
    """
    config = {
        "mcpServers": {
            "siftmesh": {
                "command": sys.executable,
                "args": ["-m", "siftmesh_core.cli", "mcp-serve"],
                "env": {
                    "SIFTMESH_RUN_ROOT": str(Path(ctx.run.root).resolve()),
                    "SIFTMESH_EVIDENCE_ROOT": str(Path(ctx.evidence_root).resolve()),
                },
            }
        }
    }
    target = safe_write_path(ctx.run.root, "context/mcp_config.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return target


_ENVELOPE_TEXT_KEYS = ("result", "response", "text", "output", "content")


def _find_claims_dict(obj: object, depth: int = 0) -> dict[str, object] | None:
    """Recursively locate a dict carrying a list-valued ``claims`` key (handles nested/escaped
    structured results, e.g. ``{"result": {"claims": [...]}}`` or a stringified inner payload)."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("claims"), list):
            return obj
        for v in obj.values():
            hit = _find_claims_dict(v, depth + 1)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_claims_dict(v, depth + 1)
            if hit is not None:
                return hit
    elif isinstance(obj, str):
        try:
            return _find_claims_dict(json.loads(obj), depth + 1)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _envelope_text(obj: dict[str, object]) -> str | None:
    """The agent's message text from a single JSON envelope (known key, or a nested claims dict)."""
    for key in _ENVELOPE_TEXT_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val
    claims = _find_claims_dict(obj)
    return json.dumps(claims) if claims is not None else None


def _str(val: object) -> str | None:
    """The value if it is a ``str``, else None (mypy-narrowing helper for nested .get() reads)."""
    return val if isinstance(val, str) else None


def _event_text(ev: dict[str, object]) -> str | None:
    """Agent-message text from one JSONL event across CLI shapes (codex / gemini-stream / opencode).

    Codex: ``item.completed`` → ``item.agent_message.text``; gemini stream: ``msg.message``;
    opencode: ``type:text`` → ``part.text``. Reasoning/tool events are skipped so chain-of-thought
    never leaks into the parsed answer."""
    item = ev.get("item")
    if isinstance(item, dict):
        if item.get("type") in (None, "agent_message"):
            text = _str(item.get("text"))
            if text is not None:
                return text
            details = item.get("details")
            if isinstance(details, dict):
                return _str(details.get("text"))
        return None
    msg = ev.get("msg")
    if isinstance(msg, dict):
        for k in ("message", "last_agent_message", "text"):
            text = _str(msg.get(k))
            if text is not None:
                return text
        return None
    if ev.get("type") in (None, "text", "message", "assistant"):
        text = _str(ev.get("text"))
        if text is not None:
            return text
        part = ev.get("part")
        if isinstance(part, dict):
            return _str(part.get("text"))
    return None


def extract_agent_text(stdout: str, output_format: str) -> str:
    """Tolerantly pull the agent's message text from its stdout (single envelope / JSONL / raw).

    ``parse_agent_result`` then finds the ``{claims:[…]}`` JSON inside whatever this returns. It
    handles both a single JSON envelope AND a JSON-Lines EVENT STREAM (codex ``exec --json``, gemini
    ``stream-json``, opencode) where the final message is escaped inside an event — the case a naive
    whole-stdout ``json.loads`` fails on and the claims would otherwise be lost forever."""
    s = stdout.strip()
    if not s:
        return ""
    if output_format in ("claude_json", "agent_json", "opencode_json"):
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if isinstance(obj, dict):  # single JSON envelope
            txt = _envelope_text(obj)
            if txt:
                return txt
        # JSON-Lines event stream → concatenate agent-message text (skips reasoning/tool events).
        parts: list[str] = []
        for line in s.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(ev, dict):
                t = _event_text(ev)
                if t:
                    parts.append(t)
        if parts:
            return "".join(parts)
    return s  # raw stdout (parse_agent_result will still find the claims JSON)


class HeadlessAdapter(ExecutorAdapter):
    """Generic config-driven one-shot agent connector. Subclasses set ``profile_id`` only."""

    def _prof(self) -> AgentProfile | None:
        return self.profile()

    def available(self) -> bool:
        prof = self._prof()
        if prof is None or not prof.launch_argv:
            return False
        if shutil.which(prof.launch_argv[0]) is None:
            return False
        if not is_sandboxed(prof):
            return False  # fail closed: never dispatch an agent whose native tools are un-denied
        return profile_authed(prof)

    def _build_argv(
        self,
        prof: AgentProfile,
        prompt: str,
        mcp_config: Path | None,
        *,
        allowed_tools: list[str] | tuple[str, ...] = (),
    ) -> list[str]:
        argv = [*prof.launch_argv, prompt]
        model = effective_model(self.settings, self.profile_id, prof.model)
        if model and prof.model_flag:
            argv += [prof.model_flag, model]
        argv += list(prof.extra_argv)
        argv += list(prof.native_tool_argv)
        if mcp_config is not None:  # claude_flag: typed tools AND the full claude sandbox block
            argv += ["--mcp-config", str(mcp_config), "--strict-mcp-config"]
            argv += claude_sandbox_flags(allowed_tools)
        return argv

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        prof = self._prof()
        if prof is None or not prof.launch_argv:
            return self._error(contract, ctx, started, "headless_profile_missing_launch_argv")
        prompt = build_task_prompt(
            contract,
            run_id=ctx.run.run_id,
            critic_feedback=ctx.critic_feedback,
            incident_objective=ctx.incident_objective,
        )
        mcp_config = (
            write_run_scoped_mcp_config(ctx) if prof.mcp_strategy == "claude_flag" else None
        )
        argv = self._build_argv(prof, prompt, mcp_config, allowed_tools=contract.allowed_tools)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.settings.agent_timeout_seconds,
                shell=False,
                check=False,
                cwd=scratch_cwd(ctx.run, contract.task_id),  # never the operator CWD
                env=minimal_child_env(keep=[*prof.auth_env, *prof.env_passthrough]),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._error(contract, ctx, started, "agent_failed_or_timeout")
        text = extract_agent_text(proc.stdout, prof.output_format)
        self._scan(
            ctx, contract, text
        )  # injection scan on the agent's output (logged, not executed)
        if proc.returncode != 0 and not text.strip():
            return self._error(contract, ctx, started, "agent_error")
        # parse_agent_result governs honesty: under-anchored → unsupported; unparseable → retry.
        return parse_agent_result(
            text,
            contract=contract,
            ctx=ctx,
            adapter_id=self.profile_id,
            started=started,
            ended=datetime.now(UTC),
        )

    def _error(
        self, contract: TaskContract, ctx: AdapterContext, started: datetime, code: str
    ) -> TaskResult:
        return TaskResult(
            task_id=contract.task_id,
            profile=ctx.requested_profile or self.profile_id,
            adapter=self.profile_id,
            attempt=ctx.attempt,
            status="error",
            started_utc=started,
            ended_utc=datetime.now(UTC),
            errors=[code],
        )

    def _scan(self, ctx: AdapterContext, contract: TaskContract, text: str) -> None:
        for m in scan_injection(text):
            append_injection_alert(
                ctx.run.root,
                InjectionAlert(
                    alert_id=next_alert_id(ctx.run.root),
                    source="agent_result",
                    signature=m.signature,
                    snippet=m.snippet,
                    detected_utc=datetime.now(UTC),
                    task_id=contract.task_id,
                ),
                evidence_root=ctx.evidence_root,
            )


@register
class GeminiHeadlessAdapter(HeadlessAdapter):
    """Live Gemini CLI (config-driven; human-gated)."""

    profile_id = "gemini_headless"
    backend_label = "gemini"


@register
class CodexHeadlessAdapter(HeadlessAdapter):
    """Live Codex CLI (config-driven; human-gated)."""

    profile_id = "codex_headless"
    backend_label = "codex"

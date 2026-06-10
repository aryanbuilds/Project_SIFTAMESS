"""Config-driven, agent-NEUTRAL headless connector (Epic Q, round 1).

One generic adapter launches ANY CLI coding agent (Gemini, Codex, OpenClaw, …) from its profile
``launch_argv`` recipe, hands it the SAME spotlighted task prompt every executor gets, and parses
its ``{claims:[…]}`` output through the same ``parse_agent_result`` — so adding an agent is a YAML
row, not a new adapter. Governance is unchanged: native agent tools are denied (per-CLI flags), the
agent reaches forensic tools only through the run-scoped typed MCP server, and the deterministic
critic governs truth. A missing CLI/auth ⇒ ``available()`` False ⇒ the registry falls to the floor.

Honest tool-reachability: only the ``claude_flag`` MCP strategy is verified to reach our typed tools
today (Claude's ``--mcp-config``). For other agents the per-run MCP wiring is ``verify-live`` /
round-2 (ACP) — until then they run but reach no typed tools, so their claims go ``unsupported`` and
the run falls to the floor (fail-closed, never faked). ``doctor --agents`` reports this per agent.
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
from siftmesh_core.adapters.prompt_builder import build_task_prompt
from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.schemas.agent_profile import AgentProfile
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult


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


def extract_agent_text(stdout: str, output_format: str) -> str:
    """Tolerantly pull the agent's message text from its stdout (envelope / nd-JSON / raw).

    ``parse_agent_result`` then finds the ``{claims:[…]}`` JSON inside whatever this returns, so an
    exact per-agent shape is not required (robust to the JSON-shape drift across CLIs)."""
    s = stdout.strip()
    if not s:
        return ""
    if output_format in ("claude_json", "agent_json"):
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if isinstance(obj, dict):
            for key in ("result", "response", "text", "output", "content"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            return s  # a dict without a known text field — hand the whole thing on
    if output_format == "opencode_json":  # nd-JSON event stream → concatenate text chunks
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
                text = ev.get("text")
                if not isinstance(text, str):
                    part = ev.get("part")
                    text = part.get("text") if isinstance(part, dict) else None
                if isinstance(text, str):
                    parts.append(text)
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
        # auth: if the profile names auth env vars, at least one must be set (else assume OK).
        return not prof.auth_env or any(os.environ.get(v) for v in prof.auth_env)

    def _build_argv(self, prof: AgentProfile, prompt: str, mcp_config: Path | None) -> list[str]:
        argv = [*prof.launch_argv, prompt]
        if prof.model and prof.model_flag:
            argv += [prof.model_flag, prof.model]
        argv += list(prof.extra_argv)
        argv += list(prof.native_tool_argv)
        if mcp_config is not None:
            argv += ["--mcp-config", str(mcp_config), "--strict-mcp-config"]
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
        argv = self._build_argv(prof, prompt, mcp_config)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=prof.max_runtime_seconds,
                shell=False,
                check=False,
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


@register
class OpenClawHeadlessAdapter(HeadlessAdapter):
    """Live OpenClaw CLI (config-driven; human-gated)."""

    profile_id = "openclaw_headless"
    backend_label = "openclaw"

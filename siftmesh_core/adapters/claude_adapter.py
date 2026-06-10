"""Claude Code headless adapter (Epic F, F8) — the live autonomous executor (CORE).

Thin wrapper around ``claude -p`` in non-interactive JSON mode. The agent is SANDBOXED to
SIFTMesh's typed tools: the FastMCP server is launched via ``python -m siftmesh_core.cli mcp-serve``
(NOT bare ``siftmesh`` — not on the subprocess PATH), ``--strict-mcp-config`` ignores ambient MCP
servers, ``--allowedTools`` pre-approves only the contract's ``mcp__siftmesh__*`` tools,
``--disallowedTools`` denies the built-in shell/file/web/spawn tools, and ``--permission-mode
dontAsk`` auto-denies anything else (no prompt/hang). So the agent cannot run raw shell or write
files (CLAUDE §3/§6 privilege separation). When the CLI or all auth (subscription token / OAuth
bearer / API key / logged-in CLI) is absent the adapter is unavailable and the registry falls closed
to the deterministic floor.

HARD GATES (CLAUDE §2A/§2B):
* CLI flags re-confirmed against claude v2.1.170 ``--help`` (Epic L): ``--permission-mode`` accepts
  ``dontAsk`` (of acceptEdits/auto/bypassPermissions/default/dontAsk/plan); ``--strict-mcp-config``
  ignores ambient MCP servers; ``--allowedTools`` / ``--disallowedTools`` / ``--mcp-config`` /
  ``--output-format`` present. Isolated in ``_build_claude_argv``; re-confirm on bumps.
* Live validation against real evidence is HUMAN-GATED. Unit tests mock the subprocess boundary
  only; do NOT autonomously run a live agent against evidence.
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
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult

_MCP_TOOL_PREFIX = "mcp__siftmesh__"
# Env vars that authenticate `claude -p`: a subscription token (claude setup-token) OR an OAuth
# bearer OR the commercial API key. Any one present => the adapter is usable (dual auth).
_AUTH_ENV = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")

# Built-in Claude Code tools the SANDBOXED forensic agent must NOT have. `--allowedTools` is only
# ADDITIVE (it does not exclude built-ins — confirmed via claude-code docs + issue #62608), so we
# explicitly DENY raw shell / file-write / read / web / spawn tools. Combined with
# `--permission-mode dontAsk` (auto-deny anything not explicitly allowed, no prompt, no hang) this
# constrains the agent to ONLY the typed mcp__siftmesh__* tools (CLAUDE.md §3/§6 privilege
# separation). Over-listing is harmless — denying an unknown tool name is a no-op.
_DISALLOWED_TOOLS = (
    "Bash",
    "BashOutput",
    "KillShell",
    "Edit",
    "MultiEdit",
    "Write",
    "NotebookEdit",
    "Read",
    "Glob",
    "Grep",
    "LS",
    "WebFetch",
    "WebSearch",
    "Task",
    "Agent",
    "TodoWrite",
    "Skill",
    "SlashCommand",
)


def _claude_logged_in() -> bool:
    """True if the Claude Code CLI is already logged in (its own credential store exists).

    After ``claude setup-token`` / ``claude login`` the credentials live in
    ``~/.claude/.credentials.json`` and ``claude -p`` authenticates from there with NO env var — so
    a logged-in CLI is usable even when no ANTHROPIC_*/CLAUDE_CODE_* var is set. Existence is a
    best-effort signal; an expired token still fails closed at subprocess time (never faked).
    """
    return (Path.home() / ".claude" / ".credentials.json").is_file()


def _build_claude_argv(
    cli_path: str,
    prompt: str,
    mcp_config: Path,
    allowed_tools: list[str],
    *,
    model: str | None = None,
    permission_mode: str = "dontAsk",
) -> list[str]:
    """Build the SANDBOXED headless ``claude -p`` argv (flags isolated here; confirmed v2.1.x).

    The agent is constrained to ONLY the contract's ``mcp__siftmesh__*`` tools:
    ``--allowedTools`` pre-approves them, ``--disallowedTools`` denies the built-in shell/file/web/
    spawn tools (``--allowedTools`` alone is additive, not exclusive), ``--permission-mode dontAsk``
    auto-denies anything else with no prompt/hang, and ``--strict-mcp-config`` ignores ambient MCP
    servers. ``--model`` (when set) pins the model. Re-confirm ``claude --help`` on version bumps.
    """
    tools = ",".join(f"{_MCP_TOOL_PREFIX}{t}" for t in allowed_tools)
    argv = [
        cli_path,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--mcp-config",
        str(mcp_config),
        "--strict-mcp-config",
        "--allowedTools",
        tools,
        "--disallowedTools",
        *_DISALLOWED_TOOLS,
        "--permission-mode",
        permission_mode,
    ]
    if model:
        argv += ["--model", model]
    return argv


@register
class ClaudeHeadlessAdapter(ExecutorAdapter):
    """Run the live Claude Code agent headlessly, constrained to the typed tools."""

    profile_id = "claude_headless"
    backend_label = "claude_headless"

    def available(self) -> bool:
        # CLI present AND authenticated: an auth env var (subscription token / OAuth bearer / API
        # key) OR a logged-in Claude Code CLI (its own credential store; `claude -p` uses it with no
        # env var). Fails closed when the CLI or all auth is absent -> registry walks to the floor.
        if shutil.which(self.settings.claude_cli_path) is None:
            return False
        has_env_auth = any(os.environ.get(var) for var in _AUTH_ENV)
        return has_env_auth or _claude_logged_in()

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        prompt = build_task_prompt(
            contract,
            run_id=ctx.run.run_id,
            critic_feedback=ctx.critic_feedback,
            incident_objective=ctx.incident_objective,
        )
        mcp_config = self._write_mcp_config(ctx)
        prof = self.profile()
        argv = _build_claude_argv(
            self.settings.claude_cli_path,
            prompt,
            mcp_config,
            contract.allowed_tools,
            model=prof.model if prof else None,
            permission_mode=self.settings.claude_permission_mode,
        )
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.settings.agent_timeout_seconds,
                shell=False,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._error(contract, ctx, started, "agent_failed_or_timeout")
        self._write_raw(ctx, contract, proc.stdout)  # persist raw envelope for debugging
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return self._error(contract, ctx, started, "agent_bad_json")
        result_text = str(envelope.get("result", ""))
        self._scan(ctx, contract, result_text)  # injection scan on the agent's final message
        if envelope.get("is_error", proc.returncode != 0):
            return self._error(contract, ctx, started, str(envelope.get("subtype", "agent_error")))
        # K3: capture the agent's claims from its final message. Under-anchored claims land as
        # 'unsupported' (never fabricated) so the deterministic critic drives a retry-with-feedback.
        return parse_agent_result(
            result_text,
            contract=contract,
            ctx=ctx,
            adapter_id=self.profile_id,
            started=started,
            ended=datetime.now(UTC),
        )

    def _write_mcp_config(self, ctx: AdapterContext) -> Path:
        """Write a per-run MCP config pointing at SIFTMesh's stdio FastMCP server.

        The server is launched as ``<this interpreter> -m siftmesh_core.cli mcp-serve`` — NOT bare
        ``siftmesh`` (a uv/pip console script that is not on the agent subprocess's PATH), so the
        agent can actually reach the typed tools regardless of how SIFTMesh was invoked. Roots are
        written ABSOLUTE so the run-scoped server resolves them from any cwd.
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

    def _write_raw(self, ctx: AdapterContext, contract: TaskContract, stdout: str) -> None:
        """Persist the agent's raw stdout envelope for debugging (no parsing, no judgment)."""
        target = safe_write_path(ctx.run.root, f"results/{contract.task_id}.agent_raw.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(stdout, encoding="utf-8")

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

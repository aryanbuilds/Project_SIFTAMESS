"""Claude Code headless adapter (Epic F, F8) — the live autonomous executor (CORE).

Thin wrapper around ``claude -p`` in non-interactive JSON mode. The agent is
constrained to SIFTMesh's typed tools by pointing it at the FastMCP server
(``siftmesh mcp-serve``, the 10 allowlisted tools — no raw shell) and narrowing
``--allowedTools`` to the contract's single tool. When the CLI or all auth
(subscription token / OAuth bearer / API key) is absent the adapter is unavailable
and the registry falls closed to the deterministic floor.

HARD GATES (CLAUDE §2A/§2B):
* The exact CLI flags are UNVERIFIED — they are isolated in ``_build_claude_argv``
  so they can be corrected in one place after confirming via ``claude --help`` /
  the claude-code docs before any live run.
* Live validation against real evidence is HUMAN-GATED. Unit tests mock the
  subprocess boundary only; do NOT autonomously run a live agent against evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    permission_mode: str = "acceptEdits",
) -> list[str]:
    """Build the headless ``claude -p`` argv (flags isolated here; Epic-I6 research-grounded).

    Flags confirmed via the claude-code docs (deepwiki) but **re-confirm `claude --help` before any
    live run** — the single place to correct them. ``--mcp-config`` constrains the agent to the
    typed tools; ``--allowedTools`` narrows to the contract's tool(s); ``--permission-mode`` is
    non-interactive; ``--model`` (when set) pins the model.
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
        "--allowedTools",
        tools,
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
            contract, run_id=ctx.run.run_id, critic_feedback=ctx.critic_feedback
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
        """Write a per-run MCP config pointing at SIFTMesh's stdio FastMCP server."""
        config = {
            "mcpServers": {
                "siftmesh": {
                    "command": "siftmesh",
                    "args": ["mcp-serve"],
                    "env": {
                        "SIFTMESH_RUN_ROOT": str(ctx.run.root),
                        "SIFTMESH_EVIDENCE_ROOT": str(ctx.evidence_root),
                    },
                }
            }
        }
        target = safe_write_path(ctx.run.root, "context/mcp_config.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return target

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

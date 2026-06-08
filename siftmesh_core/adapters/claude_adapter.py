"""Claude Code headless adapter (Epic F, F8) — the live autonomous executor (CORE).

Thin wrapper around ``claude -p`` in non-interactive JSON mode. The agent is
constrained to SIFTMesh's typed tools by pointing it at the FastMCP server
(``siftmesh mcp-serve``, the 10 allowlisted tools — no raw shell) and narrowing
``--allowedTools`` to the contract's single tool. When the CLI or
``ANTHROPIC_API_KEY`` is absent the adapter is unavailable and the registry falls
closed to the deterministic floor.

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

from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.spotlight import scan_injection, wrap_evidence
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult

_MCP_TOOL_PREFIX = "mcp__siftmesh__"


def _build_claude_argv(
    cli_path: str, prompt: str, mcp_config: Path, allowed_tools: list[str]
) -> list[str]:
    """Build the headless ``claude -p`` argv (flags isolated here; UNVERIFIED).

    Re-confirm against ``claude --help`` before any live run; this is the single
    place to correct flags. ``--mcp-config`` constrains the agent to SIFTMesh's
    typed tools; ``--allowedTools`` narrows further to the contract's tool(s).
    """
    tools = ",".join(f"{_MCP_TOOL_PREFIX}{t}" for t in allowed_tools)
    return [
        cli_path,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--mcp-config",
        str(mcp_config),
        "--allowedTools",
        tools,
    ]


@register
class ClaudeHeadlessAdapter(ExecutorAdapter):
    """Run the live Claude Code agent headlessly, constrained to the typed tools."""

    profile_id = "claude_headless"
    backend_label = "claude_headless"

    def available(self) -> bool:
        return shutil.which(self.settings.claude_cli_path) is not None and bool(
            os.environ.get("ANTHROPIC_API_KEY")
        )

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        profile = ctx.requested_profile or self.profile_id
        rows = [{"path": a.path, "sha256": a.sha256} for a in contract.input_artifacts]
        prompt = (
            f"{contract.objective}\n\nSuccess criteria:\n- "
            + "\n- ".join(contract.success_criteria)
            + "\n\n"
            + wrap_evidence(rows, run_id=ctx.run.run_id)
        )
        mcp_config = self._write_mcp_config(ctx)
        argv = _build_claude_argv(
            self.settings.claude_cli_path, prompt, mcp_config, contract.allowed_tools
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
        self._scan(ctx, contract, str(envelope.get("result", "")))
        status = "success" if not envelope.get("is_error", proc.returncode != 0) else "error"
        # Claims are produced by the agent calling the typed MCP tools (audited to
        # tool_calls.jsonl); structured claim extraction is finalized in Epic G. The
        # envelope is captured honestly here — no synthetic claims are fabricated.
        return TaskResult(
            task_id=contract.task_id,
            profile=profile,
            adapter=self.profile_id,
            attempt=ctx.attempt,
            status=status,
            started_utc=started,
            ended_utc=datetime.now(UTC),
            errors=[] if status == "success" else [str(envelope.get("subtype", "agent_error"))],
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

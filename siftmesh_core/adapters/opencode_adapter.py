"""OpenCode headless adapter (Epic F, F8) - secondary live executor.

Thin wrapper around ``opencode run … --format json``. OpenCode DOES support MCP servers (via the
``mcp`` key in an ``opencode.json`` config), but SIFTMesh does not yet wire the run-scoped typed
server for it (round-2 work), so today it cannot be constrained to the typed tools as tightly as the
Claude adapter - it is the secondary path. Unavailable (→ floor) when the CLI is absent. Live
validation is HUMAN-GATED; unit tests mock the subprocess boundary only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime

from siftmesh_core.adapters.agent_result import parse_agent_result
from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.profiles import effective_model
from siftmesh_core.adapters.prompt_builder import build_task_prompt
from siftmesh_core.adapters.sandbox import scratch_cwd
from siftmesh_core.adapters.spotlight import scan_injection
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult

# Model id is operator-configured at live time; a placeholder default is fine for argv.
_DEFAULT_MODEL = "anthropic/claude-opus-4-8"


def _build_opencode_argv(cli_path: str, prompt: str, model: str) -> list[str]:
    """Build the headless ``opencode run`` argv (Epic-I6 research-grounded).

    Confirmed via opencode.ai/docs/cli: the non-interactive form is ``opencode run <prompt>`` with
    ``--format json`` (NOT ``--output-format``, NOT ``-p``). Re-confirm ``opencode run --help``
    before a live run; this is the single place to correct the flags.
    """
    return [cli_path, "run", prompt, "--model", model, "--format", "json"]


def _collect_text(stdout: str) -> str:
    """Concatenate the agent's text from OpenCode's line-delimited JSON events (best-effort).

    OpenCode streams ``{"type": <kind>, ..., "part": {"text": ...}}`` events; the assistant's answer
    arrives as ``type == "text"`` events. We take ``part.text`` ONLY from those (skipping
    ``reasoning`` / ``tool_use`` / ``step_*`` events) so chain-of-thought - which may hold a draft
    ``{claims:[…]}`` - never leaks into the parsed answer. If nothing parses, raw stdout is used.
    """
    parts: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        text = part.get("text") if isinstance(part, dict) else event.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts) if parts else stdout


@register
class OpenCodeHeadlessAdapter(ExecutorAdapter):
    """Run the live OpenCode agent headlessly (secondary; no MCP constraint)."""

    profile_id = "opencode_headless"
    backend_label = "opencode"

    def available(self) -> bool:
        return shutil.which(self.settings.opencode_cli_path) is not None

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        prompt = build_task_prompt(
            contract,
            run_id=ctx.run.run_id,
            critic_feedback=ctx.critic_feedback,
            incident_objective=ctx.incident_objective,
        )
        prof = self.profile()
        model = effective_model(
            self.settings, self.profile_id, prof.model if (prof and prof.model) else _DEFAULT_MODEL
        )
        cli = self.settings.opencode_cli_path
        argv = _build_opencode_argv(cli, prompt, model or _DEFAULT_MODEL)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.settings.agent_timeout_seconds,
                shell=False,
                check=False,
                cwd=scratch_cwd(
                    ctx.run, contract.task_id
                ),  # never the operator CWD (injection/escape)
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._error(contract, ctx, started, "agent_failed_or_timeout")
        text = _collect_text(proc.stdout)
        self._scan(ctx, contract, text)  # injection scan on the agent's output
        if proc.returncode != 0 and not text.strip():
            return self._error(contract, ctx, started, "agent_error")
        # K3: capture the agent's claims; under-anchored claims land as 'unsupported' (never
        # fabricated) so the critic drives a retry-with-feedback.
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

"""OpenCode headless adapter (Epic F, F8) — secondary live executor.

Thin wrapper around ``opencode run … --output-format json``. OpenCode has no MCP
support, so it cannot be constrained to the typed tools as tightly as the Claude
adapter — it is the secondary path. Unavailable (→ floor) when the CLI is absent.
Live validation is HUMAN-GATED; unit tests mock the subprocess boundary only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime

from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.spotlight import wrap_evidence
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult

# Model id is operator-configured at live time; a placeholder default is fine for argv.
_DEFAULT_MODEL = "anthropic/claude-opus-4-8"


def _build_opencode_argv(cli_path: str, prompt: str, model: str) -> list[str]:
    """Build the headless ``opencode run`` argv (flags isolated; UNVERIFIED)."""
    return [cli_path, "run", prompt, "--model", model, "--output-format", "json"]


@register
class OpenCodeHeadlessAdapter(ExecutorAdapter):
    """Run the live OpenCode agent headlessly (secondary; no MCP constraint)."""

    profile_id = "opencode_headless"
    backend_label = "opencode"

    def available(self) -> bool:
        return shutil.which(self.settings.opencode_cli_path) is not None

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        started = datetime.now(UTC)
        profile = ctx.requested_profile or self.profile_id
        rows = [{"path": a.path, "sha256": a.sha256} for a in contract.input_artifacts]
        prompt = f"{contract.objective}\n\n{wrap_evidence(rows, run_id=ctx.run.run_id)}"
        argv = _build_opencode_argv(self.settings.opencode_cli_path, prompt, _DEFAULT_MODEL)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.settings.agent_timeout_seconds,
                shell=False,
                check=False,
            )
            envelope = json.loads(proc.stdout)
            status = "success" if not envelope.get("is_error", proc.returncode != 0) else "error"
            code = None if status == "success" else str(envelope.get("subtype", "agent_error"))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            status, code = "error", "agent_failed_or_timeout"
        except json.JSONDecodeError:
            status, code = "error", "agent_bad_json"
        return TaskResult(
            task_id=contract.task_id,
            profile=profile,
            adapter=self.profile_id,
            attempt=ctx.attempt,
            status=status,
            started_utc=started,
            ended_utc=datetime.now(UTC),
            errors=[] if status == "success" else [code or "agent_error"],
        )

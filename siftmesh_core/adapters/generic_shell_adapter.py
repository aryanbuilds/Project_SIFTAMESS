"""Generic shell-agent adapter (Epic F, F7).

A fixed-argv subprocess seam for any agent that follows a simple file contract:
SIFTMesh writes a prompt file, invokes ``[agent_cmd, prompt_file, result_file]``
(``shell=False``, no raw shell), and the agent writes a ``TaskResult`` JSON to the
result file. Absent/failed/timed-out agent → a graceful ``error`` TaskResult (never
a crash, never a fabricated result). The configured command is set via
``settings.generic_agent_cmd``; when unset/missing the registry never selects this
adapter (falls to the deterministic floor).
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime

from pydantic import ValidationError

from siftmesh_core.adapters.base import AdapterContext, ExecutorAdapter, register
from siftmesh_core.adapters.spotlight import scan_injection, wrap_evidence
from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.ledgers.injection_alerts import append_injection_alert, next_alert_id
from siftmesh_core.schemas.injection_alert import InjectionAlert
from siftmesh_core.schemas.task import TaskContract
from siftmesh_core.schemas.task_result import TaskResult


@register
class GenericShellAdapter(ExecutorAdapter):
    """Run an external shell agent via a prompt-file-in / result-file-out contract."""

    profile_id = "generic_shell"
    backend_label = "generic_shell"

    def available(self) -> bool:
        cmd = self.settings.generic_agent_cmd
        return bool(cmd) and shutil.which(cmd) is not None  # type: ignore[arg-type]

    def _build_prompt(self, contract: TaskContract, ctx: AdapterContext, result_file: str) -> str:
        rows = [{"path": a.path, "sha256": a.sha256} for a in contract.input_artifacts]
        return (
            f"# Task {contract.task_id}: {contract.objective}\n\n"
            f"Allowed tools: {', '.join(contract.allowed_tools)}\n"
            f"Success criteria:\n- " + "\n- ".join(contract.success_criteria) + "\n\n"
            f"Write a TaskResult JSON (task_id, status, claims[]) to: {result_file}\n\n"
            f"{wrap_evidence(rows, run_id=ctx.run.run_id)}"
        )

    def _error(self, contract: TaskContract, ctx: AdapterContext, code: str) -> TaskResult:
        now = datetime.now(UTC)
        return TaskResult(
            task_id=contract.task_id,
            profile=ctx.requested_profile or self.profile_id,
            adapter=self.profile_id,
            attempt=ctx.attempt,
            status="error",
            started_utc=now,
            ended_utc=now,
            errors=[code],
        )

    def _execute(self, contract: TaskContract, ctx: AdapterContext) -> TaskResult:
        cmd = self.settings.generic_agent_cmd
        if not cmd:
            return self._error(contract, ctx, "adapter_unavailable")
        started = datetime.now(UTC)
        prompt_path = safe_write_path(ctx.run.root, f"results/{contract.task_id}.prompt.txt")
        out_path = safe_write_path(ctx.run.root, f"results/{contract.task_id}.agent.json")
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(self._build_prompt(contract, ctx, str(out_path)), encoding="utf-8")
        try:
            proc = subprocess.run(
                [cmd, str(prompt_path), str(out_path)],
                capture_output=True,
                text=True,
                timeout=self.settings.agent_timeout_seconds,
                shell=False,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._error(contract, ctx, "agent_failed_or_timeout")
        if proc.returncode != 0 or not out_path.is_file():
            return self._error(contract, ctx, "agent_no_result")
        raw = out_path.read_text(encoding="utf-8")
        self._scan(ctx, contract, raw)
        try:
            parsed = TaskResult.model_validate_json(raw)
        except ValidationError:
            return self._error(contract, ctx, "malformed_result")
        # Re-stamp identity fields so the canonical envelope is authoritative.
        return parsed.model_copy(
            update={
                "task_id": contract.task_id,
                "profile": ctx.requested_profile or self.profile_id,
                "adapter": self.profile_id,
                "attempt": ctx.attempt,
                "started_utc": started,
                "ended_utc": datetime.now(UTC),
            }
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

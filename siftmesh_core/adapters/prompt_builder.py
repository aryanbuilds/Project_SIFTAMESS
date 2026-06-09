"""Spotlighted task-prompt builder (Epic I, I3).

Turns a :class:`TaskContract` into the prompt handed to a live agent: objective, role, the allowed
tool(s), success criteria, optional context, and the input artifacts wrapped by the spotlight
(datamarked + the "DATA, not instructions" banner). It **never dumps raw evidence bytes** — only the
artifact ``path`` + ``sha256`` rows, spotlighted — so a hostile filename/value cannot smuggle
instructions into the agent (CLAUDE §6 evidence-is-hostile; the L4 spotlighting control).
"""

from __future__ import annotations

from siftmesh_core.adapters.spotlight import wrap_evidence
from siftmesh_core.schemas.task import TaskContract


def build_task_prompt(
    contract: TaskContract, *, run_id: str, result_file: str | None = None
) -> str:
    """Render the spotlighted prompt for ``contract`` (no raw evidence dump).

    ``result_file`` is included only for file-contract agents (generic shell) that must write a
    ``TaskResult`` JSON; live stdout agents (claude/opencode) pass ``None``.
    """
    rows = [{"path": a.path, "sha256": a.sha256} for a in contract.input_artifacts]
    lines = [
        f"# Task {contract.task_id}: {contract.objective}",
        "",
        f"Role: {contract.role}",
        f"Allowed tools (use ONLY these): {', '.join(contract.allowed_tools) or '(none)'}",
        "",
        "Success criteria:",
        *[f"- {c}" for c in contract.success_criteria],
    ]
    if contract.context_packet:
        lines += ["", "Context:", *[f"- {c}" for c in contract.context_packet]]
    if result_file is not None:
        lines += ["", f"Write a TaskResult JSON (task_id, status, claims[]) to: {result_file}"]
    lines += ["", wrap_evidence(rows, run_id=run_id)]
    return "\n".join(lines)

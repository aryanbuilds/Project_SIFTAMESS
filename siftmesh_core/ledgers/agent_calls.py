"""Agent-call audit ledger (Epic F, F6).

Appends one :class:`AgentCall` per executor dispatch to ``audit/agent_calls.jsonl``,
built on the generic validate-before-write JSONL ledger. ``next_agent_call_id``
mints a deterministic ``AGENT-NNN`` from the current ledger length (mirrors how the
tool ledger mints ``TOOL-NNN``).
"""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.ledgers.jsonl_ledger import append_record, read_records
from siftmesh_core.schemas.agent_call import AgentCall

_AGENT_CALLS = Path("audit") / "agent_calls.jsonl"


def next_agent_call_id(run_root: Path | str) -> str:
    """Return the next ``AGENT-NNN`` id from the current ledger length."""
    return f"AGENT-{len(read_agent_calls(run_root)) + 1:03d}"


def append_agent_call(
    run_root: Path | str,
    call: AgentCall,
    *,
    evidence_root: Path | str | None = None,
) -> Path:
    """Append one agent-call record to ``audit/agent_calls.jsonl``."""
    return append_record(run_root, _AGENT_CALLS, call, evidence_root=evidence_root)


def read_agent_calls(run_root: Path | str) -> list[AgentCall]:
    """Read all agent-call records for a run."""
    return list(read_records(Path(run_root) / _AGENT_CALLS, AgentCall))

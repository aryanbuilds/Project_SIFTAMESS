"""Tag classification for the real-time log stream.

Maps orchestration events (by name) and typed ledger records (by ledger path) to a tag in
``[info] [agent] [tool_log] [alert] [output] [result] [tasks]`` plus a one-line summary.
Every value interpolated into a summary is **escaped** (``rich.markup.escape``) and control
chars stripped - claim text, source artifacts and ``reason`` strings are evidence-derived
(a terminal-markup / ANSI injection surface), never trusted.
"""

from __future__ import annotations

from typing import Any

# Tag → Rich colour. Semantic, theme-independent concrete colour names.
TAG_STYLE: dict[str, str] = {
    "info": "white",
    "agent": "blue",
    "tool_log": "cyan",
    "alert": "bold red",
    "output": "green",
    "result": "green",
    "tasks": "bold cyan",
}

# Orchestration event name → tag (default = info).
_EVENT_TAG: dict[str, str] = {
    # pipeline / task lifecycle
    "transition": "tasks",
    "task_dispatched": "tasks",
    "decision": "tasks",
    "plan_started": "tasks",
    "plan_complete": "tasks",
    "cap_reached": "tasks",
    "parallel_dispatch_started": "tasks",
    "tier_floor_forced": "tasks",
    # problems / governance stops
    "gate_rejected": "alert",
    "gate_blocked": "alert",
    "halted": "alert",
    "result_missing": "alert",
    "result_malformed": "alert",
    "reports_failed": "alert",
    "contradiction_detected": "alert",
    "critic_injection_detected": "alert",
    "evidence_modified": "alert",
    "task_quarantined": "alert",
    # results / findings
    "critic_verdict": "result",
    "claim_promoted": "result",
    "result_collected": "result",
    "critic_complete": "result",
    # outputs
    "reports_generated": "output",
    "run_complete": "output",
}

# Ledger basename → tag.
_LEDGER_TAG: dict[str, str] = {
    "agent_calls.jsonl": "agent",
    "tool_calls.jsonl": "tool_log",
    "injection_alerts.jsonl": "alert",
    "contradiction_ledger.jsonl": "alert",
    "retries.jsonl": "alert",
    "claim_ledger.jsonl": "result",
    "unsupported_claims.jsonl": "result",
    "confidence_changes.jsonl": "result",
    "critic_verdicts.jsonl": "result",
    "followups.jsonl": "info",
    "custody_log.jsonl": "info",
}


def _esc(value: Any, *, limit: int = 80) -> str:
    """Escape Rich markup + strip control chars + truncate (hostile-evidence safe)."""
    from rich.markup import escape

    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ch >= " " or ch == "\t").replace("\t", " ")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return escape(text)


def _base(name: str | None) -> str:
    return (name or "?").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _pick(fields: dict[str, Any], *keys: str) -> str:
    """`key=value` for the present keys, escaped."""
    parts = [f"{k}={_esc(fields[k], limit=40)}" for k in keys if fields.get(k) is not None]
    return " ".join(parts)


def classify_event(event: str, fields: dict[str, Any]) -> tuple[str, str]:
    """Return ``(tag, summary)`` for an orchestration event."""
    tag = _EVENT_TAG.get(event, "info")
    if event == "transition":
        dur = fields.get("duration_ms")
        suffix = f" ({int(dur)}ms)" if isinstance(dur, (int, float)) else ""
        summary = (
            f"{_esc(fields.get('from_state'), limit=24)} → "
            f"{_esc(fields.get('to_state'), limit=24)}"
            f" [iter {_esc(fields.get('iteration'), limit=6)}]{suffix}"
        )
    elif event == "task_dispatched":
        summary = (
            f"{_esc(fields.get('task_id'), limit=24)} via "
            f"{_esc(fields.get('profile') or fields.get('adapter'), limit=24)}"
            f" [{_esc(fields.get('status'), limit=16)}]"
        )
    elif event == "decision":
        summary = f"decide → {_esc(fields.get('action'), limit=24)}: {_esc(fields.get('reason'))}"
    elif event == "plan_complete":
        summary = f"plan ready: {_esc(fields.get('task_count'), limit=8)} task(s)"
    elif event in ("gate_rejected", "gate_blocked", "gate_approved"):
        summary = f"gate {_esc(fields.get('gate'), limit=16)}: {event.removeprefix('gate_')}"
    elif event == "halted":
        summary = (
            f"halted at {_esc(fields.get('state'), limit=24)} "
            f"(gate={_esc(fields.get('blocked_gate'), limit=16)})"
        )
    elif event == "critic_verdict":
        summary = (
            f"{_esc(fields.get('task_id'), limit=24)}: {_esc(fields.get('verdict'), limit=28)}"
        )
    elif event == "reports_generated":
        summary = f"reports: {_esc(fields.get('count'), limit=8)} written"
    elif event == "run_complete":
        summary = "run complete"
    elif event == "cap_reached":
        summary = f"cap {_esc(fields.get('cap'), limit=24)}={_esc(fields.get('value'), limit=8)}"
    else:
        rest = _pick(fields, "task_id", "reason", "count", "state", "gate", "tasks")
        summary = f"{event}{(' ' + rest) if rest else ''}"
    return tag, summary


def classify_record(rel: str, record: Any) -> tuple[str, str, str | None]:
    """Return ``(tag, summary, task_id)`` for a typed ledger record."""
    base = _base(rel)
    tag = _LEDGER_TAG.get(base, "info")

    def g(*names: str) -> Any:
        """First present (non-None) attribute among ``names``."""
        for n in names:
            val = getattr(record, n, None)
            if val is not None:
                return val
        return None

    task_id = g("task_id")
    if base == "agent_calls.jsonl":
        summary = (
            f"{_esc(g('agent_call_id'), limit=16)} {_esc(task_id, limit=20)} "
            f"{_esc(g('profile', 'adapter'), limit=20)} [{_esc(g('status'), limit=16)}]"
        )
    elif base == "tool_calls.jsonl":
        src = _base(str(g("source_artifact") or ""))
        summary = (
            f"{_esc(g('tool_call_id'), limit=16)} {_esc(g('tool_name'), limit=28)} "
            f"[{_esc(g('status'), limit=12)}] {_esc(src, limit=32)}"
        )
    elif base == "injection_alerts.jsonl":
        summary = (
            f"injection? {_esc(task_id, limit=20)} "
            f"sev={_esc(g('severity'), limit=10)} {_esc(g('description', 'pattern'), limit=48)}"
        )
    elif base in ("claim_ledger.jsonl", "unsupported_claims.jsonl"):
        summary = (
            f"{_esc(g('claim_id'), limit=20)} [{_esc(g('status'), limit=14)}] "
            f"conf={_esc(g('confidence'), limit=6)} {_esc(g('claim'), limit=56)}"
        )
    elif base == "critic_verdicts.jsonl":
        summary = f"{_esc(task_id, limit=20)}: {_esc(g('verdict'), limit=28)}"
    elif base == "retries.jsonl":
        summary = (
            f"retry {_esc(task_id, limit=20)} attempt={_esc(g('attempt'), limit=4)} "
            f"{_esc(g('retry_cause', 'reason'), limit=40)}"
        )
    elif base == "contradiction_ledger.jsonl":
        summary = (
            f"contradiction {_esc(g('contradiction_id'), limit=20)} {_esc(g('rule'), limit=40)}"
        )
    elif base == "followups.jsonl":
        summary = f"follow-up {_esc(g('reason'), limit=24)} {_esc(g('artifact'), limit=40)}"
    else:
        summary = f"{base}: {_esc(g('id', 'claim_id', 'tool_call_id'), limit=40)}"
    return tag, summary, (str(task_id) if task_id is not None else None)

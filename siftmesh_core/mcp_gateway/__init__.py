"""Typed, evidence-safe forensic tool gateway (Epic D).

Eight typed forensic tools (CLAUDE.md §7) exposed over FastMCP stdio, behind an
allowlist registry (:mod:`registry`), a single audited-execution wrapper
(:mod:`audit_exec`) that writes full provenance to ``audit/tool_calls.jsonl``, and
a real-vs-SIFT-lane backend abstraction (:mod:`backends`). REAL-ONLY: every tool
wraps a real library; a missing backend fails closed, never a fake fallback.

CLI-first: the CLI calls these service functions directly; the FastMCP server is a
thin adapter over the same functions.
"""

from __future__ import annotations

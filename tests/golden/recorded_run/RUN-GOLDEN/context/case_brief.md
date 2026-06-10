# Case Brief

- Case: `golden-case`
- Run: RUN-20260610-071122
- Template: windows_initial_triage
- Mode: standard

## Objective

Triage the supplied Windows evidence and produce evidence-backed findings, each anchored to a tool execution and a source hash.

## Scope

3 artifact(s); families present: Windows Security event log, Prefetch (program execution), Windows registry hive.

## Constraints

- Evidence is read-only; every write is confined to the run directory.
- Every claim must bind to a tool_call_id + source_sha256; unsupported claims are never reported as fact.
- Only the typed, allowlisted forensic tools may be used; no raw shell.

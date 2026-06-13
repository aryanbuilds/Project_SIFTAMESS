# Case Brief

- Case: `rocba_full`
- Run: RUN-20260612-163324
- Template: windows_initial_triage
- Mode: standard

## Objective

Operator incident objective (investigate TOWARD this; full brief in `context/incident_brief.md`):

> The Fred Rocba Case 1 2 Fred Rocba is a victim of a Break-In and IP Theft 3 Fred Rocba and SRL Victim of Break-In and IP Theft: Background 4 Why Stark Research Labs? 5 System and Setup Information 6 Fred is on vacation – Pictures synced to Fred’s home system 7 The Game is Afoot! Key Questions to Answer

Produce evidence-backed findings that bear on this objective, each anchored to a tool execution and a source hash.

## Scope

1 artifact(s); families present: Disk image.

## Constraints

- Evidence is read-only; every write is confined to the run directory.
- Every claim must bind to a tool_call_id + source_sha256; unsupported claims are never reported as fact.
- Only the typed, allowlisted forensic tools may be used; no raw shell.

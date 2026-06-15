# Case Brief

- Case: `case_fast`
- Run: RUN-20260615-064002
- Template: windows_initial_triage
- Mode: standard

## Objective

Operator incident objective (investigate TOWARD this; full brief in `context/incident_brief.md`):

> What key projects did Fred Rocba have access to? What was stolen, where to, how, and when? The Fred Rocba Case 1 2 Fred Rocba is a victim of a Break-In and IP Theft 3 Fred Rocba and SRL Victim of Break-In and IP Theft: Background 4 Why Stark Research Labs? 5 System and Setup Information 6 Fred is on vacation – Pictures synced to Fred’s home system 7 The Game is Afoot! Key Questions to Answer

Produce evidence-backed findings that bear on this objective, each anchored to a tool execution and a source hash.

## Scope

4 artifact(s); families present: Disk image, Archive, Unrecognised artifact.

## Constraints

- Evidence is read-only; every write is confined to the run directory.
- Every claim must bind to a tool_call_id + source_sha256; unsupported claims are never reported as fact.
- Only the typed, allowlisted forensic tools may be used; no raw shell.

# SIFTMesh Forensic Report - RUN-GOLDEN

## Executive summary

- Confirmed findings: 5
- Inferred findings: 2
- Unsupported claims (rejected, not facts): 0
- Contradictions detected: 0
- Self-correction retries: 0
- Prompt-injection alerts (logged, not executed): 0
- Critic verdicts: accepted=4
- Run status: driven by discrete CLI commands (no engine snapshot)

## Scope & case metadata

- Case: golden-case
- Run: RUN-20260610-071122
- Sealed (UTC): 2026-06-10 07:11:22.974185+00:00
- Evidence artifacts: 3
- SIFTMesh tool version: 0.1.0

## Methodology & tools

| Tool | Backend | Invocations |
| --- | --- | --- |
| analyze_prefetch | real | 1 |
| build_timeline | real | 1 |
| extract_registry_run_keys | real | 1 |
| parse_evtx_security | real | 1 |

## Timeline of events (UTC)

| Timestamp | Status | Event |
| --- | --- | --- |
| 2026-06-10 07:11:23.012578+00:00 | confirmed | CMD.EXE executed 3 time(s). |
| 2026-06-10 07:11:23.012578+00:00 | inferred | 1 execution timestamp(s) recorded. |
| 2026-06-10 07:11:23.081482+00:00 | confirmed | 1 autostart Run/RunOnce value(s) found. |
| 2026-06-10 07:11:23.081482+00:00 | confirmed | Autostart Run key 'Sidebar' present under \Software\Microsoft\Windows\CurrentVersion\Run. |
| 2026-06-10 07:11:23.091793+00:00 | confirmed | Parsed 7 Security event(s). |
| 2026-06-10 07:11:23.091793+00:00 | confirmed | Security EventID 4625 (failed logon) observed (event #4). |
| 2026-06-10 07:11:23.101472+00:00 | inferred | Unified timeline built: 8 events across 2 source(s). |

## Confirmed findings

**TASK-003-CLAIM-001** - Parsed 7 Security event(s).
- artifact `Security.evtx` · sha256 `50c87926d2dfed97…` · tool `parse_evtx_security` · call `TOOL-003` · confidence 0.950
- ATT&CK: Execution / T1059 Command and Scripting Interpreter

**TASK-001-CLAIM-001** - CMD.EXE executed 3 time(s).
- artifact `CMD.EXE-89305D47.pf` · sha256 `6127d820b031cac7…` · tool `analyze_prefetch` · call `TOOL-001` · confidence 0.900
- ATT&CK: Execution / T1204 User Execution

**TASK-003-CLAIM-002** - Security EventID 4625 (failed logon) observed (event #4).
- artifact `Security.evtx` · sha256 `50c87926d2dfed97…` · tool `parse_evtx_security` · call `TOOL-003` · confidence 0.900
- ATT&CK: Execution / T1059 Command and Scripting Interpreter

**TASK-002-CLAIM-001** - 1 autostart Run/RunOnce value(s) found.
- artifact `NTUSER.DAT` · sha256 `6a38fcea92411396…` · tool `extract_registry_run_keys` · call `TOOL-002` · confidence 0.850
- ATT&CK: Persistence / T1547.001 Registry Run Keys / Startup Folder

**TASK-002-CLAIM-002** - Autostart Run key 'Sidebar' present under \Software\Microsoft\Windows\CurrentVersion\Run.
- artifact `NTUSER.DAT` · sha256 `6a38fcea92411396…` · tool `extract_registry_run_keys` · call `TOOL-002` · confidence 0.850
- ATT&CK: Persistence / T1547.001 Registry Run Keys / Startup Folder

## Inferred findings (lower confidence)

**TASK-001-CLAIM-002** - 1 execution timestamp(s) recorded.
- INFERRED · artifact `CMD.EXE-89305D47.pf` · sha256 `6127d820b031cac7…` · tool `analyze_prefetch` · call `TOOL-001` · confidence 0.700
- ATT&CK: Execution / T1204 User Execution

**TASK-004-CLAIM-001** - Unified timeline built: 8 events across 2 source(s).
- INFERRED · artifact `timeline` · sha256 `4ad00a02214d95f6…` · tool `build_timeline` · call `TOOL-004` · confidence 0.600

## MITRE ATT&CK mapping

| Evidence type | Tactic / Technique | Name | Claims |
| --- | --- | --- | --- |
| program_execution | Execution / T1204 | User Execution | 2 |
| registry_autostart | Persistence / T1547.001 | Registry Run Keys / Startup Folder | 2 |
| timeline | (unmapped) | - | 1 |
| windows_event_log | Execution / T1059 | Command and Scripting Interpreter | 2 |
_ATT&CK reference: MITRE ATT&CK (https://attack.mitre.org/) (CC-BY-4.0)._

## Contradictions & resolution

None detected.

## Self-correction & retries

No self-correction events recorded.

## Chain of custody

| Artifact | sha256 | Action | Actor | Tool | Result |
| --- | --- | --- | --- | --- | --- |
| CMD.EXE-89305D47.pf | 6127d820b031cac7… | analyze_prefetch | siftmesh | analyze_prefetch | success |
| NTUSER.DAT | 6a38fcea92411396… | extract_registry_run_keys | siftmesh | extract_registry_run_keys | success |
| Security.evtx | 50c87926d2dfed97… | parse_evtx_security | siftmesh | parse_evtx_security | success |
| timeline | 4ad00a02214d95f6… | build_timeline | siftmesh | build_timeline | success |

## Appendix A - tool-execution log (complete)

| tool_call_id | Tool | Source artifact | source_sha256 | Status | Code |
| --- | --- | --- | --- | --- | --- |
| TOOL-001 | analyze_prefetch | CMD.EXE-89305D47.pf | 6127d820b031cac7f5fb1e6d45e244aa48cbb7fa62910ad0317eacb71a0edcd0 | success | - |
| TOOL-002 | extract_registry_run_keys | NTUSER.DAT | 6a38fcea924113963e4931725cc4c2f4f10e1240234cb1867d101a1cd92cd439 | success | - |
| TOOL-003 | parse_evtx_security | Security.evtx | 50c87926d2dfed9776906ffbcc77e61577940910a71fb1c1871860a4e2213456 | success | - |
| TOOL-004 | build_timeline | timeline | 4ad00a02214d95f6e8a449395f4ad99be293f7da1c76f3e22527afa8cb066033 | success | - |

## Appendix B - unsupported claims (rejected, NOT findings)

None - every recorded claim was evidence-anchored.

## Appendix C - prompt-injection alerts (hostile-evidence handling)

None.

## Limitations & assumptions

- This report is generated by an automated triage system. It is **NOT a claim of court admissibility or forensic completeness**; findings are evidence-anchored leads for an analyst.
- Timestamps are interpreted and reported in UTC.
- Evidence is treated as hostile: filenames and content are data, never instructions.
- Evidence types without an ATT&CK mapping: timeline.
- Load note: no run_state.json (run driven by discrete commands; engine snapshot absent)

# Agent Execution Logs — real ROCBA run (traceable, timestamped)

This is the **real, structured execution log** of SIFTMesh's autonomous run against the **ROCBA**
evidence on the SANS SIFT workstation — the exact JSONL records, with timestamps, that let a reviewer
**trace any finding back to the specific tool execution that produced it.** Nothing here is a fixture
or a demo; every line below is copied from the run's append-only ledgers.

> The **complete ledgers for both runs are committed** under [`logs/`](logs/) — the full `audit/`,
> `claims/`, `reports/`, `context/`, `tasks/`, and chain-of-custody ledgers (see
> [`logs/README.md`](logs/README.md)). This file is the guided walkthrough of one trace. Only the heavy
> *derived* trees (per-tool `results/`, the carved `evidence/extracted/`, the 11 GB Plaso
> `super_timeline/`) and the raw evidence images stay off-repo (size + chain of custody).

| Run | Evidence | SHA-256 | Result |
|---|---|---|---|
| Disk `RUN-20260612-163324` | `rocba-cdrive.e01` (23,678,691,658 B) | `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` | 634 claims · 0 unsupported · 0 contradictions |
| Memory `RUN-20260612-082630` | `Rocba-Memory.raw` (19,050,528,768 B) | `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` | vol3, 6 plugins, 0 failed |

---

## 1. The trace: a finding → its claim → the tool execution → the timestamps

Take one finding from the report — *"Parsed 2 PowerShell event(s)"* (host SRL-FORGE, EventID 4104).
Here is the **complete chain**, each link a real ledger line.

**(1) The promoted finding** — `claims/claim_ledger.jsonl`. It cites a `tool_call_id` **and** the
`source_sha256` of the exact bytes parsed (the hallucination firewall: no anchor → not a fact):

```json
{"claim_id":"TASK-003-CLAIM-001","task_id":"TASK-003","status":"confirmed","claim":"Parsed 2 PowerShell event(s).","confidence":0.95,"evidence_type":"windows_event_log","source_artifact":"evidence/extracted/Microsoft-Windows-PowerShell%4Operational.evtx","source_sha256":"e81d6040eaacd01ee9c4c4f3d26c94aa3fbe14e95d276caa4a23d79b310d3f8c","tool_name":"parse_evtx_powershell","tool_call_id":"TOOL-004","timestamp_utc":"2026-06-12T16:46:19.512198Z","supporting_evidence_refs":["TOOL-004"],"contradicting_evidence_refs":[],"requires_human_review":false}
```

**(2) The tool execution it points to** — `audit/tool_calls.jsonl`, `TOOL-004`. Same `source_sha256`
(custody match), with **start/end timestamps**, status, backend, and the structured-output path:

```json
{"tool_call_id":"TOOL-004","tool_name":"parse_evtx_powershell","source_artifact":"evidence/extracted/Microsoft-Windows-PowerShell%4Operational.evtx","source_sha256":"e81d6040eaacd01ee9c4c4f3d26c94aa3fbe14e95d276caa4a23d79b310d3f8c","start_time_utc":"2026-06-12T16:46:19.495308Z","end_time_utc":"2026-06-12T16:46:19.512198Z","status":"success","backend":"real","tool_version":"0.1.0","structured_result_path":"results/TOOL-004.structured.json","raw_output_path":null,"error_code":null}
```

**(3) The dispatch that ran it** — `audit/agent_calls.jsonl`, `AGENT-004` (one line per dispatch:
which profile/adapter, the attempt number, start/end times):

```json
{"agent_call_id":"AGENT-004","task_id":"TASK-003","profile":"deterministic_executor","adapter":"deterministic_executor","backend":"real","attempt":1,"start_time_utc":"2026-06-12T16:46:19.458176Z","end_time_utc":"2026-06-12T16:46:19.533281Z","status":"success","fell_back_from":null}
```

**(4) The orchestration events** — `audit/orchestration_events.jsonl` (every state transition and
dispatch is a timestamped event; transitions carry `duration_ms`):

```json
{"run_id": "RUN-20260612-163324", "from_state": "plan", "to_state": "dispatch", "iteration": 0, "duration_ms": 16, "event": "transition", "level": "info", "timestamp": "2026-06-12T16:34:58.975483Z"}
{"run_id": "RUN-20260612-163324", "task_id": "TASK-003", "profile": "deterministic_executor", "adapter": "deterministic_executor", "status": "success", "event": "task_dispatched", "level": "info", "timestamp": "2026-06-12T16:46:19.534772Z"}
{"run_id": "RUN-20260612-163324", "from_state": "report", "to_state": "done", "iteration": 2, "duration_ms": 86, "event": "transition", "level": "info", "timestamp": "2026-06-12T16:49:23.546185Z"}
```

**Chain proven:** `TASK-003-CLAIM-001` → `TOOL-004` (matching `source_sha256 e81d6040…`) →
`AGENT-004` (dispatch) → the dispatch/transition events — all timestamped, all real.

### The custody anchor (disk extraction)

The headline disk finding traces the same way to the Sleuth Kit extraction, anchored to the **original
image's** SHA-256 (`f2eb856d…` = the sealed manifest hash, i.e. chain of custody to the raw evidence):

```json
{"claim_id":"TASK-001-CLAIM-001","task_id":"TASK-001","status":"confirmed","claim":"Extracted 428 curated artifact(s) from the disk image.","confidence":0.8,"evidence_type":"image_extraction","source_artifact":"rocba-cdrive.e01","source_sha256":"f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67","tool_name":"extract_artifacts_from_image","tool_call_id":"TOOL-001"}
{"tool_call_id":"TOOL-001","tool_name":"extract_artifacts_from_image","source_artifact":"rocba-cdrive.e01","source_sha256":"f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67","start_time_utc":"2026-06-12T16:36:02.498291Z","end_time_utc":"2026-06-12T16:43:42.131708Z","status":"success","backend":"sift_lane","tool_version":"0.1.0","structured_result_path":"results/TOOL-001.structured.json"}
```

## 2. Memory run — Volatility 3 (separate real run)

`RUN-20260612-082630` triaged `Rocba-Memory.raw` with Volatility 3 (subprocess lane). One tool call,
fully timestamped, anchored to the raw image's hash, with both structured + raw output preserved:

```json
{"tool_call_id":"TOOL-001","tool_name":"analyze_memory","source_artifact":"evidence/extracted/Rocba-Memory.raw","source_sha256":"eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563","start_time_utc":"2026-06-12T08:31:34.209699Z","end_time_utc":"2026-06-12T08:38:47.647730Z","status":"success","backend":"sift_lane","tool_version":"0.1.0","structured_result_path":"results/TOOL-001.structured.json","raw_output_path":"results/TOOL-001.raw.json"}
```

## 3. Evidence-as-hostile, logged not executed

The injection scanner flags evidence strings that look like instructions and writes them to
`claims/injection_alerts.jsonl` — **logged only, never executed** (this run flagged 3,949 such
strings across the 5.7 M-event timeline / 383 K USN records / 479 K-file `$MFT`):

```json
{"alert_id":"ALERT-001","source":"tool_result","signature":"base64_blob","snippet":"…\"derived_path\": \"evidence/extracted/Prefetch/ACCOUNTSCONTROLHOST.EXE-00EAE375.pf\", \"sha2…","detected_utc":"…"}
```

## 4. Trace any finding yourself (the commands)

On the workstation, against the same run dir (`$RUN`):

```bash
uv run siftmesh claims show  "$RUN" TASK-003-CLAIM-001   # the finding + its anchor
uv run siftmesh audit tail   "$RUN" --ledger tool-calls  # every tool execution, timestamped
uv run siftmesh audit tail   "$RUN" --ledger agent-calls # every dispatch (attempts, times)
uv run siftmesh replay       "$RUN" --html               # the whole run reconstructed from JSONL
```

Or read the raw ledgers directly: `claims/claim_ledger.jsonl`, `audit/tool_calls.jsonl`,
`audit/agent_calls.jsonl`, `audit/critic_verdicts.jsonl`, `audit/orchestration_events.jsonl`. Live,
every command **also streams a tagged, per-task, %-complete log to the terminal** by default
(`[info] [agent] [tool_log] [alert] [result] [tasks]`; `--quiet` to silence).

## 5. On token usage (honest)

This ROCBA run executed on the **deterministic real-tool floor** — real Sleuth Kit / Volatility 3 /
evtx / regipy / Plaso, **no LLM in the executor** — so there are no executor token counts to report.
`audit/token_budget.jsonl` records the **profile-routing** decisions the engine made (escalation
policy), not LLM tokens:

```json
{"base_profile": "deterministic_executor", "selected_profile": "deterministic_executor", "escalated": false, "reason": "critic_retry", "recorded_utc": "2026-06-12T16:45:03.202131Z"}
```

LLM token usage appears only when a **live agent** drives the run (`--agent claude`); that path writes
agent attempts to `audit/agent_calls.jsonl` and the agent's raw envelope to `results/*.agent_raw.json`.
The deterministic floor is the reproducible baseline; the live agent is the opt-in hero
(`docs/demo_script.md`).

---

*Provenance: every record above is from the real run ledgers (`rocba_full/case_runs/RUN-20260612-163324`,
`case_mem/case_runs/RUN-20260612-082630`). Findings narrative: [`findings_rocba.md`](findings_rocba.md);
accuracy: [`accuracy_report.md`](accuracy_report.md); dataset + reproduce:
[`dataset_documentation.md`](dataset_documentation.md).*

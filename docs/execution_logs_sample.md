# Agent Execution Logs: real ROCBA run (traceable, timestamped)

This file is the real, structured execution log of SIFTMesh's autonomous run against the **ROCBA**
evidence on the SANS SIFT workstation: the exact JSONL records, with timestamps, that let a reviewer
trace any finding back to the specific tool execution that produced it. Nothing here is a fixture or a
demo. Every line below is copied from the run's append-only ledgers. This was a **live Claude-agent
run** (the agent drove the typed tools; heavy tools ran on the floor; disk + memory in one pass).

> The **complete ledgers are committed** under
> [`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002): the full `audit/`,
> `claims/`, `reports/`, `context/`, `tasks/`, and chain-of-custody ledgers (see
> [`logs/README.md`](logs/README.md)). This file walks through one trace. Only the heavy *derived* trees
> (per-tool `results/`, the carved `evidence/extracted/`) and the raw evidence images stay off-repo, for
> size and chain of custody.

| Run | Evidence | SHA-256 | Result |
|---|---|---|---|
| `RUN-20260615-064002` (live `--agent claude`) | `rocba-cdrive.e01` (23,678,691,658 B) | `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` | 223 claims · 0 unsupported · 5 contradictions caught |
| same run, memory | `Rocba-Memory.raw` | `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` | vol3 triage: 2,186 procs, 430 endpoints |

---

## 1. The trace: a finding -> its claim -> the tool execution -> the live dispatch

Take one finding from the report: *"FTK Imager was executed once, last run 2020-11-16T02:43:57Z"* (an
anti-forensic / imaging signal on Fred Rocba's host). Below is the complete chain, each link a real
ledger line.

**(1) The promoted finding**, from `claims/claim_ledger.jsonl`. It cites a `tool_call_id` and the
`source_sha256` of the exact bytes parsed. This is the hallucination firewall: without an anchor, a
statement is not a fact.

```json
{"claim_id":"TASK-007-A1-CLAIM-001","task_id":"TASK-007","status":"confirmed","claim":"FTK Imager (FTK IMAGER.EXE), a forensic disk-imaging tool, was executed once with last run time 2020-11-16T02:43:57Z (run_count=1) on the Fred Rocba (FREDR) system - the latest dated program execution observed in the prefetch set.","confidence":0.97,"evidence_type":"prefetch_execution","source_artifact":"evidence/extracted/Prefetch/FTK_IMAGER.EXE-913F398E.pf","source_sha256":"1211cce623d6845d5e6e2a3c86a70177a3b33a24d06719bf2d458b6c7ae6d667","tool_name":"analyze_prefetch","tool_call_id":"TOOL-020","supporting_evidence_refs":["TOOL-020"],"contradicting_evidence_refs":[],"requires_human_review":false}
```

**(2) The tool execution it points to**, from `audit/tool_calls.jsonl`, `TOOL-020`. The `source_sha256`
matches (custody match), and the record carries start/end timestamps, status, backend, and the
structured-output path:

```json
{"tool_call_id":"TOOL-020","tool_name":"analyze_prefetch","source_artifact":"evidence/extracted/Prefetch/FTK_IMAGER.EXE-913F398E.pf","source_sha256":"1211cce623d6845d5e6e2a3c86a70177a3b33a24d06719bf2d458b6c7ae6d667","start_time_utc":"2026-06-15T07:05:40.036434Z","end_time_utc":"2026-06-15T07:05:40.038214Z","status":"success","backend":"real","tool_version":"0.1.0","structured_result_path":"results/TOOL-020.structured.json","raw_output_path":null,"error_code":null}
```

**(3) The dispatch that ran it**, from `audit/agent_calls.jsonl`, `AGENT-007`. This is the **live Claude
agent** (`claude_headless`) - it investigated TASK-007 and emitted the anchored claim above. Each
dispatch is one line, recording profile/adapter/backend, attempt, and start/end times:

```json
{"agent_call_id":"AGENT-007","task_id":"TASK-007","profile":"claude_headless","adapter":"claude_headless","backend":"claude_headless","attempt":1,"start_time_utc":"2026-06-15T07:05:08.847087Z","end_time_utc":"2026-06-15T07:08:59.321671Z","status":"success","fell_back_from":null}
```

**(4) The critic verdict**, from `audit/critic_verdicts.jsonl`, `VERDICT-008`. The deterministic Tier-1
critic - the sole promoter - accepted the task because every claim was evidence-anchored:

```json
{"verdict":"accepted","reasons":["all claims evidence-anchored"],"affected_claim_ids":[],"task_id":"TASK-007","verdict_id":"VERDICT-008","decided_utc":"2026-06-15T08:08:47.723410Z"}
```

**(5) The orchestration events**, from `audit/orchestration_events.jsonl` - every dispatch and state
transition is timestamped, and transitions carry `duration_ms`:

```json
{"run_id": "RUN-20260615-064002", "task_id": "TASK-007", "profile": "claude_headless", "adapter": "claude_headless", "status": "success", "event": "task_dispatched", "level": "info", "timestamp": "2026-06-15T07:08:59.322814Z"}
{"run_id": "RUN-20260615-064002", "from_state": "report", "to_state": "done", "iteration": 2, "duration_ms": 186, "event": "transition", "level": "info", "timestamp": "2026-06-15T08:37:01.571037Z"}
```

**Chain proven:** `TASK-007-A1-CLAIM-001` -> `TOOL-020` (matching `source_sha256 1211cce6…`) ->
`AGENT-007` (live `claude_headless` dispatch) -> `VERDICT-008` (critic accepted) -> the timestamped
events. All real, all the live agent.

### The custody anchor (disk extraction)

The headline disk finding traces the same way to the Sleuth Kit extraction (`TASK-001`, the heavy tool
that runs on the floor), anchored to the original image's SHA-256 `f2eb856d…` - the sealed manifest
hash, so this is chain of custody back to the raw `.E01`:

```json
{"tool_call_id":"TOOL-001","tool_name":"extract_artifacts_from_image","source_artifact":"rocba-cdrive.e01","source_sha256":"f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67","status":"success","backend":"sift_lane","tool_version":"0.1.0","structured_result_path":"results/TOOL-001.structured.json"}
```

## 2. The self-correction arc (the critic catching the live agent)

The most important thing in these ledgers is where the governance disagreed with the LLM. The agent
**could not anchor** the `$MFT` / USN-journal tasks. Watch TASK-016 across the ledgers:

**Attempt 1** - the live agent runs but returns no parseable anchored claims, so the dispatch is
recorded `retry_required` (not "success", not faked):

```json
{"agent_call_id":"AGENT-016","task_id":"TASK-016","profile":"claude_headless","adapter":"claude_headless","backend":"claude_headless","attempt":1,"start_time_utc":"2026-06-15T07:45:15.703599Z","end_time_utc":"2026-06-15T07:52:57.745116Z","status":"retry_required","fell_back_from":null}
```

**The critic forces a retry** with tightened criteria, written to `audit/retries.jsonl` and injected
into the next prompt:

```json
{"retry_id":"RETRY-001","task_id":"TASK-016","from_attempt":1,"to_attempt":2,"cause":"critic_retry","tightened_criteria":["Every claim MUST include a tool_call_id and source_sha256 bound to a real tool call.","Do not assert beyond the tool rows; no claim may exceed the evidence the tool returned.","Do not assign final severity; report observations only."],"decided_utc":"2026-06-15T08:08:50.554653Z"}
```

**Attempt 2** - still no anchored claims; the dispatch errors, the task is escalated and **quarantined**
(its claims are never promoted):

```json
{"agent_call_id":"AGENT-026","task_id":"TASK-016","profile":"claude_headless","adapter":"claude_headless","backend":"claude_headless","attempt":2,"start_time_utc":"2026-06-15T08:08:50.665516Z","end_time_utc":"2026-06-15T08:18:50.693376Z","status":"error","fell_back_from":null}
```

This is genuine, un-staged self-correction: the live agent failed on the largest tabular outputs
(`parse_mft_filesystem` and `parse_usnjrnl` ran, but produced no promoted findings), and the
deterministic engine refused to emit unsupported claims rather than guess. The honest cost is recorded,
not hidden. Across the run: **3 retries, 8 escalations, 3 human-review gates, 7 quarantined tasks, 5
contradictions, 14 confidence downgrades.**

## 3. Evidence-as-hostile, logged not executed

The injection scanner flags evidence strings that look like instructions and writes them to
`claims/injection_alerts.jsonl`. They are logged only, never executed. This run flagged 11,628 such
strings - the great majority base64-like SHA-256 hash fragments in tool output (a fail-safe over-trigger
we disclose honestly):

```json
{"alert_id":"ALERT-001","source":"tool_result","signature":"base64_blob","snippet":"28-4\", \"derived_path\": \"evidence/extracted/Prefetch/ACCOUNTSCONTROLHOST.EXE-00EAE375.pf\", \"sha2","detected_utc":"2026-06-15T06:49:12.674210Z","task_id":"TOOL-001","source_artifact":"rocba-cdrive.e01","requires_human_review":true}
```

## 4. Trace any finding yourself (the commands)

On the workstation, against the same run dir (`$RUN`):

```bash
uv run siftmesh claims show  "$RUN" TASK-007-A1-CLAIM-001   # the finding + its anchor
uv run siftmesh audit tail   "$RUN" --ledger tool-calls     # every tool execution, timestamped
uv run siftmesh audit tail   "$RUN" --ledger agent-calls    # every dispatch (attempts, times)
uv run siftmesh replay       "$RUN" --html                  # the whole run reconstructed from JSONL
```

Or read the raw ledgers directly: `claims/claim_ledger.jsonl`, `audit/tool_calls.jsonl`,
`audit/agent_calls.jsonl`, `audit/critic_verdicts.jsonl`, `audit/orchestration_events.jsonl`. Live,
every command also streams a tagged, per-task, %-complete log to the terminal by default
(`[info] [agent] [tool_log] [alert] [result] [tasks]`; pass `--quiet` to silence).

## 5. On token usage (honest)

This run used the live Claude executor (`claude_headless`): the agent attempts are in
`audit/agent_calls.jsonl` (with attempt numbers and start/end times) and the raw envelopes are written to
`results/*.agent_raw.json` on the box. **Per-agent LLM token counts are not yet recorded** in the audit
trail - a known gap. `audit/token_budget.jsonl` records the engine's profile-routing decisions (the
escalation policy), not LLM tokens:

```json
{"base_profile": "deterministic_executor", "selected_profile": "deterministic_executor", "escalated": false, "reason": "critic_retry", "recorded_utc": "2026-06-15T08:08:50.551647Z"}
```

The deterministic floor remains the reproducible, no-keys baseline; the live agent is the opt-in hero.

---

*Provenance: every record above is from the committed run ledgers
([`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002)). Findings narrative:
[`findings_rocba.md`](findings_rocba.md); accuracy: [`accuracy_report.md`](accuracy_report.md); dataset +
reproduce: [`dataset_documentation.md`](dataset_documentation.md).*

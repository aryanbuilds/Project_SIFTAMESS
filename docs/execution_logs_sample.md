# Agent Execution Logs — annotated sample

Hackathon criterion 5 (audit trail): every SIFTMesh action is a structured, timestamped JSONL record
under `case_runs/RUN-*/audit/` and `…/claims/`. The whole run is **replayable** from these files
(`siftmesh replay RUN`). This walkthrough annotates the real ledgers of the golden regression run
(`tests/golden/recorded_run/RUN-GOLDEN/`) — a §2B deterministic-floor run over committed public
fixtures (no keys, no live agent). The `examples/demo_case` produces the same shape.

All timestamps are UTC. Records are append-only and validated against the Pydantic schemas before
write (a corrupt line raises, never silently skips).

## 1. Orchestration events — the state machine (`audit/orchestration_events.jsonl`)

```json
{"run_id":"RUN-20260610-071122","event":"plan_started","review_only":false,"timestamp":"2026-06-10T07:11:22.975665Z"}
{"run_id":"RUN-20260610-071122","event":"plan_complete","context_files":5,"task_count":4,"timestamp":"2026-06-10T07:11:22.993801Z"}
```

The deterministic planner read **only** the sealed manifest metadata (privilege separation — it never
touches evidence bytes) and emitted 4 task contracts + 5 context files.

## 2. Agent calls — who executed each task (`audit/agent_calls.jsonl`)

```json
{"agent_call_id":"AGENT-001","task_id":"TASK-001","profile":"deterministic_executor","adapter":"deterministic_executor","backend":"real","attempt":1,"start_time_utc":"2026-06-10T07:11:23.010811Z","end_time_utc":"2026-06-10T07:11:23.018472Z","status":"success","fell_back_from":null}
```

Tier **T0** (deterministic floor). `fell_back_from` records when a requested live agent was
unavailable and the registry walked to the floor (here: none). A live run shows `attempt: 1` then
`attempt: 2` when the critic drives a retry (the self-correction loop).

## 3. Tool calls — real backends with full provenance (`audit/tool_calls.jsonl`)

```json
{"tool_call_id":"TOOL-001","tool_name":"analyze_prefetch","source_artifact":"CMD.EXE-89305D47.pf","source_sha256":"6127d820b031cac7…edcd0","status":"success","backend":"real","tool_version":"0.1.0","structured_result_path":"results/TOOL-001.structured.json","start_time_utc":"2026-06-10T07:11:23.011728Z","end_time_utc":"2026-06-10T07:11:23.012578Z","error_code":null}
{"tool_call_id":"TOOL-002","tool_name":"extract_registry_run_keys","source_artifact":"NTUSER.DAT","source_sha256":"6a38fcea92411396…cd439","status":"success","backend":"real",...}
```

Each call records `source_sha256` (the chain-of-custody anchor), `backend` (`real`/`sift_lane`),
`tool_version`, UTC start/end, and the structured-result path. A failed real tool is logged honestly
(`status:"error"`, `error_code`), never faked.

## 4. Claim ledger — anchored findings (`claims/claim_ledger.jsonl`)

Every promoted claim carries the provenance that lets a reviewer re-derive it:

```json
{"claim_id":"TASK-003-CLAIM-002","status":"confirmed","claim":"Security EventID 4625 (failed logon) observed","confidence":0.9,"source_artifact":"Security.evtx","source_sha256":"50c87926d2dfed97…13456","tool_name":"parse_evtx_security","tool_call_id":"TOOL-003","supporting_evidence_refs":["TOOL-003"]}
```

A claim **without** `tool_call_id` + `source_sha256` cannot be a `confirmed`/`inferred` fact (schema
validator + critic) — it is confined to Appendix B of the report. That is the hallucination firewall.

## 5. Critic verdicts — the governance gate (`audit/critic_verdicts.jsonl`)

```json
{"verdict_id":"VERDICT-001","task_id":"TASK-001","verdict":"accepted","reasons":["all claims evidence-anchored"],"affected_claim_ids":[],"decided_utc":"2026-06-10T07:11:23.106790Z"}
{"verdict_id":"VERDICT-002","task_id":"TASK-002","verdict":"accepted","reasons":["all claims evidence-anchored"],...}
```

The deterministic Tier-1 critic is the **sole promoter**. On a live run, an under-anchored claim gets
`retry_required` here; its rejection reasons are injected into the retry prompt, the agent revises
against the real tool output, and the corrected claim is accepted on attempt 2. Claim IDs are
attempt-scoped (`…-A1-…` vs `…-A2-…`) so the correction never overwrites the rejection. See
`docs/demo_script.md` for the narrated self-correction sequence.

## 6. Reproduce / replay

```bash
bash examples/demo_case/run_demo.sh                 # generate your own ledgers (no keys)
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
uv run siftmesh replay "$RUN"                        # text replay of the audit timeline
uv run siftmesh replay "$RUN" --html                # self-contained HTML replay
uv run siftmesh audit tail "$RUN" --ledger tool-calls
```

The byte-determinism of the report generators is golden-tested
(`tests/golden/` — render-from-recorded == committed bodies, no LLM at report time).

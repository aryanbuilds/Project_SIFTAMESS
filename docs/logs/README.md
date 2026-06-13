# Agent execution logs — the real ROCBA runs (full ledgers)

These are the **complete, structured execution logs** of SIFTMesh's two real runs against the ROCBA
evidence on the SANS SIFT workstation — committed so a judge can inspect and **trace any finding back
to the exact tool execution** without the workstation. A guided walkthrough of one trace is in
[`../execution_logs_sample.md`](../execution_logs_sample.md).

| Bundle | Run | Evidence (sealed) |
|---|---|---|
| `rocba-disk-RUN-20260612-163324/` | disk image | `rocba-cdrive.e01` · sha256 `f2eb856d…` · 634 claims |
| `rocba-memory-RUN-20260612-082630/` | memory capture | `Rocba-Memory.raw` · sha256 `eb33bdf6…` · Volatility 3, 6 plugins |

## What's in each bundle

- **`audit/`** — `orchestration_events.jsonl` (every state transition, timestamped, with `duration_ms`),
  `tool_calls.jsonl` (every real tool execution: `tool_call_id`, `source_sha256`, start/end times,
  status, backend), `agent_calls.jsonl` (every dispatch: profile/adapter, attempt, times),
  `critic_verdicts.jsonl`, `retries.jsonl`, `followups.jsonl`, `token_budget.jsonl`.
- **`claims/`** — `claim_ledger.jsonl` (the promoted findings, each citing `tool_call_id` +
  `source_sha256`), `unsupported_claims.jsonl`, `contradiction_ledger.jsonl`,
  `confidence_changes.jsonl`, `injection_alerts.jsonl`.
- **`reports/`** — `final_report.md`, `accuracy_report.md`, `dataset_documentation.md`,
  `architecture_notes.md`, and `replay.html` (the whole run reconstructed).
- **`context/`** — the case brief, context pack, investigation plan, tool map, assumptions.
- **`tasks/`** — every per-task contract (`TASK-*.yaml`).
- **`evidence/`** — the chain-of-custody ledgers only: `evidence_manifest.json`, `hashes.sha256`,
  `custody_log.jsonl`, `readonly_mounts.json`, `derived_artifacts.json`.
- **`run_state.json`** — the final durable state-machine snapshot.

## What's intentionally NOT here (derived bulk, not "logs")

To keep the repo lean, three large *derived* trees stay on the workstation (they're outputs the ledgers
already reference, not the audit trail itself):

- `results/` — the full per-tool structured outputs (≈407 MB on disk; each `tool_calls.jsonl` row points
  to its `structured_result_path` there).
- `evidence/extracted/` — the carved artifacts (≈4.5 GB).
- `super_timeline/` — the Plaso `.plaso` + psort output (≈11 GB).

The **raw evidence images themselves are never committed** (chain of custody; they're held read-only on
the box). `injection_alerts.jsonl` contains *truncated* evidence-derived string fragments — they were
**logged, never executed**.

## Trace any finding → its tool execution

In `rocba-disk-RUN-20260612-163324/`:

1. Open `reports/final_report.md` → pick a finding.
2. Find its claim in `claims/claim_ledger.jsonl` → note `tool_call_id` + `source_sha256`.
3. Match that `tool_call_id` in `audit/tool_calls.jsonl` → the exact execution, its `source_sha256`
   (custody match), and start/end timestamps.
4. `audit/agent_calls.jsonl` shows the dispatch (attempt, times); `audit/orchestration_events.jsonl`
   shows where it sits in the timeline.

On the workstation the same is one command: `uv run siftmesh replay <run> --html`.

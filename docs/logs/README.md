# Agent execution logs: the real ROCBA run (full ledgers)

This is the **complete, structured execution log** of SIFTMesh's real run against the ROCBA evidence on
the SANS SIFT workstation. It is a **live Claude-agent run**: 26 of 28 dispatches were the sandboxed
`claude_headless` executor; the only 2 deterministic dispatches are the heavy tools (disk extraction and
memory triage), which are pinned to the floor by policy. Disk and memory were handled in **one
autonomous pass** (the memory `.zip` was auto-decompressed and re-ingested mid-run). We committed the
ledgers so a judge can inspect any finding and trace it back to the exact tool execution without the
workstation. See a guided walkthrough of one trace in
[`../execution_logs_sample.md`](../execution_logs_sample.md).

| Bundle | Run | Evidence (sealed) | Result |
|---|---|---|---|
| `rocba-live-RUN-20260615-064002/` | disk + memory, live Claude agent | `rocba-cdrive.e01` (sha256 `f2eb856d...`, 23.7 GB) + `Rocba-Memory.raw` (sha256 `eb33bdf6...`) | 223 claims, all anchored; 0 unsupported |

## What this run shows (live self-correction, in the ledgers)

- **Live executor:** `audit/agent_calls.jsonl` - 26 `claude_headless` dispatches, 2 `deterministic_executor`
  (the tier-floor-forced heavy tools), 0 fall-backs.
- **Critic actually fired:** `audit/critic_verdicts.jsonl` - 51 verdicts: 34 accepted, 2
  accepted_with_downgrade, 4 retry_required, 8 escalation_required, 3 human_review_required (not a flat
  all-accepted pass).
- **Genuine retries:** `audit/retries.jsonl` - 3 critic-driven retries (TASK-016/017/019) with the
  tightened criteria written back into the contract.
- **Honest failure:** the live agent could not anchor the `$MFT` / USN-journal tasks (TASK-016/017/019);
  attempt 1 produced no parseable anchored claims, the critic forced a retry, attempt 2 still failed, and
  the tasks were escalated and **quarantined** - so those tools ran (`parse_mft_filesystem` x22,
  `parse_usnjrnl` x15) but produced **no promoted claims**. The governance refused to emit unsupported
  findings rather than fabricate them.
- **Contradictions + downgrades:** `claims/contradiction_ledger.jsonl` (5) and
  `claims/confidence_changes.jsonl` (14) - the critic caught and downgraded over-broad memory claims.
- **Dynamic re-planning:** `audit/followups.jsonl` - 24 derived-gap follow-up tasks generated mid-run.

## What's in the bundle

- **`audit/`**: `orchestration_events.jsonl` (every state transition, timestamped, with `duration_ms`),
  `tool_calls.jsonl` (every real tool execution: `tool_call_id`, `source_sha256`, start/end times,
  status, backend; 245 calls, 244 success + 1 honest parse error), `agent_calls.jsonl` (every dispatch:
  profile/adapter/backend, attempt, times), `critic_verdicts.jsonl`, `retries.jsonl`, `followups.jsonl`,
  `token_budget.jsonl`.
- **`claims/`**: `claim_ledger.jsonl` (223 promoted findings, each citing `tool_call_id` +
  `source_sha256`), `contradiction_ledger.jsonl`, `confidence_changes.jsonl`, `injection_alerts.jsonl`.
- **`reports/`**: `final_report.md`, `accuracy_report.md`, `dataset_documentation.md`,
  `architecture_notes.md`, and `replay.html` (the whole run reconstructed).
- **`context/`**: the case brief, context pack, investigation plan, tool map, assumptions, the trusted
  incident brief, and the run-scoped MCP config.
- **`tasks/`**: every per-task contract (`TASK-*.yaml`).
- **`evidence/`**: the chain-of-custody ledgers only: `evidence_manifest.json`, `hashes.sha256`,
  `custody_log.jsonl`, `readonly_mounts.json`, `derived_artifacts.json`.
- **`run_state.json`**: the final durable state-machine snapshot (state=done, iteration 2/3).

## What's intentionally NOT here (derived bulk, not "logs")

To keep the repo lean, large *derived* trees stay on the workstation. They are outputs the ledgers
already reference, not the audit trail itself:

- `results/`: the full per-tool structured outputs (each `tool_calls.jsonl` row points to its
  `structured_result_path` there).
- `evidence/extracted/`: the carved artifacts (the disk extraction + decompressed memory image).

We never commit the raw evidence images themselves (chain of custody; they stay read-only on the box).
`injection_alerts.jsonl` contains *truncated* evidence-derived string fragments (11,628 alerts, the
great majority base64-like hash fragments over-flagged by the spotlight scanner). We **logged** them and
never executed them.

## Trace any finding -> its tool execution

1. Open `reports/final_report.md` -> pick a finding.
2. Find its claim in `claims/claim_ledger.jsonl` -> note `tool_call_id` + `source_sha256`.
3. Match that `tool_call_id` in `audit/tool_calls.jsonl` -> the exact execution, its `source_sha256`
   (custody match), and start/end timestamps.
4. `audit/agent_calls.jsonl` shows the dispatch (which agent, attempt, times);
   `audit/orchestration_events.jsonl` places it in the timeline.

On the workstation the same is one command: `uv run siftmesh replay <run> --html`.

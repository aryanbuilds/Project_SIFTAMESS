# Submission index: the 8 required components

Every required component maps to its artifact. All results, metrics, and logs come from the **real ROCBA
investigation** - one live Claude-agent run, `RUN-20260615-064002`, disk plus memory in a single
autonomous pass on the SANS SIFT workstation, not a demo fixture.

| # | Component | Where it lives | Status |
|---|---|---|---|
| 1 | **Code repository + license** | Public GitHub repo · [`LICENSE`](../LICENSE) (Apache-2.0) · [`README.md`](../README.md) | ✅ |
| 2 | **Demo video (≤5 min, narrated, real data + self-correction)** | <https://youtu.be/oVX59SM6AZQ> | ✅ |
| 3 | **Architecture diagram (pattern + boundaries + prompt-vs-architectural)** | [`architecture.md`](architecture.md) · [`threat_model.md`](threat_model.md) · [`diagrams/security_boundaries.mmd`](diagrams/security_boundaries.mmd) | ✅ |
| 4 | **Written project description (Devpost story)** | [`project_story.md`](project_story.md) | ✅ |
| 5 | **Dataset documentation** | [`dataset_documentation.md`](dataset_documentation.md) (sealed ROCBA hashes, source, reproduce) | ✅ |
| 6 | **Accuracy report (+ evidence integrity, spoliation)** | [`accuracy_report.md`](accuracy_report.md) · [`evidence_integrity.md`](evidence_integrity.md) | ✅ |
| 7 | **Try-it-out instructions** | [`try_it_out.md`](try_it_out.md) · [`../RUNBOOK.md`](../RUNBOOK.md) (real ROCBA flow) | ✅ |
| 8 | **Agent execution logs (timestamped, finding→tool traceable)** | **full committed ledgers:** [`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002/) (the live ROCBA run) · guided trace: [`execution_logs_sample.md`](execution_logs_sample.md) | ✅ |

## Headline real-evidence results (ROCBA)

- **One live run** `RUN-20260615-064002` (mode `auto`, iteration 2 of 3, final state `done`) executed against
  `rocba-cdrive.e01`, sha `f2eb856d…` (~23.7 GB) and `Rocba-Memory.raw`, sha `eb33bdf6…` (auto-decompressed
  from `Rocba-Memory.zip`, sha `32cec940…`, ~5.7 GB). The executor was a **live Claude agent** via
  `claude_headless` (28 agent calls = 26 live + 2 deterministic-floor for the two heavy tools); `opencode`
  ran as an advisory Tier-2 judge that never promotes.
- It promoted **223 claims** (182 confirmed / 41 inferred), with **0 unsupported and 0 contradicted-status** -
  and **all 223 anchored** (every claim carries a `tool_call_id` and `source_sha256`). 13 distinct typed tools
  fired across 245 tool calls (244 success, 1 honestly-logged prefetch parse error); the critic issued 51
  verdicts and 14 confidence downgrades. **11,628 injection alerts** were logged (never executed) - candidly,
  11,625 of those are an over-trigger on base64-like hash fragments in tool output (fail-safe, noisy).
- **Volatility 3** triage recovered 2,186 processes and 430 network endpoints; malfind RWX regions in system
  processes were flagged for review, not concluded malicious (some downgraded/contradicted by the critic).
- **Self-correction (real, not staged):** the live agent failed to anchor the `$MFT` and USN-journal parses
  (TASK-016/017/019). The deterministic critic forced retries (RETRY-001/002/003); attempt 2 still failed, so
  those tasks were escalated and quarantined - so `parse_mft_filesystem` and `parse_usnjrnl` **ran but produced
  no promoted claims** rather than emit unsupported ones. The Plaso super-timeline was not run this pass.
- **Answers the brief:** stolen STARK-RESEARCH-LABS IP was staged to a removable `F:` volume and mirrored to a
  personal Google Drive `G:` (Airwolf, KITT, Vibrainium, an SRL email export `SRL-EMAIL-EXPORT.pst`), with
  SDelete, `vssadmin`, and `wevtutil` used for cleanup and an `FTK IMAGER.EXE` execution at
  2020-11-16T02:43:57Z. Read the full narrative in [`findings_rocba.md`](findings_rocba.md); the end-to-end
  operation log lives in [`complete_operation.md`](complete_operation.md).

## At-a-glance integrity posture (for a quick trust read)

- **Pattern:** "LLM proposes, code decides." An autonomous agent runs under a deterministic governance FSM.
- **Architectural (code-enforced) guardrails:** read-only evidence with a SHA-256 seal, the 19-tool MCP
  allowlist (no raw shell), the `safe_write_path` run-dir write-jail, the critic as sole promoter, and the
  injection ledger. These hold **regardless of which agent runs**. See [`threat_model.md`](threat_model.md) §1, §4 to 5.
- **Prompt-based (advisory) guardrails:** the per-harness sandbox flags such as Claude
  `--disallowedTools` / `--permission-mode dontAsk`. We mark these as the inner, weaker
  layer that the architectural layer does not depend on.

## Notes

- We commit the **full execution-log ledgers** for the live run under
  [`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002/) (audit, claims, reports,
  context, tasks, custody). Only the heavy derived bulk stays off-repo: per-tool `results/` and the carved
  `evidence/extracted/`, along with the raw evidence images. Size and chain of custody drive that choice
  (CLAUDE.md §2B).
- `examples/demo_case/` and `tests/golden/` exist purely as **test infrastructure** for golden-determinism
  and CI without licensed evidence. They are **not** the submission's results.

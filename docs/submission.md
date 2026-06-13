# Submission index: the 8 required components

Every required component maps to its artifact. All results, metrics, and logs come from the **real ROCBA
investigation** (disk `RUN-20260612-163324` plus memory `RUN-20260612-082630`) on the SANS SIFT
workstation, not a demo fixture.

| # | Component | Where it lives | Status |
|---|---|---|---|
| 1 | **Code repository + license** | Public GitHub repo · [`LICENSE`](../LICENSE) (Apache-2.0) · [`README.md`](../README.md) | ✅ |
| 2 | **Demo video (≤5 min, narrated, real data + self-correction)** | **Link: _TODO - paste the recorded URL here and in the README_** · shot list: [`demo_script.md`](demo_script.md) | ⏳ record |
| 3 | **Architecture diagram (pattern + boundaries + prompt-vs-architectural)** | [`architecture.md`](architecture.md) · [`threat_model.md`](threat_model.md) · [`diagrams/security_boundaries.mmd`](diagrams/security_boundaries.mmd) | ✅ |
| 4 | **Written project description (Devpost story)** | [`project_story.md`](project_story.md) | ✅ |
| 5 | **Dataset documentation** | [`dataset_documentation.md`](dataset_documentation.md) (sealed ROCBA hashes, source, reproduce) | ✅ |
| 6 | **Accuracy report (+ evidence integrity, spoliation)** | [`accuracy_report.md`](accuracy_report.md) · [`evidence_integrity.md`](evidence_integrity.md) | ✅ |
| 7 | **Try-it-out instructions** | [`try_it_out.md`](try_it_out.md) · [`../RUNBOOK.md`](../RUNBOOK.md) (real ROCBA flow) | ✅ |
| 8 | **Agent execution logs (timestamped, finding→tool traceable)** | **full committed ledgers:** [`logs/`](logs/) (both real ROCBA runs) · guided trace: [`execution_logs_sample.md`](execution_logs_sample.md) | ✅ |

## Headline real-evidence results (ROCBA)

- **Disk** `RUN-20260612-163324` ran against `rocba-cdrive.e01`, sha `f2eb856d…` (23.7 GB). It produced
  **634 claims** (220 confirmed / 414 inferred), with **0 unsupported and 0 contradictions**. 19 tools fired,
  3,949 injection strings were flagged (logged, never executed), and the Plaso super-timeline holds 5.7 M events.
- **Memory** `RUN-20260612-082630` ran against `Rocba-Memory.raw`, sha `eb33bdf6…` (19 GB). Volatility 3 ran
  6 plugins with 0 failures, recovering 2,186 processes and 430 network endpoints.
- **Answers the brief:** stolen ADAMANTIUM research went to a personal Google Drive plus USB exfil, and
  SDelete with 47,966 USN deletions handled cleanup. Read the full narrative in
  [`findings_rocba.md`](findings_rocba.md); the end-to-end operation log lives in
  [`complete_operation.md`](complete_operation.md).

## At-a-glance integrity posture (for a quick trust read)

- **Pattern:** "LLM proposes, code decides." An autonomous agent runs under a deterministic governance FSM.
- **Architectural (code-enforced) guardrails:** read-only evidence with a SHA-256 seal, the 19-tool MCP
  allowlist (no raw shell), the `safe_write_path` run-dir write-jail, the critic as sole promoter, and the
  injection ledger. These hold **regardless of which agent runs**. See [`threat_model.md`](threat_model.md) §1, §4 to 5.
- **Prompt-based (advisory) guardrails:** the per-harness sandbox flags such as Claude
  `--disallowedTools` / `--permission-mode dontAsk`. We mark these as the inner, weaker
  layer that the architectural layer does not depend on.

## Notes

- We commit the **full execution-log ledgers** for both real runs under [`logs/`](logs/) (audit,
  claims, reports, context, tasks, custody). Only the heavy derived bulk stays off-repo: per-tool `results/`, the
  carved `evidence/extracted/`, and the 11 GB Plaso `super_timeline/`, along with the raw evidence images.
  Size and chain of custody drive that choice (CLAUDE.md §2B).
- `examples/demo_case/` and `tests/golden/` exist purely as **test infrastructure** for golden-determinism
  and CI without licensed evidence. They are **not** the submission's results.

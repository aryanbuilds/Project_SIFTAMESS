# Judge runbook

A fast path for evaluators to verify SIFTMesh against the hackathon criteria, and to inspect the
**real ROCBA** investigation it ran on the SANS SIFT workstation.

## 0. Setup (≈2 min)

```bash
git clone <repo-url> siftmesh && cd siftmesh
uv sync --all-extras
uv run siftmesh doctor          # host health (fail-closed); doctor --agents shows the safety tiers
uv run pytest -q                # full suite (no evidence needed) - confirms the build is healthy
```

## 1. The real run (ROCBA, on the workstation)

With the ROCBA evidence read-only on the box (`~/projects/data/`), one command runs the whole case:

```bash
SIFTMESH_ENABLE_SUPER_TIMELINE=true \
uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx --auto --max-agent-tasks 400 --max-iterations 6
RUN=$(ls -dt ./case_rocba/case_runs/RUN-* | head -1)
```

This command hashes and seals, plans, extracts (Sleuth Kit), re-ingests the carved artifacts, parses
(evtx/registry/prefetch/MFT/USN/Plaso), critiques, then reports. For the full staged, memory, and
portions flows, see [`../RUNBOOK.md`](../RUNBOOK.md). Run dirs stay off-repo per CLAUDE §2B, so the
committed real-evidence record lives in [`findings_rocba.md`](findings_rocba.md),
[`accuracy_report.md`](accuracy_report.md),
[`execution_logs_sample.md`](execution_logs_sample.md), and
[`complete_operation.md`](complete_operation.md).

## 2. Criteria map: what to look at

| # | Criterion | Where to verify |
| --- | --- | --- |
| 1 | **Autonomous execution / self-correction** | live run §4; the deterministic FSM loop in `siftmesh_core/orchestrator/` |
| 2 | **IR accuracy / no hallucination** | real ROCBA results in `docs/findings_rocba.md` + `docs/accuracy_report.md`; in any run `"$RUN/claims/claim_ledger.jsonl"` - every claim cites `tool_call_id`+`source_sha256`; unanchored claims are confined to Appendix B of `reports/final_report.md` |
| 3 | **Breadth & depth** | the 19-tool allowlist (`siftmesh doctor`), real backends (evtx/regipy/pyscca/mft + browser/LNK/shellbag/Amcache/USN parsers + Sleuth Kit/Volatility/Plaso for disk/memory/super-timeline in `RUNBOOK.md`) |
| 4 | **Constraint implementation (bypass-tested)** | `docs/threat_model.md`; `uv run pytest tests/EPIC_L_TESTS -q` (80+ effect-asserting bypass tests); agent **safety tiers** in `docs/architecture.md §2a` |
| 5 | **Audit trail quality** | `"$RUN/audit/*.jsonl"` + `uv run siftmesh replay "$RUN"` (every transition is timestamped JSONL); the traceable excerpt in `docs/execution_logs_sample.md`; chain of custody in `docs/evidence_integrity.md` |
| 6 | **Usability & docs** | `docs/try_it_out.md`, this runbook, `README.md`, the cockpit `uv run siftmesh tui "$RUN"` |

## 3. Inspect a run

```bash
cat "$RUN/reports/final_report.md"          # evidence-backed findings + ATT&CK + appendices
cat "$RUN/reports/accuracy_report.md"       # honest self-assessment (no ground-truth key on ROCBA)
cat "$RUN/audit/critic_verdicts.jsonl"      # one verdict per task (the governance gate)
uv run siftmesh audit tail "$RUN" --ledger tool-calls   # every tool execution, timestamped
uv run siftmesh replay "$RUN" --html        # self-contained HTML replay of the whole run
uv run siftmesh tui "$RUN"                   # live cockpit (optional `tui` extra)
```

`siftmesh tui` with no argument opens the minimal home. Press **`o`** for onboarding, which gives you
an **Agents** tab and a **Tier-2 judge** tab. SIFTMesh validates LiteLLM keys and saves them to a
600-perm `~/.config/siftmesh/.env`, never to the committed config.

## 4. See the live self-correction hero (optional)

Claude is the constrained (tier T1) executor. Add auth, then one flag, against the real ROCBA evidence:

```bash
claude setup-token                                   # or export ANTHROPIC_API_KEY=…
uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx --agent claude --auto-human-loop --max-iterations 2
```

Watch the loop in the new run's ledgers: `audit/agent_calls.jsonl` (attempt 1 → 2),
`audit/critic_verdicts.jsonl` (`retry_required` → `accepted`), `claims/unsupported_claims.jsonl` (the
rejected attempt-1 over-claim), then `claims/claim_ledger.jsonl` (the corrected, anchored claim).

## 5. Honesty notes (please read)

- **Tiers, not theatre.** `siftmesh agents list` labels each agent T0 to T3. Only Claude reaches the
  typed tools through the strict-MCP boundary (T1). opencode/gemini/codex are honestly labelled
  unconstrained opt-ins (T2). LiteLLM is advisory-only (T3, tool-less judge). Tiers never gate
  dispatch. They make the containment posture visible.
- **Real-only.** No mock tool backends; a missing backend fails closed, never fakes output. The
  results in `docs/` come from the real ROCBA disk and memory runs, not a demo fixture.
- **Run dirs are off-repo** (CLAUDE §2B): the `docs/` set is the curated, verifiable record, and the
  maintainer can show the complete ledgers live on the workstation. The full committed ledgers for
  both runs also sit in `docs/logs/rocba-disk-RUN-20260612-163324/` and
  `docs/logs/rocba-memory-RUN-20260612-082630/` for direct inspection.
- **Not court-ready.** SIFTMesh is a triage accelerator, and the final report states this limitation.

## 6. Run the test suite (optional)

```bash
uv run pytest -q                      # full suite (1 maintainer-gated live e2e is skipped without keys)
uv run pytest tests/EPIC_L_TESTS -q   # just the security bypass suite
```

# Judge runbook

A fast, reproducible path for evaluators to verify SIFTMesh against the hackathon criteria - with
**no API keys** (deterministic floor) and an optional one-flag live run.

## 0. Setup (≈2 min)

```bash
git clone <repo-url> siftmesh && cd siftmesh
uv sync
uv run siftmesh doctor          # host health (fail-closed); doctor --agents shows the safety tiers
```

## 1. Run it against the provided evidence (step by step)

**Prerequisite:** the provided ROCBA evidence, read-only, at `~/projects/data/` (the ~23.7 GB disk
`rocba-cdrive.e01`, the memory `Rocba-Memory.zip`, and `ROCBA-BACKGROUND.pptx`). Pick a path by time:

| Path | What runs | Time | Needs |
| --- | --- | --- | --- |
| **A. Deterministic floor** | real forensic tools, no LLM executor | **~40-60 min** | nothing (no API keys) |
| **B. Live agent** | Claude investigates via the typed tools and self-corrects under the critic | **~2 h** | Claude auth |

**Path A - deterministic floor (no keys, reproducible):**

```bash
uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --auto --max-agent-tasks 400 --max-iterations 3
RUN=$(ls -dt ./case_rocba/case_runs/RUN-* | head -1); echo "RUN=$RUN"
```

**Path B - live Claude agent (the committed reference run):**

```bash
claude setup-token            # subscription login (or: export ANTHROPIC_API_KEY=…)

SIFTMESH_CAPS__MAX_PARALLEL_TASKS=6 uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --objective "What key projects did Fred Rocba have access to? What was stolen, where to, how, and when?" \
  --auto --agent claude --judge opencode --parallel \
  --max-agent-tasks 400 --max-iterations 2
RUN=$(ls -dt ./case_rocba/case_runs/RUN-* | head -1); echo "RUN=$RUN"
```

Both paths hash and seal the evidence, plan, extract (Sleuth Kit), re-ingest the carved artifacts,
parse (evtx/registry/prefetch/LNK/shellbags/USB/Amcache), critique, then report. `Ctrl-C` is safe;
resume with `uv run siftmesh resume <RUN>`. Path B is the command behind the committed bundle
[`logs/rocba-live-RUN-20260615-064002/`](https://github.com/aryanbuilds/Project_SIFTMESH/tree/mvp_phase_1/docs/logs/rocba-live-RUN-20260615-064002); inspect it directly
without a run (§3).

**No evidence on hand? A 60-second no-keys proof on a public fixture:**

```bash
bash examples/demo_case/run_demo.sh
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
```

This runs the full pipeline on the deterministic floor over a real Windows `Security.evtx`
(ground truth in `examples/demo_case/expected_findings.md`).

## 2. Criteria map - what to look at

| # | Criterion | Where to verify |
| --- | --- | --- |
| 1 | **Autonomous execution / self-correction** | live run §4; deterministic loop in `tests/golden/`; engine: `siftmesh_core/orchestrator/` |
| 2 | **IR accuracy / no hallucination** | real ROCBA results in `docs/findings_rocba.md` + `docs/accuracy_report.md`; in any run `"$RUN/claims/claim_ledger.jsonl"` - every claim cites `tool_call_id`+`source_sha256`; unanchored claims are confined to Appendix B of `reports/final_report.md` |
| 3 | **Breadth & depth** | the 19-tool allowlist (`siftmesh doctor`), real backends (evtx/regipy/pyscca/mft + Sleuthkit/Volatility for disk/memory in `RUNBOOK.md`) |
| 4 | **Constraint implementation (bypass-tested)** | `docs/threat_model.md`; `uv run pytest tests/EPIC_L_TESTS -q` (60 effect-asserting bypass tests); agent **safety tiers** in `docs/architecture.md §2a` |
| 5 | **Audit trail quality** | `"$RUN/audit/*.jsonl"` + `uv run siftmesh replay "$RUN"` (every transition is timestamped JSONL); chain of custody in `docs/evidence_integrity.md` |
| 6 | **Usability & docs** | this runbook, `README.md`, the cockpit `uv run siftmesh tui "$RUN"` |

## 3. Inspect a run

```bash
cat "$RUN/reports/final_report.md"          # evidence-backed findings + ATT&CK + appendices
cat "$RUN/reports/accuracy_report.md"       # diff vs expected_findings.md (this case ships ground truth)
cat "$RUN/audit/critic_verdicts.jsonl"      # one verdict per task (the governance gate)
uv run siftmesh replay "$RUN" --html        # self-contained HTML replay of the whole run
uv run siftmesh tui "$RUN"                   # live cockpit (optional `tui` extra)
```

`siftmesh tui` (no arg) opens the minimal home (recent runs + a centered *New run*). Press **`o`** for
onboarding: an **Agents** tab (which agents are ready, with one-click *Launch auth*) and a **Tier-2
judge** tab (pick a provider, log in or paste an API key - LiteLLM keys are validated and saved to a
600-perm `~/.config/siftmesh/.env`, never to the committed config).

## 4. See the live self-correction loop (optional)

Claude is the constrained (tier T1) executor. Add auth, then one flag:

```bash
claude setup-token                                   # or export ANTHROPIC_API_KEY=…
bash examples/demo_case/run_demo.sh --agent claude
```

Watch the loop in the new run's ledgers: `audit/agent_calls.jsonl` (attempt 1 → 2),
`audit/critic_verdicts.jsonl` (`retry_required` → `accepted`), `claims/unsupported_claims.jsonl` (the
rejected attempt-1 over-claim) → `claims/claim_ledger.jsonl` (the corrected, anchored claim).

## 5. Honesty notes (please read)

- **Tiers are informational, not gatekeeping.** `siftmesh agents list` labels each agent T0-T3.
  Only Claude reaches the typed tools through the strict-MCP boundary (T1); opencode/gemini/codex
  are unconstrained opt-ins (T2). LiteLLM is advisory-only (T3, tool-less judge).
- **Real-only.** No mock tool backends; a missing backend fails closed, never fakes output.
- **Real evidence is maintainer-gated** (CLAUDE §2B). The committed demo uses public test fixtures so
  you can reproduce everything; the full ROCBA disk/memory walkthrough is in `RUNBOOK.md`.
- **Not court-ready.** SIFTMesh is a triage accelerator; the final report states this limitation.

## 6. Run the test suite (optional)

```bash
uv run pytest -q          # full suite (1 maintainer-gated live e2e is skipped without keys)
uv run pytest tests/EPIC_L_TESTS -q   # just the security bypass suite
```

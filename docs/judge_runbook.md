# Judge runbook

A fast, reproducible path for evaluators to verify SIFTMesh against the hackathon criteria — with
**no API keys** (deterministic floor) and an optional one-flag live run.

## 0. Setup (≈2 min)

```bash
git clone <repo-url> siftmesh && cd siftmesh
uv sync
uv run siftmesh doctor          # host health (fail-closed); doctor --agents shows the safety tiers
```

## 1. The 60-second proof (no keys)

```bash
bash examples/demo_case/run_demo.sh
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
```

This runs the full pipeline (hash → plan → dispatch → real tools → claims → critic → report) on the
deterministic floor over a real Windows `Security.evtx`. Ground truth: `examples/demo_case/expected_findings.md`.

## 2. Criteria map — what to look at

| # | Criterion | Where to verify |
| --- | --- | --- |
| 1 | **Autonomous execution / self-correction** | live run §4; deterministic loop in `tests/golden/` + `docs/demo_script.md`; engine: `siftmesh_core/orchestrator/` |
| 2 | **IR accuracy / no hallucination** | `"$RUN/claims/claim_ledger.jsonl"` — every claim cites `tool_call_id`+`source_sha256`; unanchored claims are confined to Appendix B of `reports/final_report.md`; the run also generates `reports/accuracy_report.md` |
| 3 | **Breadth & depth** | the 10-tool allowlist (`siftmesh doctor`), real backends (evtx/regipy/pyscca/mft + Sleuthkit/Volatility for disk/memory in `RUNBOOK.md`) |
| 4 | **Constraint implementation (bypass-tested)** | `docs/threat_model.md`; `uv run pytest tests/EPIC_L_TESTS -q` (80+ effect-asserting bypass tests); agent **safety tiers** in `docs/architecture.md §2a` |
| 5 | **Audit trail quality** | `"$RUN/audit/*.jsonl"` + `uv run siftmesh replay "$RUN"` (every transition is timestamped JSONL); chain of custody in `docs/evidence_integrity.md` |
| 6 | **Usability & docs** | `docs/try_it_out.md`, this runbook, `README.md`, the cockpit `uv run siftmesh tui "$RUN"` |

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
judge** tab (pick a provider, log in or paste an API key — LiteLLM keys are validated and saved to a
600-perm `~/.config/siftmesh/.env`, never to the committed config).

## 4. See the live self-correction hero (optional)

Claude is the constrained (tier T1) executor. Add auth, then one flag:

```bash
claude setup-token                                   # or export ANTHROPIC_API_KEY=…
bash examples/demo_case/run_demo.sh --agent claude
```

Watch the loop in the new run's ledgers: `audit/agent_calls.jsonl` (attempt 1 → 2),
`audit/critic_verdicts.jsonl` (`retry_required` → `accepted`), `claims/unsupported_claims.jsonl` (the
rejected attempt-1 over-claim) → `claims/claim_ledger.jsonl` (the corrected, anchored claim). Narrated
step-by-step in `docs/demo_script.md`.

## 5. Honesty notes (please read)

- **Tiers, not theatre.** `siftmesh agents list` labels each agent T0–T3. Only Claude reaches the
  typed tools through the strict-MCP boundary (T1); opencode/gemini/codex are honestly labelled
  unconstrained opt-ins (T2). LiteLLM is advisory-only (T3, tool-less judge). Tiers never gate
  dispatch — they make the containment posture visible.
- **Real-only.** No mock tool backends; a missing backend fails closed, never fakes output.
- **Real evidence is maintainer-gated** (CLAUDE §2B). The committed demo uses public test fixtures so
  you can reproduce everything; the full ROCBA disk/memory walkthrough is in `RUNBOOK.md`.
- **Not court-ready.** SIFTMesh is a triage accelerator; the final report states this limitation.

## 6. Run the test suite (optional)

```bash
uv run pytest -q          # full suite (1 maintainer-gated live e2e is skipped without keys)
uv run pytest tests/EPIC_L_TESTS -q   # just the security bypass suite
```

# Demo script (≤5 minutes)

A shot list + narration for the submission video. Two acts: **(A)** the zero-keys deterministic proof
(reliable, always works), then **(B)** the live self-correction demo (Claude). If recording time is
tight, Act A alone satisfies criteria 2/4/5; add Act B for criterion 1.

Record a real terminal. Pre-stage the repo (`uv sync`) so the camera starts on the run.
Target ≈4:30 to leave buffer.

---

## 0:00 — Hook (15s)

> "SIFTMesh is a CLI-first, evidence-safe controller for autonomous DFIR. The LLM proposes; **code
> decides**. Every finding is anchored to a real tool call, every claim is critiqued by deterministic
> code, and the whole run replays from an audit log. And it's honest about agent risk — it labels
> every agent's safety tier."

Show: `uv run siftmesh agents list` — point at the **tier** column (T0 floor, T1 Claude, T2
opencode/gemini/codex, T3 judge) and the legend.

## 0:15 — Act A: zero-keys run (45s)

```bash
bash examples/demo_case/run_demo.sh
```

> "No API keys. This runs the deterministic real-tool floor — tier T0 — over a real Windows Security
> event log. It hashes the evidence, plans, dispatches, runs the real evtx parser, and reaches done."

Show the tail: `state: done`, and the printed run directory.

## 1:00 — Evidence safety + anchored claims (60s)

```bash
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUN/evidence/evidence_manifest.json"     # SHA-256 sealed at ingest
cat "$RUN/claims/claim_ledger.jsonl"           # every claim cites tool_call_id + source_sha256
```

> "Evidence is SHA-256 sealed and never modified — chain of custody. Each finding cites the exact tool
> call and the source hash. A claim *without* that anchor can't be accepted."

## 2:00 — The critic gate + report (45s)

```bash
cat "$RUN/audit/critic_verdicts.jsonl"         # the deterministic governance gate
sed -n '1,40p' "$RUN/reports/final_report.md"  # evidence-backed findings + ATT&CK
```

> "The deterministic critic is the only gate that can accept a finding. Here both tasks are accepted
> because every claim is anchored. Unsupported claims would be confined to Appendix B — never the
> findings body."

## 2:45 — Replay / audit (30s)

```bash
uv run siftmesh replay "$RUN"                  # the whole run reconstructed from JSONL
```

> "Every action is a timestamped JSONL record. The entire investigation replays — that's criterion 5,
> audit-trail quality."

(Optional B-roll: `uv run siftmesh tui` — the minimal home (recent runs + a centered *New run*), the
new-run wizard browsing the filesystem for evidence with `#file`/`#folder` fuzzy search, then
`uv run siftmesh tui "$RUN"` — the live cockpit: vitals, pipeline ribbon, task table,
claims/agents/budget, audit ticker.)

## 3:15 — Act B: live self-correction hero (75s)

```bash
bash examples/demo_case/run_demo.sh --agent claude
RUNL=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUNL/audit/agent_calls.jsonl"            # attempt 1 … then attempt 2
cat "$RUNL/audit/critic_verdicts.jsonl"        # retry_required → accepted
cat "$RUNL/claims/unsupported_claims.jsonl"    # the rejected, under-anchored attempt-1 over-claim
cat "$RUNL/claims/claim_ledger.jsonl"          # the corrected, anchored attempt-2 claim
```

> "Now the live agent — Claude, restricted to typed tools via strict-MCP, tier T1. It investigates
> on its own. When it over-claims without an anchor, the deterministic critic returns
> `retry_required`; the rejection reasons are fed back into the prompt; the agent revises against the
> real tool output; and the corrected, anchored claim is accepted on attempt 2. The mistake and the
> correction are both in the audit log — self-correction, not scripted."

> "Crucially: even a successful prompt injection can't exfiltrate (no network tool), can't write
> outside the run dir, and can't become a reported fact without passing the critic. LLM proposes,
> code decides."

## 4:30 — Close (15s)

> "Real tools, evidence-safe, agent-agnostic with honest safety tiers, fully replayable — and it
> self-corrects. That's SIFTMesh."

Show: `README.md` top + the repo URL + Apache-2.0.

---

## Recording notes

- Use the committed `examples/demo_case` so the run is fast and identical every take.
- Act B needs `claude setup-token` (subscription) — do it before recording; never show the token.
- If a live take is flaky, Act A is the guaranteed-green fallback (golden-tested determinism).
- Keep terminal font large; pre-set `siftmesh tui` theme with `ctrl+t` if needed.
- Per CLAUDE §2B, do **not** record against real SANS/ROCBA evidence — the demo case is public data.

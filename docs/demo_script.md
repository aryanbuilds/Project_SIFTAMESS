# Demo script (≤5 minutes)

A shot list + narration for the submission video. Two acts: **(A)** the zero-keys deterministic proof
(reliable, always works), then **(B)** the live self-correction demo (Claude). If recording time is
tight, Act A alone satisfies criteria 2/4/5; add Act B for criterion 1.

The committed reference run is a single REAL LIVE Claude-agent pass over the ROCBA case - disk + memory
in one autonomous run, `RUN-20260615-064002` (case `case_fast`, ~1 h 57 m wall clock, final state
`done`). Its sealed ledgers and `replay.html` ship under
`docs/logs/rocba-live-RUN-20260615-064002/` for anyone who wants the full audit trail without keys.
For the video itself, record against the public demo case so each take is fast and identical.

Record a real terminal. Pre-stage the repo (`uv sync`) so the camera starts on the run.
Target ≈4:30 to leave buffer.

---

## 0:00 - Hook (15s)

> "SIFTMesh is a CLI-first, evidence-safe controller for autonomous DFIR. The LLM proposes; **code
> decides**. Every finding is anchored to a real tool call, every claim is critiqued by deterministic
> code, and the whole run replays from an audit log. And it's honest about agent risk - it labels
> every agent's safety tier."

Show: `uv run siftmesh agents list` - point at the **tier** column (T0 floor, T1 Claude, T2
opencode/gemini/codex, T3 judge) and the legend.

## 0:15 - Act A: zero-keys run (45s)

```bash
bash examples/demo_case/run_demo.sh
```

> "No API keys. This runs the deterministic real-tool floor - tier T0 - over a real Windows Security
> event log. It hashes the evidence, plans, dispatches, runs the real evtx parser, and reaches done."

Show the tail: `state: done`, and the printed run directory.

## 1:00 - Evidence safety + anchored claims (60s)

```bash
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUN/evidence/evidence_manifest.json"     # SHA-256 sealed at ingest
cat "$RUN/claims/claim_ledger.jsonl"           # every claim cites tool_call_id + source_sha256
```

> "Evidence is SHA-256 sealed and never modified - chain of custody. Each finding cites the exact tool
> call and the source hash. A claim *without* that anchor can't be accepted."

## 2:00 - The critic gate + report (45s)

```bash
cat "$RUN/audit/critic_verdicts.jsonl"         # the deterministic governance gate
sed -n '1,40p' "$RUN/reports/final_report.md"  # evidence-backed findings + ATT&CK
```

> "The deterministic critic is the only gate that can accept a finding. Here both tasks are accepted
> because every claim is anchored. Unsupported claims would be confined to Appendix B - never the
> findings body."

## 2:45 - Replay / audit (30s)

```bash
uv run siftmesh replay "$RUN"                  # the whole run reconstructed from JSONL
```

> "Every action is a timestamped JSONL record. The entire investigation replays - that's criterion 5,
> audit-trail quality."

(Optional B-roll: `uv run siftmesh tui` - the minimal home (recent runs + a centered *New run*), the
new-run wizard browsing the filesystem for evidence with `#file`/`#folder` fuzzy search, then
`uv run siftmesh tui "$RUN"` - the live cockpit: vitals, pipeline ribbon, task table,
claims/agents/budget, audit ticker.)

## 3:15 - Act B: live self-correction hero (75s)

```bash
bash examples/demo_case/run_demo.sh --agent claude --judge opencode
RUNL=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUNL/audit/agent_calls.jsonl"            # attempt 1 … then the forced retry
cat "$RUNL/audit/critic_verdicts.jsonl"        # retry_required → escalation_required
```

The committed reference for this act is the live ROCBA run - the exact command, for the record:

```bash
SIFTMESH_CAPS__MAX_PARALLEL_TASKS=6 uv run siftmesh run ./case_fast \
  --evidence ~/projects/data --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --objective "What key projects did Fred Rocba have access to? What was stolen, where to, how, and when?" \
  --auto --agent claude --judge opencode --parallel \
  --max-agent-tasks 400 --max-iterations 2
```

> "Now the live agent - Claude, restricted to typed tools via strict-MCP, tier T1. It investigates
> on its own. On the committed ROCBA run it produced 223 anchored claims - 182 confirmed, 41 inferred,
> zero unsupported - across 245 tool calls. opencode runs as an advisory Tier-2 judge; it never
> promotes."

> "The honest part: on three heavy tasks - the $MFT and USN-journal parses, TASK-016/017/019 - the
> tools *ran* but the live agent failed to return anchored claims. The deterministic critic returned
> `retry_required`, the rejection reasons were fed back into the prompt, attempt 2 still failed, so
> those tasks were escalated and quarantined - their claims never reached the findings. That's the
> critic catching the agent, not a scripted win. Three real self-correction retries are in the audit
> log; the run still reached `done` because governance refused to promote unsupported claims."

> "Crucially: even a successful prompt injection can't exfiltrate (no network tool), can't write
> outside the run dir, and can't become a reported fact without passing the critic. This run logged
> 11,628 injection alerts - none executed - and most are an honest over-trigger on base64-like hash
> fragments in tool output: fail-safe, noisy, disclosed. LLM proposes, code decides."

## 4:30 - Close (15s)

> "Real tools, evidence-safe, agent-agnostic with honest safety tiers, fully replayable - and it
> self-corrects. That's SIFTMesh."

Show: `README.md` top + the repo URL + Apache-2.0.

---

## Recording notes

- Use the committed `examples/demo_case` so the run is fast and identical every take.
- Act B needs `claude setup-token` (subscription) - do it before recording; never show the token.
- If a live take is flaky, Act A is the guaranteed-green fallback (golden-tested determinism).
- Keep terminal font large; pre-set `siftmesh tui` theme with `ctrl+t` if needed.
- Per CLAUDE §2B, do **not** record against real SANS/ROCBA evidence - the demo case is public data.

# Demo script (≤5 minutes): recorded against the REAL ROCBA evidence

A shot list and narration for the submission video. The maintainer records it on the SANS SIFT
workstation against the real ROCBA evidence (the disk image plus memory capture). Component 2 requires
*real case data* and *a self-correction sequence*. Both are below.

> **On CLAUDE §2B:** that rule forbids the *coding agent* from autonomously running the pipeline against
> real evidence. It does **not** forbid the maintainer operating their own authorized run for the
> recording. The maintainer runs every command here.

**Pre-stage (before the camera rolls):** `uv sync --all-extras`; `claude setup-token`; have the
**completed** real ROCBA run dir ready (`./case_rocba/case_runs/RUN-*` from
`docs/try_it_out.md` §4) so Act A reads real findings instantly, and pre-extract a small slice of its
artifacts for the live Act B so it self-corrects within the time budget. Keep the terminal font large.
Never show a token. Target ≈4:30.

---

## 0:00 Hook (15s)

> "SIFTMesh is a CLI-first, evidence-safe controller for autonomous DFIR. The LLM proposes; **code
> decides**. Every finding is anchored to a real tool call, every claim is critiqued by deterministic
> code, and the whole run replays from an audit log. It also labels every agent's safety tier."

Show: `uv run siftmesh agents list`. Point at the **tier** column (T0 floor · T1 Claude · T2
opencode/gemini/codex · T3 judge).

## 0:15 The real case and the result (45s)

> "This is the real ROCBA case, a 23 GB Windows disk image and a 19 GB memory capture. SIFTMesh sealed
> them read-only, then ran nineteen real forensic tools on its own."

Show the completed real run:

```bash
RUN=$(ls -dt ./case_rocba/case_runs/RUN-* | head -1)
sed -n '1,40p' "$RUN/reports/final_report.md"   # ADAMANTIUM → Google Drive + USB exfil; SDelete cleanup
```

> "634 evidence-anchored findings, zero unsupported, zero contradictions. Stolen ADAMANTIUM research
> exfiltrated to a personal Google Drive and USB, with SDelete and forty-eight thousand journal
> deletions as cleanup."

## 1:00 Evidence safety and anchored claims (60s)

```bash
cat "$RUN/evidence/evidence_manifest.json"     # the .E01 sealed at ingest: sha256 f2eb856d…
grep -m1 PowerShell "$RUN/claims/claim_ledger.jsonl"   # a finding citing tool_call_id + source_sha256
grep -m1 '"tool_call_id":"TOOL-004"' "$RUN/audit/tool_calls.jsonl"   # the exact tool exec it points to
```

> "Code SHA-256 seals the evidence and never modifies it: chain of custody. Each finding cites the exact
> tool call and the source hash; the claim's hash matches the tool's hash. A claim without that anchor
> cannot become a fact. The anchor is the hallucination firewall. (Walked end-to-end in
> `docs/execution_logs_sample.md`.)"

## 2:00 The critic gate and replay (45s)

```bash
cat "$RUN/audit/critic_verdicts.jsonl"         # the deterministic governance gate
uv run siftmesh replay "$RUN"                  # the whole run reconstructed from timestamped JSONL
```

> "The deterministic critic is the sole promoter: accepted, retry, human-review, escalate. SIFTMesh
> records every action with a timestamp, so the entire investigation replays. That is audit-trail
> quality, the fifth judging criterion."

## 2:45 Live self-correction against the real evidence (90s)

Run the live agent on a small slice of the real ROCBA artifacts so it finishes on camera:

```bash
uv run siftmesh run ./case_live --evidence ~/projects/rocba_slice \
  --agent claude --auto-human-loop --max-iterations 2
RUNL=$(ls -dt ./case_live/case_runs/RUN-* | head -1)
cat "$RUNL/audit/agent_calls.jsonl"            # attempt 1 … then attempt 2
cat "$RUNL/audit/critic_verdicts.jsonl"        # retry_required → accepted
cat "$RUNL/claims/unsupported_claims.jsonl"    # the rejected, under-anchored attempt-1 over-claim
cat "$RUNL/claims/claim_ledger.jsonl"          # the corrected, anchored attempt-2 claim
```

> "Now the live agent: Claude, sandboxed to the typed tools via strict-MCP, tier T1, investigating
> real evidence on its own. When it over-claims without an anchor, the deterministic critic returns
> `retry_required`; the rejection reasons go back into the prompt; the agent revises against the real
> tool output; and code accepts the corrected, anchored claim on attempt 2. The audit log holds both
> the mistake and the correction. This is emergent self-correction, not a script."

> "And even a successful prompt injection over the evidence cannot exfiltrate, because there is no
> network tool. It cannot write outside the run dir, and it cannot become a reported fact without
> passing the critic. LLM proposes, code decides."

## 4:15 Close (15s)

> "Real tools on real evidence, evidence-safe, agent-agnostic with honest safety tiers, fully
> replayable, and it self-corrects. That is SIFTMesh."

Show: `README.md` top + the repo URL + Apache-2.0.

---

## Recording notes

- **Act A reads the completed real run** (instant); only **Act B runs live**. Keep its evidence slice
  small (a few extracted artifacts: the PowerShell evtx plus a couple registry hives) so the
  self-correction loop completes inside the 90s budget.
- Act B needs `claude setup-token` (subscription) done **before** recording; never show the token.
- If a live take is flaky, fall back to replaying a previously-recorded real live run's ledgers
  (`agent_calls`/`critic_verdicts`/`unsupported_claims`/`claim_ledger`). That is still real, still
  self-correction, just not live-typed.
- Optional B-roll: `uv run siftmesh tui "$RUN"`, the live cockpit (vitals, pipeline ribbon, task
  table, claims, audit ticker) over the real run; and the default real-time tagged log stream in the
  plain CLI.
- The full committed ledgers for both reference runs back every fact above: see
  `docs/logs/rocba-disk-RUN-20260612-163324/` and `docs/logs/rocba-memory-RUN-20260612-082630/`.

# SIFTMesh demo case (zero-keys, deterministic floor)

A tiny, fully reproducible case that exercises the **whole** SIFTMesh pipeline — hash → plan →
dispatch → real tool execution → claim ledger → critic → report → replay — **with no API keys and no
live agent**. It runs on the deterministic real-tool floor (tier **T0**), so a judge can reproduce it
on a fresh checkout in seconds.

## What's here

```
examples/demo_case/
  README.md            # this file
  expected_findings.md # ground truth — what a correct investigation must surface
  evidence/
    Security.evtx      # a real Windows Security event log (7 records; public test fixture)
  run_demo.sh          # one command: siftmesh run … --auto
```

`evidence/Security.evtx` is the public `Security_short_selected.evtx` sample from
[omerbenamram/evtx](https://github.com/omerbenamram/evtx) (7 records, EventIDs incl. 4625/4776/5152).
It is **real** evidence parsed by the **real** `evtx` backend — nothing is mocked.

## Run it

```bash
uv sync                      # or: uv run siftmesh setup
bash examples/demo_case/run_demo.sh
```

The run reaches `state: done` and writes a full run directory under
`examples/demo_case/case_runs/RUN-*` (git-ignored). Inspect it:

```bash
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUN/claims/claim_ledger.jsonl"      # evidence-anchored findings
cat "$RUN/audit/tool_calls.jsonl"         # every real tool call (provenance)
cat "$RUN/audit/critic_verdicts.jsonl"    # one critic verdict per task
cat "$RUN/reports/final_report.md"        # the deterministic, evidence-backed report
```

## What it proves

- **Evidence safety** — `Security.evtx` is SHA-256 sealed at ingest; the original is never modified.
- **Real tools** — `parse_evtx_security` + `build_timeline` run against the real log.
- **Anchored claims** — every promoted claim cites a `tool_call_id` + `source_sha256`.
- **The critic gate** — both task verdicts are `accepted`; an unanchored claim would be rejected and
  kept out of the report (see `expected_findings.md`).
- **Replayable audit** — the JSONL ledgers reconstruct the whole run.

## Want the live, self-correcting agent?

The floor is the safe baseline. To see the **emergent self-correction** hero loop (tier **T1**), add
a live agent (Claude is the only constrained/T1 executor today):

```bash
claude setup-token        # subscription auth (or export ANTHROPIC_API_KEY=…)
bash examples/demo_case/run_demo.sh --agent claude
```

See `docs/judge_runbook.md` for what to look at.

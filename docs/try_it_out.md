# Try it out — local deploy in 3 minutes

SIFTMesh runs on **Linux** (SANS SIFT / Ubuntu). It is `uv`-managed (not pip/venv). The path below
needs **no API keys** — it runs the deterministic real-tool floor (tier **T0**) over a committed
public fixture. Going live (tier T1/T2) is one extra flag (§5).

## 1. Prerequisites

- Python 3.11 or 3.12 on Linux.
- [`uv`](https://docs.astral.sh/uv/) (Astral). Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- `git`.

## 2. Install

```bash
git clone <repo-url> siftmesh && cd siftmesh
uv sync                       # base deps + dev tools
# Optional: install ALL backends (forensic parsers, brief readers, TUI) + onboard agents:
uv run siftmesh setup         # one command — see §5; or `uv run siftmesh setup --no-tui --yes`
```

> `uv sync --extra X` is *declarative* (it removes extras you don't name). To add an extra always use
> `uv sync --all-extras` (or `siftmesh setup`, which does that for you).

## 3. Verify the host (fail-closed)

```bash
uv run siftmesh doctor            # host + each tool backend; non-zero exit if a needed dep is missing
uv run siftmesh doctor --agents   # which coding agents are installed / authed / sandboxed + tier
```

`doctor --agents` prints the honest **safety tiers** (T0–T3) and, for any not-ready agent, the exact
fix (install / authenticate). A missing backend fails *closed* when invoked — never a fake result.

## 4. Run the zero-keys demo

```bash
bash examples/demo_case/run_demo.sh
```

Expect `state: done`. Then inspect the real run directory:

```bash
RUN=$(ls -dt examples/demo_case/case_runs/RUN-* | head -1)
cat "$RUN/claims/claim_ledger.jsonl"       # evidence-anchored findings (each cites tool_call_id+sha)
cat "$RUN/audit/tool_calls.jsonl"          # every real tool call
cat "$RUN/audit/critic_verdicts.jsonl"     # the critic gate (accepted/retry_required/…)
cat "$RUN/reports/final_report.md"         # the deterministic, evidence-backed report
uv run siftmesh replay "$RUN"              # replay the audit timeline (add --html for a file)
```

What you just proved: evidence is SHA-256 sealed and never modified; the real `parse_evtx_security` +
`build_timeline` backends ran; every promoted claim is anchored; the critic accepted both tasks; the
whole run is replayable from JSONL. See `examples/demo_case/expected_findings.md` for the ground
truth, and inspect `"$RUN/audit/*.jsonl"` (or `uv run siftmesh replay "$RUN"`) for the full
timestamped, tool-traceable audit trail.

## 5. Go live (optional — tier T1/T2)

A live agent is opt-in. **Claude** is the only constrained (T1) executor today (typed tools via
strict-MCP); opencode/gemini/codex are T2 (unconstrained opt-ins — see `docs/architecture.md §2a`).

```bash
claude setup-token                                   # subscription auth (or export ANTHROPIC_API_KEY=…)
bash examples/demo_case/run_demo.sh --agent claude   # live, self-correcting investigation
```

## 6. Watch it in the cockpit (optional)

```bash
uv run siftmesh tui            # home: recent runs + a centered "New run" + onboarding
uv run siftmesh tui "$RUN"     # attach the live cockpit to a run
```

The home screen is minimal — a left list of recent runs (badged `terminal`/`blocked`/`paused`/
`running`) and a centered **New run**, with the shortcuts always visible (`n` new · `Enter` attach ·
`r` resume · `o` agents · `q` quit). **New run** is a 2-screen wizard: pick evidence by browsing the
whole filesystem (the tree is reachable *above* the project dir; type `#file <name>` or
`#folder <name>` to fuzzy-search anywhere) + give the objective, then review the host/space readiness
and launch. Press **`o`** for onboarding — an **Agents** tab (greys out anything not installed/authed
and offers a one-click *Launch auth*) and a **Tier-2 judge** tab (pick a provider, log in or paste an
API key; LiteLLM keys are validated and saved to a 600-perm `~/.config/siftmesh/.env`).

## 7. Real evidence

Driving SIFTMesh against a real disk image / memory capture (Sleuthkit, Volatility 3, the live
agent) is documented in `RUNBOOK.md`. Per CLAUDE.md §2B the project never self-tests against real
forensic evidence — the operator runs those flows on a real SANS SIFT workstation.

## Troubleshooting

- **`textual` not installed** (`siftmesh tui`): `uv sync --all-extras` or `uv run siftmesh setup`.
- **A backend shows `[warn]` in `doctor`**: it's only needed when its tool is invoked; install it
  then re-run `doctor`. The demo case needs none beyond the base install.
- **Dev checks**: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

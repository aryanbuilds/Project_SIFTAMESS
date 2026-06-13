# Try it out — run the real investigation locally

SIFTMesh runs on **Linux** (SANS SIFT / Ubuntu) and is `uv`-managed (not pip/venv). These steps run the
**real** pipeline against the **ROCBA** evidence on the workstation — real Sleuth Kit / Volatility 3 /
Plaso / evtx / regipy, real claims, a real replayable audit trail. The deterministic floor needs **no
API keys**; the live agent (tier T1) is one extra flag (§5).

## 1. Prerequisites

- Python 3.11 or 3.12 on Linux (the SANS SIFT workstation has the forensic CLIs already).
- [`uv`](https://docs.astral.sh/uv/) (Astral): `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- `git`.
- The **ROCBA evidence** read-only on the box (e.g. `~/projects/data/`): `rocba-cdrive.e01`,
  `Rocba-Memory.zip`, `ROCBA-BACKGROUND.pptx`.

## 2. Install

```bash
git clone <repo-url> siftmesh && cd siftmesh
uv sync --all-extras          # all backends (forensic parsers, brief readers, TUI)
uv run siftmesh setup         # onboard agents + create the Volatility symbol cache (or: setup --no-tui --yes)
```

> `uv sync --extra X` is *declarative* (it removes extras you don't name). Always use `uv sync
> --all-extras` (or `siftmesh setup`, which does that for you).

## 3. Verify the host (fail-closed)

```bash
uv run siftmesh doctor            # host + each tool backend; non-zero exit if a needed dep is missing
uv run siftmesh doctor --agents   # which coding agents are installed / authed / sandboxed + safety tier
uv run pytest -q                  # full suite (no evidence needed) — confirms the build is healthy
```

`doctor` prints the honest **safety tiers** (T0–T3) and, for any not-ready agent, the exact fix. A
missing backend fails *closed* when invoked — never a fake result.

## 4. Run the real ROCBA investigation (one command, `--auto`)

A single `run --auto` drives the whole case itself: hash + seal → plan → Sleuth Kit extraction →
auto re-ingest the carved artifacts → parse (evtx/registry/prefetch/MFT/USN/Plaso…) → critique →
report. Point `--evidence` at the ROCBA dir and `--brief` at the incident document:

```bash
SIFTMESH_ENABLE_SUPER_TIMELINE=true \
uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --auto --max-agent-tasks 400 --max-iterations 6
RUN=$(ls -dt ./case_rocba/case_runs/RUN-* | head -1); echo "RUN=$RUN"
```

The full staged flow (disk + memory separately, `evidence extract` / `decompress` / `ingest`, and the
low-disk "run in portions" mode) is in **[`../RUNBOOK.md`](../RUNBOOK.md)**. As it runs, a tagged
real-time log streams to your terminal (`[info] [agent] [tool_log] [alert] [result] [tasks]`, per-task
separators, `▸ N/M (P%)` progress); add `--quiet` to silence.

## 5. Inspect the real run

```bash
cat "$RUN/reports/final_report.md"          # evidence-backed findings + MITRE ATT&CK + chain of custody
cat "$RUN/claims/claim_ledger.jsonl"        # every finding cites tool_call_id + source_sha256
cat "$RUN/audit/tool_calls.jsonl"           # every real tool call, timestamped
cat "$RUN/audit/critic_verdicts.jsonl"      # the deterministic governance gate
uv run siftmesh replay "$RUN" --html        # the whole run reconstructed from JSONL
```

What you just proved: evidence is SHA-256 sealed and never modified; real forensic backends ran; every
promoted claim is anchored; unsupported claims are firewalled to Appendix B; the whole run is
replayable. A worked, traceable excerpt is in [`execution_logs_sample.md`](execution_logs_sample.md).

## 6. Go live — the self-correcting agent (optional, tier T1)

**Claude** is the constrained (T1) executor today — typed tools via strict-MCP. Add auth and one flag:

```bash
claude setup-token            # subscription (or: export ANTHROPIC_API_KEY=…)
uv run siftmesh run ./case_rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx --agent claude --auto-human-loop --max-iterations 2
```

Watch the self-correction in the ledgers: `audit/agent_calls.jsonl` (attempt 1 → 2),
`audit/critic_verdicts.jsonl` (`retry_required` → `accepted`), `claims/unsupported_claims.jsonl` (the
rejected attempt-1 over-claim) → `claims/claim_ledger.jsonl` (the corrected, anchored claim).
opencode/gemini/codex are honestly labelled unconstrained opt-ins (T2) — see
[`architecture.md`](architecture.md) §2a.

## 7. Watch it in the cockpit (optional)

```bash
uv run siftmesh tui            # home: recent runs + a centered "New run" + onboarding
uv run siftmesh tui "$RUN"     # attach the live cockpit to a run
```

The home screen is minimal — a list of recent runs and a centered **New run** wizard (browse the
filesystem for evidence with `#file`/`#folder` fuzzy search, pick a run-type, launch). Press **`o`** for
agent onboarding.

## Troubleshooting

- **`textual` not installed** (`siftmesh tui`): `uv sync --all-extras` or `uv run siftmesh setup`.
- **A backend shows `[warn]` in `doctor`**: it's only needed when its tool is invoked; install it then
  re-run `doctor`.
- **`vol` elsewhere**: `export SIFTMESH_VOL_PATH=/opt/volatility3/bin/vol`; symbols:
  `export SIFTMESH_VOL_SYMBOL_DIRS=/tmp/vol_symbols`.
- **A disk image yields 200+ derived tasks** → raise the cap: `--max-agent-tasks 400` (or
  `export SIFTMESH_CAPS__MAX_AGENT_TASKS=400` for the staged flow).
- **Dev checks**: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

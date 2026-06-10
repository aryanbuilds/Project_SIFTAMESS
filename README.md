# SIFTMesh

CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR on SANS SIFT and
Protocol SIFT. **The LLM proposes; deterministic code decides** — every finding is an evidence-anchored
claim, every claim is critiqued by deterministic code, and every run is a replayable, audited chain of
custody. (`uv`-managed; do not use pip/venv.)

## Setup (two commands)

```bash
uv sync                       # base deps + dev tools (ruff/mypy/pytest)
uv run siftmesh doctor --setup   # installs ALL backends (forensic + brief + a2a) + the Volatility
                                 # symbol cache, then verifies the host. Fails closed on a missing dep.
```

`doctor --setup` replaces the old `uv sync --extra …` / `export SIFTMESH_VOL_SYMBOL_DIRS=…` dance.
(Note: plain `uv sync --extra X` is *declarative* — it removes extras you don't name; `--setup`
runs `uv sync --all-extras`.)

## Run an investigation — automated (the headline)

Put the evidence in one dir, point `--brief` at the incident document (the TRUSTED objective), and
run one command:

```bash
uv run siftmesh run ./case_rocba --evidence ~/projects/ev_all \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --agent claude --auto --max-agent-tasks 400 --max-iterations 5
```

It reads the brief → hashes evidence → auto-decompresses archives → plans (one task per artifact
**family**, not per file) → the live agent investigates **toward the objective**, self-correcting
under the deterministic critic → quarantines any single flagged task (the run still completes) →
writes a report whose "Answer to the incident objective" section is anchored to real tool calls.

- **No briefing file?** Use `--objective "was host X compromised? find initial access"`.
- **Agent-neutral.** `--agent claude|gemini|codex|opencode|openclaw` (or `deterministic`). SIFTMesh is
  not Claude-only: any agent is a swap-in connector under the same deterministic governance. Run
  `siftmesh doctor --agents` (or `siftmesh agents list`) to onboard — it shows which agents are
  installed + authenticated and picks the best default. (Only Claude reaches the typed tools today;
  others run but their tool wiring is `verify-live` — see `PLAN/13`.)
- **Free, no keys?** Omit `--agent …` — the deterministic real-tool floor runs the whole pipeline.
- **Heavy tasks (disk-image extract, memory triage)** always run on the floor (the tool does the work);
  `--all-live` overrides. A pre-flight check estimates derived-data size vs free disk and, if it won't
  fit, prints a partition plan (run portions → `prune` → `merge`); `--force` skips it.

## Command reference

**Automated (one deterministic engine; modes are config):**

| Command | What it does |
|---|---|
| `run CASE --evidence DIR [--brief/--objective] [--auto\|--auto-human-loop\|--review-only\|--mode manual] [--agent claude\|gemini\|codex\|opencode]` | Init → plan → dispatch → collect → critique → decide → report, end to end. |
| `resume RUN` | Continue an interrupted run from its persisted state (skips hashing + decompress). |
| `status RUN` | Show state, mode, iteration, gates, per-task attempts, quarantined tasks. |
| `approve RUN --gate G` / `reject RUN --gate G` | Resolve a gate (plan\|dispatch\|retry\|report) in guided mode. |
| `merge CASE --run RUN_A --run RUN_B … [--agent claude]` | Combine ≥2 completed runs into one provenance-tracked report (opt-in advisory synthesis). |
| `doctor [--setup] [--protocol-sift] [--agents]` | Verify the host/backends (fail-closed); `--setup` installs + configures them; `--agents` onboards the coding agents. |

**Manual / deterministic (staged — full control; `run --auto` does all of this for you):**

| Command | What it does |
|---|---|
| `init-case CASE --evidence DIR [--brief/--objective]` | Hash + seal evidence into a new run dir (manifest, custody, policy). |
| `plan RUN [--review-only]` | Deterministic investigation plan + task contracts (one per artifact family). |
| `dispatch RUN` / `collect RUN` / `critique RUN` | Execute task contracts → gather results → validate claims, emit verdicts. |
| `report RUN` / `replay RUN [--html]` | Render the deterministic evidence-backed reports / replay the audit timeline. |
| `extract-artifacts RUN --image … --keys …` | Recover Windows artifacts from a disk image (Sleuthkit; audited). |
| `analyze-memory RUN --memory …` | Triage a memory image with Volatility 3 (subprocess; audited). |
| `decompress RUN --archive …` / `ingest-derived RUN` | Expand an archive → make derived artifacts plannable. |
| `prune RUN [--force]` | Reclaim a completed run's bulky `evidence/extracted/` derived data; keep all ledgers. |
| `retry RUN TASK` | Re-critique one task; tighten + re-dispatch if DECIDE says so. |

**Inspection (read-only):**

| Command | What it does |
|---|---|
| `tasks list\|show RUN [TASK]` · `claims list\|show RUN [CLAIM]` · `audit tail RUN [--ledger …]` | Inspect contracts, claims, and audit ledgers. |
| `agents list` · `agents inspect <id>` | Onboard/inspect the coding-agent connectors (installed? authed? tool-reachable? default?). |
| `protocol-sift inspect` · `protocol-sift skills list` | Inspect/govern the `~/.claude` Protocol SIFT layer. |

## Develop

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Architecture decisions live in `PLAN/` (notably `PLAN/01_ARCHITECTURE.md` and
`PLAN/12_ADR_orchestration_engine.md` — keep the native deterministic FSM; no LangGraph/CAO). Real
end-to-end runs against forensic evidence are maintainer-gated (CLAUDE.md §2B).

License: **Apache-2.0**.

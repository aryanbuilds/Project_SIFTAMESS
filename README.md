# SIFTMesh

CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR on SANS SIFT and
Protocol SIFT. **The LLM proposes; deterministic code decides** — every finding is an evidence-anchored
claim, every claim is critiqued by deterministic code, and every run is a replayable, audited chain of
custody. (`uv`-managed; do not use pip/venv.)

## Setup + onboarding (one command)

```bash
uv sync                  # base deps + dev tools (ruff/mypy/pytest)
uv run siftmesh setup    # installs ALL backends + the Volatility symbol cache, probes the coding
                         # agents, lets you pick which to use, and remembers the choice.
```

`siftmesh setup` is the single onboarding entry: it installs everything (`uv sync --all-extras`),
probes which agents are installed + authenticated + sandboxed, opens a TUI to pick a **multi-agent**
set (or `setup --no-tui`/`--yes` for a headless auto-pick of the ready agents), and persists it to
`~/.config/siftmesh/siftmesh.toml` (a project `./siftmesh.toml` overrides it). `doctor [--setup]`
remains for a pure host/backend health check. (Plain `uv sync --extra X` is *declarative* — it
removes extras you don't name; `setup`/`doctor --setup` run `uv sync --all-extras`.)

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
- **Agent-neutral.** `--agent claude|gemini|codex|opencode` (or `deterministic`). SIFTMesh is
  not Claude-only: any agent is a swap-in connector under the same deterministic governance. Run
  `siftmesh doctor --agents` (or `siftmesh agents list`) to onboard — it shows which agents are
  installed + authenticated + sandboxed and picks the best default. (Only Claude reaches the typed
  tools today; others run sandboxed but their tool wiring is `verify-live` — see `PLAN/13`. A live
  agent is opt-in: a plain `run` uses the deterministic floor unless you pass `--agent`.)
- **Pick a model per provider.** `--model gemini=gemini-3-pro --model codex=gpt-5.5` (repeatable)
  overrides the model for that run; persist it via `siftmesh setup` (CLI flag or the onboarding TUI's
  per-provider fields). `siftmesh agents inspect gemini` shows the effective model.
- **Tier-2 judge (advisory).** `--judge gemini|codex|opencode|claude|litellm:<model>|off` enables an
  advisory second-opinion judge for the run (fails soft; the deterministic critic stays sole promoter).
- **Free, no keys?** Omit `--agent …` — the deterministic real-tool floor runs the whole pipeline.
- **Heavy tasks (disk-image extract, memory triage)** always run on the floor (the tool does the work);
  `--all-live` overrides. A pre-flight check estimates derived-data size vs free disk and, if it won't
  fit, prints a partition plan (run portions → `prune` → `merge`); `--force` skips it.

## Watch it live — the cockpit (TUI)

```bash
uv run siftmesh tui                 # home: pick a run to attach, start a new one, or onboard agents
uv run siftmesh tui case_runs/RUN-… # attach the live cockpit to a run
```

The Textual cockpit is a **read-only** view over the run dir (it renders `run_state.json` + the
ledgers on a 1 s poll; launching a run uses the same governed engine). Four zones: a **vitals** bar
(mode · stage · gate · agent · tasks done/total · total & current-stage timers), a **pipeline ribbon**
(the FSM path, done/current/pending), a **task table** (per-task status · attempt · family · agent ·
claims · verdict) beside claims/critic/agent/budget summaries, and a live **audit-log** ticker — plus
a **navigation tree** to open any run file. Optional extra (`uv sync --extra tui`, or `setup`).

## Command reference

**Automated (one deterministic engine; modes are config):**

| Command | What it does |
|---|---|
| `run CASE --evidence DIR [--brief/--objective] [--auto\|--auto-human-loop\|--review-only\|--mode manual] [--agent claude\|gemini\|codex\|opencode] [--judge …]` | Init → plan → dispatch → collect → critique → decide → report, end to end. `--agent` picks the executor; `--judge claude\|gemini\|codex\|opencode\|litellm:<model>` picks the advisory Tier-2 judge (fail-soft, off by default). |
| `resume RUN` | Continue an interrupted run from its persisted state (skips hashing + decompress). |
| `status RUN` | Show state, mode, iteration, gates, per-task attempts, quarantined tasks. |
| `approve RUN --gate G` / `reject RUN --gate G` | Resolve a gate (plan\|dispatch\|retry\|report) in guided mode. |
| `merge CASE --run RUN_A --run RUN_B … [--agent claude]` | Combine ≥2 completed runs into one provenance-tracked report (opt-in advisory synthesis). |
| `setup [--no-tui] [--scope global\|project] [--yes]` | One-command onboarding: install backends + probe agents + pick a multi-agent set + persist it. |
| `tui [RUN]` | Live Textual cockpit: attach to a run, or the home/run-picker (start a run, onboard agents). |
| `doctor [--setup] [--protocol-sift] [--agents]` | Verify the host/backends (fail-closed); `--setup` installs + configures them; `--agents` onboards the coding agents. |

**Manual / deterministic (staged — full control; `run --auto` does all of this for you):**

| Command | What it does |
|---|---|
| `init-case CASE --evidence DIR [--brief/--objective]` | Hash + seal evidence into a new run dir (manifest, custody, policy). |
| `plan RUN [--review-only]` | Deterministic investigation plan + task contracts (one per artifact family). |
| `dispatch RUN` / `collect RUN` / `critique RUN` | Execute task contracts → gather results → validate claims, emit verdicts. |
| `report RUN` / `replay RUN [--html]` | Render the deterministic evidence-backed reports / replay the audit timeline. |
| `evidence extract RUN --image … --keys …` | Recover Windows artifacts from a disk image (Sleuthkit; audited). |
| `evidence memory RUN --memory …` | Triage a memory image with Volatility 3 (subprocess; audited). |
| `evidence decompress RUN --archive …` / `evidence ingest RUN` | Expand an archive → make derived artifacts plannable. |
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

Architecture decisions live in `PLAN/` — notably `PLAN/01_ARCHITECTURE.md`,
`PLAN/12_ADR_orchestration_engine.md` (keep the native deterministic FSM; no LangGraph/CAO),
`PLAN/13` (agent-neutral connectors), and `PLAN/14` (Textual cockpit + `setup`, Textual over Ratatui).
`PLAN/00_INDEX_AND_ROADMAP.md` is the roadmap. Real end-to-end runs against forensic evidence are
maintainer-gated (CLAUDE.md §2B).

License: **Apache-2.0**.

<p align="center">
  <img src="assets/github_banner_siftmesh.png" alt="SIFTMesh" width="100%">
</p>

<p align="center">
  <b>Autonomous, evidence-safe DFIR orchestration for SANS SIFT.</b><br>
  The LLM proposes, the code decides — every finding is anchored to a real tool call, and every run is replayable.
</p>

---

## Tech stack

`uv`-managed (please don't use pip/venv). Everything is pinned in `pyproject.toml`.

| Area | Pins |
|---|---|
| Runtime | Python ≥ 3.11 (CI: 3.11 + 3.12), Linux-first (SANS SIFT / Ubuntu) |
| Core | Typer 0.26 · Pydantic 2.13 + pydantic-settings 2.14 · structlog 25 · PyYAML 6 · Jinja2 3.1 · **MCP SDK 1.27** · regipy 6.2.1 · tomlkit 0.13 |
| `sift` extra | evtx 0.11.1 · libscca (prefetch) · mft 0.7 |
| `brief` extra | python-pptx · python-docx · pypdf (read the incident brief) |
| `tui` extra | Textual 8 (the cockpit) |
| `llm` extra | LiteLLM 1.7 (the optional Tier-2 judge only) |
| `a2a` extra | a2a-sdk 1.1 (optional agent-to-agent interop) |
| Dev | ruff · mypy · pytest · hypothesis |

External tools it drives (on a SANS SIFT host): Sleuth Kit, Volatility 3, EZ Tools, 7-Zip.

---

## About the project

SIFTMesh is a CLI-first controller that runs a real DFIR investigation for you and keeps it honest.
You point it at evidence and an objective; it hashes and seals the evidence read-only, plans the work,
sends a real agent in to investigate, then a **deterministic critic** checks every claim against the
actual tool output before anything is allowed into the report. The agent is free to reason and make
mistakes — the governance code is what decides truth. That split is the whole point: **autonomy lives
in the agent, determinism lives in the code.**

**What it can do**

- Hash + seal evidence into a read-only vault with a SHA-256 manifest and a chain-of-custody log.
- Plan from the manifest, dispatch an agent to investigate **toward your objective**, and write an
  evidence-anchored report with a full, replayable audit trail.
- Run completely on its own (`run --auto`) or step-by-step with human gates.
- Stay **agent-neutral** — Claude, Codex, Gemini, OpenCode, or a no-keys deterministic floor.
- Self-correct: when the critic rejects an unsupported claim, the agent gets the feedback and tries
  again — emergently, not scripted.
- Use **10 real typed forensic tools** (Sleuth Kit, Volatility 3, EZ Tools, evtx, regipy, prefetch,
  MFT). No mocks, no fake output.

**What it's NOT**

- Not a generic multi-agent chatbot, a SOC platform, or a web dashboard.
- Not "let the LLM decide forensic truth" — the LLM never has the final say.
- Not a replacement for court-vetted tools. It **orchestrates** them; the tools are the source of truth.
- Never runs raw shell, destructive ops, or writes to your evidence. It fails closed, not open.

---

## Pre-setup (recommended)

A live agent is **optional** — the deterministic floor runs the whole pipeline with no API keys. But
if you want a live agent to investigate, install its CLI **before** you run `setup` so onboarding can
detect it:

```bash
# uv (required)            -> https://docs.astral.sh/uv/
# claude code (best tool reach today)
npm i -g @anthropic-ai/claude-code      # then: claude setup-token
# any of these also work as the executor or the Tier-2 judge:
npm i -g @openai/codex                   # then: codex login
npm i -g @google/gemini-cli              # then: export GEMINI_API_KEY=...
curl -fsSL https://opencode.ai/install | bash   # then: opencode auth login
```

On a SANS SIFT workstation the forensic CLIs (sleuthkit, volatility3, 7z, EZ tools) are already there.
You can also onboard agents later from inside the TUI (`o` → Agent setup) — it greys out anything not
ready and tells you the exact fix.

---

## Setup & install

```bash
uv sync                  # base deps + dev tools
uv run siftmesh setup    # installs all backends, probes your agents, lets you pick a set + judge,
                         # and remembers the choice (~/.config/siftmesh/siftmesh.toml)
uv run siftmesh doctor   # fail-closed health check (host + every tool backend)
```

The commands you'll actually use day to day:

```bash
uv run siftmesh run ./case --evidence ~/data --objective "was this host compromised?" --auto
uv run siftmesh tui            # the live cockpit (or start a new run from it)
uv run siftmesh resume RUN     # continue an interrupted run
uv run siftmesh status RUN     # where is it, what's blocked
```

---

## Features

- **One-command auto run** — init → plan → dispatch → critique → decide → report, end to end.
- **Agent-neutral + honest safety tiers (T0–T3)** — `agents list` shows what's actually sandboxed and
  tool-reaching; the label can never disagree with what dispatch does.
- **Optional Tier-2 judge** — an advisory second opinion (any provider via LiteLLM). It can only lower
  confidence or annotate; it never promotes. Fails soft.
- **Evidence vault** — SHA-256 manifest, read-only posture, chain-of-custody log; originals are never
  touched.
- **Deterministic critic + self-correction** — unsupported claims get downgraded or dropped and never
  reach the report; the agent re-tries on the feedback.
- **Full traceability** — claim + contradiction ledgers, a token/agent/tool audit, and an HTML replay.
- **TUI cockpit** — a live, read-only view over the run, plus a guided new-run wizard with a
  filesystem-wide evidence picker and a 2-tab onboarding (Agents + Tier-2 judge).
- **Low-disk mode** — run in portions → prune between → merge into one report. Plus pause/resume.

---

## Architecture

<!-- Hand-drawn architecture diagrams are coming to assets/. -->
<!-- <p align="center"><img src="assets/architecture.png" alt="SIFTMesh architecture" width="100%"></p> -->

> Diagram coming soon (hand-drawn, will live in `assets/`).

Under the hood it's a deterministic state machine with a few clear roles. The agent is the only part
that "thinks"; everything around it is plain code that can be audited and replayed.

| Role | Stage | What it does |
|---|---|---|
| **Planner** | `plan` | Reads the sealed manifest, routes each artifact to the right forensic family/tool, writes task contracts. No LLM, never reads evidence bytes. |
| **Executor** | `dispatch` / `collect` | Either the deterministic real-tool floor **or** a live agent (claude/codex/gemini/opencode) investigating toward your objective. Both must emit evidence-anchored claims (a real `tool_call_id` + source hash). |
| **Critic** | `critique` | The deterministic Tier-1 validator **and the only thing allowed to promote a finding.** A claim with no real tool call or source hash gets downgraded or marked unsupported. Catches contradictions and prompt-injection. |
| **Ultraworker** | `decide` | The state machine. It folds the critic's verdicts and decides: done, retry, escalate, human-review, or follow-up — and enforces the caps + the self-correction loop. |
| **Tier-2 judge** | advisory | Optional second opinion. Lowers confidence or annotates only; never promotes; never blocks a run. |
| **Reporter / replay** | `report` | Code-built, evidence-backed report + a replayable audit timeline. Unsupported claims only ever appear in an appendix. |

**Run it step-by-step (manual / full control):**

```bash
siftmesh init-case ./case --evidence ~/data --objective "..."
siftmesh plan      ./case/case_runs/RUN-*
siftmesh dispatch  ./case/case_runs/RUN-*
siftmesh collect   ./case/case_runs/RUN-*
siftmesh critique  ./case/case_runs/RUN-*
siftmesh report    ./case/case_runs/RUN-*
siftmesh replay    ./case/case_runs/RUN-* --html
```

**Or let one engine do all of it (auto):**

```bash
siftmesh run ./case --evidence ~/data --objective "..." --auto \
  --agent claude --max-agent-tasks 400 --max-iterations 5
```

Modes: `--auto` (run to the end), `--auto-human-loop` (stop at meaningful gates), `--review-only`
(plan and stop), or `--mode manual` (one step at a time). Drop `--agent` to run free on the
deterministic floor.

---

## What makes it different

| | Generic AI tools | Plain forensic tools | **SIFTMesh** |
|---|---|---|---|
| Who decides truth | the LLM (can hallucinate) | the analyst (manual) | **code decides; LLM only proposes** |
| Provenance | usually none | per-tool | **every claim → tool call + source hash** |
| Chain of custody | no | partial | **sealed manifest + custody log + replay** |
| Autonomy | yes, ungoverned | none | **yes, under deterministic governance** |
| Evidence safety | varies | read-only | **read-only, fails closed** |
| Agent lock-in | usually | n/a | **agent-neutral (swap-in connectors)** |

---

## All commands

**Automated (one engine, modes are config):**

| Command | Does |
|---|---|
| `run CASE --evidence DIR [--auto\|--auto-human-loop\|--review-only\|--mode manual] [--agent …] [--judge …]` | The whole pipeline, end to end. |
| `resume RUN` · `status RUN` | Continue an interrupted run · show state/gates/attempts. |
| `approve RUN --gate G` / `reject RUN --gate G` | Resolve a gate (plan\|dispatch\|retry\|report). |
| `merge CASE --run A --run B …` | Combine ≥2 completed runs into one report. |
| `setup` · `doctor [--setup\|--agents\|--protocol-sift]` | Onboard + persist · health check (fail-closed). |
| `tui [RUN]` | The live cockpit / new-run wizard / onboarding. |

**Staged (full manual control):**

| Command | Does |
|---|---|
| `init-case CASE --evidence DIR [--brief/--objective]` | Hash + seal evidence into a new run. |
| `plan RUN [--review-only]` | Deterministic plan + task contracts. |
| `dispatch RUN` / `collect RUN` / `critique RUN` | Execute → gather → validate claims. |
| `report RUN` / `replay RUN [--html]` | Render reports / replay the audit timeline. |
| `retry RUN TASK` · `prune RUN` | Re-critique one task · reclaim bulky derived data (keep ledgers). |

**Evidence access (audited):**

| Command | Does |
|---|---|
| `evidence extract RUN --image … --keys …` | Recover Windows artifacts from a disk image (Sleuth Kit). |
| `evidence memory RUN --memory …` | Triage a memory image (Volatility 3). |
| `evidence decompress RUN --archive …` / `evidence ingest RUN` | Expand an archive → make it plannable. |

**Inspection (read-only):**

| Command | Does |
|---|---|
| `tasks list\|show` · `claims list\|show` · `audit tail` | Inspect contracts, claims, ledgers. |
| `agents list\|inspect` · `protocol-sift inspect\|skills list` | Onboard agents · inspect the `~/.claude` layer. |

---

## Roadmap

- Hand-drawn architecture diagrams (into `assets/`).
- A2A agent-to-agent interop (optional, governed).
- ACP round-2 — typed-tool reach for Gemini/Codex (only Claude reaches the typed tools today).
- Sigma / pySigma detection breadth.
- More SIFT-lane tools, OS-level read-only mounts, and stream-parsing for huge archives.

---

## License & thanks

Apache-2.0 — see [`LICENSE`](LICENSE).

Thanks for taking a look. SIFTMesh exists because autonomous tooling and forensic rigor shouldn't be a
trade-off — you can have an agent do the legwork and still trust every line of the report. If it saves
you an hour on a case, it did its job. Contributions, issues, and hard questions are all welcome.

> *securing digital world one byte at a time*

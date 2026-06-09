# SIFTMesh — Work, Commands & Features through Epic H

_Last updated: 2026-06-09 · branch `mvp_phase_1`_

Running reference for everything SIFTMesh has implemented through **Epic H** (the Ultraworker State
Machine & `siftmesh run` automation). Builds on [`work_till_epicd.md`](work_till_epicd.md) (Epics A–D),
[`epic_f_feature_sofar.md`](epic_f_feature_sofar.md) (Epic F), and
[`epic_g_feature_sofar.md`](epic_g_feature_sofar.md) (Epic G — the deterministic critic); adds Epic H.

> **Status:** Epics **A, B, C, D, E, F, G** are complete and human-closed. **Epic H is fully complete**
> — **all children closed** (H1–H9 + review-only enforcement `hth.1` + derived re-ingest `hth.2`); the
> epic node **`hth` is left OPEN for the human** (only a human closes an epic node). **339 tests pass;
> ruff/format/mypy clean (89 source files); `siftmesh doctor` ok (tool allowlist = exactly 10).**
> Build spine: `A → B → C → D → E → F → G → H → K → J → L → M → N → I → P → O` (strictly sequential).

---

## 1. What SIFTMesh is

A **CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR** on SANS SIFT /
Protocol SIFT. It coordinates terminal agents through deterministic CLI workflows, task contracts,
context packets, an evidence vault, typed forensic MCP tools, a claim ledger, deterministic critic
validation + self-correction, human-review gates, and replayable audit logs — now driven end-to-end by
a **deterministic state machine** (`siftmesh run`).

**Load-bearing principles (enforced in code):**
- **CLI = source of truth.** Every stage writes inspectable files under `case_runs/RUN-*`.
- **"LLM proposes, code decides."** The agent is non-deterministic; the governance (critic, `decide()`,
  the transition table, caps, evidence-safety, audit) is deterministic. **There is no LLM in the engine.**
- **REAL-ONLY (CLAUDE §2B).** Every tool wraps a real, working library and produces genuine output; no
  mocks/placeholders/synthetic outputs. A missing backend **fails closed**, never a fake.
- **Privilege separation.** Planner proposes (never reads evidence bytes / never executes); executors
  run only the contract's one allowlisted tool; the critic + state machine govern deterministically;
  no raw shell anywhere.
- **Evidence is hostile.** Filenames and content are data, never instructions.
- **Crash-safe.** `RunState` is persisted atomically on every transition → a killed run resumes exactly
  where it stopped.

---

## 2. Architecture (layers) + package map

```
Layer 0  SANS SIFT host (Sleuthkit, Volatility 3, EZ Tools, 7-Zip, dotnet)
Layer 1  Typed MCP gateway — 10 evidence-safe forensic tools (Epic D)
Layer 2  Filesystem investigation bus — case_runs/RUN-* (run_state.json + context/evidence/tasks/results/claims/audit/reports)
Layer 3  Orchestration core — Planner+Deep-Context (E), Executor adapters+scheduler (F), Critic+decide (G), STATE MACHINE (H)
Layer 4  Terminal-agent harness — claude/opencode headless (F8), generic shell (F7)
Layer 5  CLI — the user-facing source of truth (Typer)
Layer 6  Optional TUI (last; not started)
```

```
siftmesh_core/
  cli.py · config.py · run_dir.py · doctor.py · logging.py · protocol_sift.py
  schemas/    _base, tool_result, claim, task, task_result, audit (ToolCall+CriticVerdict),
              run (RunState + RunMode + PerTaskState),    ← extended in Epic H
              agent_profile, agent_call, injection_alert, workflow, plan,
              critic_records (Contradiction/ConfidenceChange/Retry/Followup), decision,
              evidence, custody, protocol_sift, yaml_io
  evidence/   vault, manifest, hash_utils, path_policy, readonly, derived, custody,
              image_access (Sleuthkit), memory_access, decompress   ← decompress = GAP 1 (b2m.1)
  mcp_gateway/ registry (allowlist) · audit_exec (run_tool) · server (FastMCP)
               backends/ real (in-process) + sift_lane (host CLIs)
               tools/ the 10 typed tools (+ validation_tools.grade_claim_against_run)
  ledgers/    jsonl_ledger · tool_call_ledger · claim_ledger · custody_ledger · audit_log
              agent_calls · injection_alerts · critic_verdicts · contradiction_ledger
              · confidence_changes · retries · followups
  orchestrator/ planner · deep_context · artifact_router (E) · scheduler (F) · critic · decide (G)
                · state_machine · workflow_runner · ultraworker · human_gate          ← Epic H
                · budget_router · run_state_store                                       ← Epic H
  adapters/   base (ABC+registry) · deterministic_executor · spotlight
              · generic_shell_adapter · claude_adapter · opencode_adapter (F)
  reports/    (placeholder — Epic J)
workflows/    windows_initial_triage.yaml
```

---

## 3. CLI command surface

`siftmesh <command>` — **real** = fully implemented; **stub** = prints, real behavior lands in its epic.

| Command | Status | What it does |
|---|---|---|
| `init-case CASE_DIR --evidence DIR [--run-name N] [--verify-after]` | **real (B)** | Streaming SHA-256 → manifest + hashes + readonly posture + custody; creates the run dir. |
| `plan RUN_DIR [--review-only]` | **real (E)** | Deterministic planner: 5 `context/` files + `tasks/TASK-*.yaml` from manifest metadata only. |
| `dispatch RUN_DIR [--task ID] [--agent-profile P] [--evidence DIR]` | **real (F)** | Runs each contract's tool; writes results + claims + `agent_calls`. |
| `collect RUN_DIR [--task ID]` | **real (F)** | Validates each result envelope; flags missing/malformed without crashing. |
| `critique RUN_DIR [--evidence DIR] [--followups/--no-followups]` | **real (G)** | One critic verdict per task; routes claims; contradictions; downgrades; injection consequence; coverage-gap follow-ups. |
| `retry RUN_DIR TASK-ID` | **real (G)** | Re-critique one task → `decide()`; if retry, tighten the contract + re-dispatch at attempt+1. |
| `decompress RUN_DIR --archive REL [--evidence DIR]` | **real (D-H, `b2m.1`)** | Decompress a memory archive (zip/7z) → `evidence/extracted/` derived image (custody-tracked). |
| `ingest-derived RUN_DIR [--evidence DIR]` | **real (H, `hth.2`)** | Make carved/decompressed derived artifacts plannable — one derived task each (resolves under the run dir; manifest untouched). |
| **`run CASE_DIR --evidence DIR [--mode M] [--review-only] [--auto-human-loop] [--auto] [--max-iterations N]`** | **real (H)** | One deterministic engine: init → plan → dispatch → collect → critique → decide → report → done. |
| **`resume RUN_DIR`** | **real (H)** | Reload `RunState`, continue from the current state (crash-safe). |
| **`status RUN_DIR`** | **real (H)** | Print state / mode / iteration / gates / per-task attempts. |
| **`approve RUN_DIR --gate G`** | **real (H)** | Approve a blocked gate (plan/dispatch/retry/report) + resume the engine. |
| **`reject RUN_DIR --gate G`** | **real (H)** | Reject a blocked gate; the run halts cleanly. |
| `doctor [--protocol-sift]` | **real (A/D)** | Verify host + every backend; fail closed; allowlist = 10. |
| `mcp-serve` | **real (D)** | FastMCP stdio gateway exposing exactly the 10 tools. |
| `extract-artifacts … --image …` / `analyze-memory … --memory …` | **real (D)** | Sleuthkit disk-image extraction / Volatility 3 memory triage (audited). |
| `protocol-sift inspect [--run-dir D]` / `protocol-sift skills list` | **real (D11)** | Inspect & govern the `~/.claude` Protocol SIFT layer. |
| `report` / `replay` | stub (J) | Final forensic report / replay (the REPORT state is the Epic-J seam). |
| `tasks` / `claims` / `audit` | stub (debug) | Inspection sub-commands. |

---

## 4. The run-directory contract (`case_runs/RUN-YYYYMMDD-HHMMSS/`)

```
run_state.json                                  ← Epic H: durable state-machine snapshot (atomic)
context/   case_brief.md  context_pack.md  investigation_plan.yaml  tool_map.md  assumptions.md
           evidence_policy.md  protocol_sift_capabilities.json  mcp_config.json
evidence/  evidence_manifest.json  hashes.sha256  readonly_mounts.json
           derived_artifacts.json  custody_log.jsonl   extracted/ (carved/decompressed derived files)
tasks/     TASK-001.yaml …                      (task contracts — E; follow-ups — G)
results/   TASK-001.result.json …               (executor envelopes — F)
           TOOL-NNN.structured.json / .raw.json (tool provenance payloads — D)
claims/    claim_ledger.jsonl  unsupported_claims.jsonl  injection_alerts.jsonl
           contradiction_ledger.jsonl  confidence_changes.jsonl                (G)
audit/     tool_calls.jsonl  agent_calls.jsonl  orchestration_events.jsonl
           critic_verdicts.jsonl  retries.jsonl  followups.jsonl               (G)
           token_budget.jsonl                                                  ← Epic H (budget router)
reports/   (final_report.md … — Epic J)
```
Every write routes through `evidence/path_policy.safe_write_path` (rejects traversal, run-dir escape,
and writes into the original evidence tree). Originals are never modified. `run_state.json` is rewritten
atomically (temp file → `flush`/`os.fsync` → `Path.replace`) on every transition.

---

## 5. Feature summary by epic

- **Epic A — Project skeleton & config (closed, 55 tests):** `uv` package, Typer CLI, `RunPaths`
  generator, structlog JSONL logging, `SiftmeshSettings`, `doctor`.
- **Epic B — Evidence vault (closed, 34 tests):** real `init-case` — streaming SHA-256 → manifest +
  `sha256sum -c` hashes + readonly posture + chain-of-custody; `safe_write_path` gate.
- **Epic C — Schemas & ledgers (closed, 41 tests):** Pydantic v2 typed layer — `ToolResult`, `Claim`
  (the hallucination firewall), `TaskContract`, `CriticVerdict`, `RunState`, manifest, custody;
  validate-before-write JSONL ledgers.
- **Epic D — Typed MCP gateway (closed, 68 tests):** exactly **10** typed, audited, fail-closed
  forensic tools over FastMCP (evtx/prefetch/registry/timeline in-process; disk-image via Sleuthkit;
  memory via Volatility 3 subprocess — VSL never imported). Includes the `decompress` CLI (GAP 1,
  `b2m.1`) over the tested `memory_access.decompress`.
- **Epic E — Planner & Deep Context (closed, 42 tests):** deterministic `siftmesh plan` — context files
  + task contracts from manifest metadata only; `artifact_router` family→tool routing; investigation
  plan acyclic step graph.
- **Epic F — Executor adapters (closed, 31 tests):** `ExecutorAdapter` ABC + registry (fall-closed to
  the floor); deterministic real-tool executor → anchored Claims; spotlight + injection alerts;
  `dispatch`/`collect`; agent_calls audit; claude/opencode thin adapters (live human-gated).
- **Epic G — Critic & Self-Correction (closed, 35 tests):** deterministic `critique` + pure `decide()`
  truth table + retry generation + coverage/corroboration gap follow-ups (see `epic_g_feature_sofar.md`).
- **Epic H — Ultraworker State Machine (core complete, 25 tests; node open):** detailed below.

---

## 6. Epic H deep-dive — the deterministic Ultraworker state machine

Epic H turns the Epic E/F/G stages into **one deterministic engine** with crash-safe resume, approval
gates, caps enforcement, and replayable transition audit. New modules in `siftmesh_core/orchestrator/`:

### 6.1 `RunState` + atomic persistence (H1) — `run_state_store.py`, `schemas/run.py`
`RunState` (extended from the Epic-C stub) is the single source of orchestration truth: `run_id`,
`state`, `mode`, `iteration`, `max_iterations`, `per_task` (`PerTaskState{attempt, max_attempts,
status}`), `pending_dispatch`, `gates`, `blocked_gate`, `terminal`. `write_run_state` persists it
**atomically** — a temp file in the run dir is written, `flush`ed + `os.fsync`'d, then `Path.replace`
swaps it in (atomic rename). A reader (or a resumed run after a crash) always sees a complete, valid
snapshot, never a partial write. Validate-before-write via Pydantic.

### 6.2 Transition table + engine (H2) — `state_machine.py`
A **frozen** `TRANSITIONS: dict[RunStateName, frozenset[...]]`:
```
init → create_evidence_vault → deep_context → plan → dispatch → collect → critique → decide
plan → done            (review-only)
decide → dispatch       (retry / follow_up, iteration++)
decide → report → done  (done)
decide → decide         (escalate / human_review → halt awaiting a human)
```
`step(current, target)` raises `IllegalTransitionError` if the target is not in the table; `next_state()`
computes the natural successor (incl. the `plan` review-only short-circuit and the `decide` branch).
**Pure, no I/O — the authoritative legality oracle.**

### 6.3 Workflow runner (H3) — `workflow_runner.py` + `ultraworker.py`
`run_engine(run, *, settings, evidence_root=None, single_step=False)` loops: execute the current
state's stage (`generate_plan` → `dispatch_run` → `collect_run` → `critique_run` → DECIDE → report seam),
persist `RunState` + log one orchestration event per transition, and stop on terminal / gate / single
step. `ultraworker.aggregate_decision` reads the **persisted** critic-verdict ledger and folds the
per-task `decide()` outcomes into one run-level action by precedence
**human_review > escalate > retry > follow_up > done** (so the choice is identical on a resumed run).

### 6.4 Caps enforcement (H4)
Two **distinct counters**: the global `iteration` (self-correction loop) is checked before each loop —
once `iteration >= max_iterations` the engine halts (`cap_reached`), so it **never loops unbounded**;
the per-task `attempt` is enforced by pure `decide()` (`attempt >= max_attempts` → escalate, not retry).
`max_agent_tasks` is enforced by `dispatch_run` (raises `CapError`); dispatch is sequential
(`max_parallel_tasks` recorded, never exceeded — parallelism is roadmap).

### 6.5 Approval gates + approve/reject (H5) — `human_gate.py`, `cli.py`
Four meaningful gates (plan/dispatch/retry/report) guard entry to sensitive states. In guided mode the
engine halts on a pending gate, persists `blocked_gate`, and exits; `siftmesh approve … --gate G` records
the approval and resumes the engine; `reject` halts the run cleanly. Auto mode auto-passes gates; manual
single-steps; review-only never reaches dispatch.

### 6.6 `siftmesh run` modes + review-only enforcement (H6 / `hth.1`)
One config-driven engine; the mode (and the CLAUDE §4 flags, which win over `--mode`) sets the policy:
- **manual** — one transition per `run`/`resume` call (true single-stepping; complements the staged commands).
- **review-only** — `generate_plan(review_only=True)`, then `plan → done`; **dispatch unreachable**, no `results/`.
- **auto-human-loop (guided)** — run automatically, halt at the four meaningful gates for `approve`.
- **auto** — run to terminal; enforce caps; no gates.

### 6.7 Resume + status (H7)
`resume RUN_DIR` reloads `RunState` and continues from `current_state` (single-step if manual);
`status RUN_DIR` prints state/mode/iteration/gates/per-task attempts (read-only).

### 6.8 Orchestration audit (H8)
The runner emits one `orchestration_events.jsonl` line per transition/decision/gate/cap
(`state_enter`/`transition`/`decision`/`gate_blocked`/`gate_approved`/`gate_rejected`/`cap_reached`/
`run_complete`); retries are recorded by `write_retry` (G5). A real `--auto` run emits 9 transitions +
`run_complete` — the run is fully reconstructable from the log.

### 6.9 Budget router (H9, MVP-light) — `budget_router.py`
`select_profile(base, *, escalate)` over a static cheap→strong map (the deterministic floor maps to
itself — an honest no-op, no fake escalation); on a retry the runner records the routing decision to
`audit/token_budget.jsonl`. Cost-based routing + a real strong tier land with Epic I (`agent_profiles.yaml`).

### 6.10 Derived re-ingest (hth.2) — carved/decompressed artifacts become plannable
The planner reads only the intake manifest, but `extract_artifacts_from_image` and `decompress` write
*derived* files into `run/evidence/extracted/`. hth.2 makes them first-class plannable inputs **without
mutating `evidence_manifest.json`** (forensically correct: ISO/IEC 27037 / NIST SP 800-86 treat
Examination/Analysis outputs as provenance-linked new evidence, distinct from the Collection seal).
- **`InputArtifact.origin`** (`evidence` | `derived`; default `evidence`) — a `derived` input's path is
  run-relative and resolves under the **run dir**. The deterministic executor picks the root per input
  (`ctx.run.root` for derived, else the evidence root); `run_tool` normalises the write-exclusion so a
  derived task (whose `evidence_root` *is* the run dir) can still write its own outputs.
- **`detect_derived_gaps` + `ingest_derived`** (`critic.py`) — read `derived_artifacts.json`, route each
  derived file by basename (a `DECOMP-` image is forced to `memory_image` because a `.raw` suffix would
  otherwise look like a disk image), and mint one `origin="derived"` task per uncovered actionable file.
- **CLI** `siftmesh ingest-derived RUN_DIR` is the explicit step; the **engine does it autonomously** —
  `critique_run`'s G9 follow-up generator now raises `derived_gap` follow-ups, so `run --auto` over a
  `.E01` drives *extract → (critique sees carved files) → follow_up → dispatch the derived tasks → …*
  through the existing `decide → follow_up` loop, **no engine change**. Provenance stays unbroken:
  `claim → tool_call → derived file (sha) → derived_artifacts.json → source image (sha + inode)`.

### 6.11 §2B boundary (what is deferred, and why)
- **REPORT state = Epic J seam.** The forensic report (`final_report.md`/`accuracy_report.md`) is Epic J
  (spine order H→K→J). The engine reaches `report → done` and logs `report_pending`; `run` tells the
  user to run `siftmesh report`. No fake report.
- **Hero self-correction demo = Epic K.** The engine *implements* the retry/follow_up/escalate/
  human_review loop correctly; the demoable under-specified→retry→corrected scenario is Epic K (K3). The
  clean deterministic floor yields all-`accepted` verdicts, so tests force the loop branches via targeted
  decisions, not a manufactured demo.
- **Full image/memory `run --auto` is host-gated.** The derived-ingest wiring is validated in CI with a
  synthetic derived registry + a real EVTX placed in `evidence/extracted/`; the end-to-end `.E01`/memory
  run needs the SANS box (Sleuthkit/Volatility) and the maintainer's evidence.

---

## 7. How to run it (commands)

The full deterministic pipeline — **no API keys needed** (the floor runs real tools over real artifacts):

```bash
uv run siftmesh doctor                                    # verify host + backends (fails closed)

# One-shot automation (the recommended demo mode):
uv run siftmesh run ./case01 --evidence ./evidence --auto-human-loop   # halts at the plan gate
uv run siftmesh status ./case01/case_runs/RUN-*                         # inspect the state machine
uv run siftmesh approve ./case01/case_runs/RUN-* --gate plan            # approve + resume
uv run siftmesh run ./case01 --evidence ./evidence --auto --max-iterations 3   # run to completion
uv run siftmesh run ./case01 --evidence ./evidence --review-only        # plan only, no dispatch
uv run siftmesh resume ./case01/case_runs/RUN-*                         # continue an interrupted run

# Or the equivalent manual staged pipeline (identical artifacts):
uv run siftmesh init-case ./case01 --evidence ./evidence
RUN=./case01/case_runs/RUN-*
uv run siftmesh plan "$RUN" && uv run siftmesh dispatch "$RUN" \
  && uv run siftmesh collect "$RUN" && uv run siftmesh critique "$RUN"

# Disk image / memory (Epic D, audited, fail-closed):
uv run siftmesh extract-artifacts "$RUN" --image disk.E01 --evidence ./evidence
uv run siftmesh decompress "$RUN" --archive Memory.zip --evidence ./evidence   # zip/7z → derived image
uv run siftmesh analyze-memory "$RUN" --memory evidence/extracted/mem.raw --evidence "$RUN"

# Expose the typed tools to an MCP agent (10 tools, no raw shell):
uv run siftmesh mcp-serve
```

**Live agent (F8) — human-gated, requires keys + CLI:** `export ANTHROPIC_API_KEY=…` then
`uv run siftmesh dispatch "$RUN" --agent-profile claude_headless` (falls closed to the floor if absent).

---

## 8. Configuration knobs (`SiftmeshSettings`, env `SIFTMESH_…` / `siftmesh.toml`)

`backend_mode` · `evidence_mode=read_only` · `raw_shell=False` · `allow_destructive_tools=False` ·
**`caps.{max_iterations,max_agent_tasks,max_parallel_tasks,max_tool_runtime_seconds}`** (enforced by the
Epic-H engine) · `extraction_tools_enabled` · `vol_path` · `vol_symbol_dirs` · `ez_tools_dir` ·
`executor_selection` (deterministic/live/auto; deterministic default) · `default_agent_profile` ·
`claude_cli_path` · `opencode_cli_path` · `generic_agent_cmd` · `agent_timeout_seconds` ·
`llm_critic_enabled`. `siftmesh run --max-iterations N` overrides `caps.max_iterations` per run. Nested
caps via `SIFTMESH_CAPS__MAX_ITERATIONS=7`.

---

## 9. Testing & quality gates

- **339 tests pass**, per epic under `tests/EPIC_<X>_TESTS/` (unique basenames; no `__init__.py`):
  **A=56, B=34, C=41, D=68, E=42, F=31, G=35, H=32.**
- **CI-safe & real:** real tools over **committed public fixtures** in `tests/fixtures/forensic/` (never
  SANS evidence); subprocess/agent boundaries mocked; no API keys. Epic H tests build a real run
  (manifest + readonly + `RunState`) and drive `run_engine` over the real fixtures; the cap test
  monkeypatches the *decision aggregation* (engine logic) to force a retry — the forensic tools stay real.
- **Gates (all green):** `uv run ruff check . && uv run ruff format --check . && uv run mypy &&
  uv run pytest && uv run siftmesh doctor` (89 source files; allowlist=10).
- **Epic H validation:** `siftmesh run --auto` over the fixtures reaches `done` (4 real tasks, all
  success), writes `run_state.json`, logs 9 transitions; `--review-only` ends at plan with no `results/`;
  `--auto-human-loop` halts at the plan gate → approve continues → halts at report gate → approve → done;
  reject halts cleanly; resume-from-mid-run reaches done; manual and auto produce identical artifacts;
  the transition table has legal/illegal tests; the global-iteration cap stops a forced retry loop.

---

## 10. Hard rules / invariants (enforced)

- **REAL-ONLY**; missing backend fails closed. **Allowlist = exactly 10**; forbidden tools never register.
- **Volatility 3 is VSL → subprocess-only, never imported** (guard test).
- **No writes outside the run dir**; never modify/commit/CI SANS evidence; evidence treated as hostile.
- **Deterministic engine** — the transition table + `decide()` are pure and authoritative (no LLM in the
  engine); every transition is validated through `step()`.
- **Crash-safe** — `RunState` persisted atomically (temp+fsync+rename) every transition.
- **No unbounded loop** — the global `iteration` cap always halts the self-correction loop; two distinct
  counters (global `iteration` vs per-task `attempt`).
- `decide()` and the transition table are **pure**. **No AI co-authorship** on any commit.
- **Live agent self-correction is human-gated** — never run autonomously. **Strictly sequential epics**;
  only a human closes an epic node (the `hth` node is left open).

---

## 11. What's next — Epic K (after the human closes `hth`)

Closing the Epic H node (`bd close Project_SIFTAMESS-hth`) unblocks **Epic K — Demo Case &
Self-Correction Scenario** (the next on the spine `H → K → J`): a real demo dataset + ground truth and
the genuine under-specified→retry→corrected hero sequence the engine now supports. **Epic J** (Reports &
Replay) follows K and fills the REPORT-state seam (`final_report.md` / `accuracy_report.md` / `replay`).
Epic H is now **fully complete** — including `hth.2`, so `siftmesh run` drives image/memory cases
end-to-end (extract → derived follow-ups → dispatch) without a second `init-case`.

```
A✓  B✓  C✓  D✓  E✓  F✓  G✓  H✓ (all children closed; gate open)  →  K  J  L  M  N  I  P  O
```

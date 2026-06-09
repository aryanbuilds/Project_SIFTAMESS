# Epic H — Ultraworker State Machine & `siftmesh run` (work, commands & features so far)

_Status: 2026-06-09. Epic H core (H1–H9 + review-only enforcement) shipped; node `Project_SIFTAMESS-hth`
left OPEN for the human. `hth.2` (derived re-ingest) remains the one open child. 331 tests green;
ruff/format/mypy clean (89 source files); `doctor` allowlist = 10._

## 1. What Epic H delivers

Epic H turns the already-built stages (`generate_plan` → `dispatch_run` → `collect_run` →
`critique_run` → `decide`) into a single **deterministic state machine** with crash-safe resume,
approval gates, caps enforcement, and replayable transition audit. **The CLI is the source of truth;
the LLM proposes, deterministic code decides** — there is no LLM in the engine.

State machine (frozen transition table):

```
init → create_evidence_vault → deep_context → plan → dispatch → collect → critique → decide
                                                │                                        │
                                       (review_only) → done           ┌─ done → report → done
                                                                      ├─ retry/follow_up → dispatch (loop, iteration++)
                                                                      └─ escalate/human_review → halt (awaiting human)
```

## 2. New modules (`siftmesh_core/orchestrator/`)

| Module | Task | Responsibility |
|---|---|---|
| `run_state_store.py` | H1 | Atomic `RunState` persistence — temp file + `flush`/`os.fsync` + `Path.replace` (atomic rename); read/exists. Crash-safe: a reader/resumed run always sees a complete snapshot. |
| `state_machine.py` | H2 | Frozen `TRANSITIONS` map + pure `step()` (rejects illegal transitions) + `next_state()` (linear spine + `decide` branch). The authoritative legality oracle. |
| `workflow_runner.py` | H3–H6, H8 | `run_engine(...)` drives the machine, calls each stage, enforces caps, honours gates, persists + logs one event per transition. |
| `ultraworker.py` | H3 | `aggregate_decision(...)` folds per-task `decide()` outcomes into one run-level action (human_review > escalate > retry > follow_up > done), reading verdicts from the persisted ledger. |
| `human_gate.py` | H5 | `set_gate(run, gate, status)` records an approve/reject into durable state. |
| `budget_router.py` | H9 | `select_profile(...)` static cheap→strong escalation + `record_routing(...)` → `audit/token_budget.jsonl` (MVP-light; deterministic floor maps to itself, no fake escalation). |

`schemas/run.py` `RunState` extended (Epic-C deferral): `mode`, `max_iterations`, `per_task`
(`PerTaskState{attempt,max_attempts,status}`), `pending_dispatch`, `gates`, `blocked_gate`, `terminal`.

## 3. Commands (now real)

```bash
siftmesh run CASE --evidence EV --mode manual          # one transition per call (single-step)
siftmesh run CASE --evidence EV --review-only          # plan + recommendations; DISPATCH unreachable
siftmesh run CASE --evidence EV --auto-human-loop      # run until a meaningful approval gate
siftmesh run CASE --evidence EV --auto --max-iterations 3   # run to terminal; caps enforced; no gates
siftmesh resume RUN_DIR                                 # reload RunState, continue from current_state
siftmesh status RUN_DIR                                 # print state/mode/iteration/gates/per-task attempts
siftmesh approve RUN_DIR --gate plan                    # approve a blocked gate + resume the engine
siftmesh reject  RUN_DIR --gate retry                   # reject a blocked gate; the run halts cleanly
```

Mode → policy: **manual** single-steps (one transition per `run`/`resume`); **review_only** stops after
PLAN; **auto_human_loop** halts at the four meaningful gates (plan/dispatch/retry/report) for `approve`;
**auto** runs to terminal with caps. Approval flags (`--review-only`/`--auto-human-loop`/`--auto`) win
over `--mode`.

## 4. Governance & safety (criteria 1/4/5)

- **Deterministic & pure** — the transition table + `decide()` are pure; an illegal successor can never
  be returned (`step()` asserts every transition). No LLM in the engine.
- **Crash-safe** — `RunState` persisted atomically every transition → `siftmesh resume` continues
  exactly where a killed run stopped (verified: interrupt mid-run → resume → DONE).
- **Caps, never unbounded** — global `iteration` cap halts the self-correction loop; per-task `attempt`
  cap escalates (two distinct counters); `max_agent_tasks` enforced by `dispatch_run`.
- **Human gates** — guided mode blocks at the four gates and persists; `approve` resumes, `reject` halts.
- **Replayable audit** — one `orchestration_events.jsonl` line per transition/decision/gate/cap; a real
  `--auto` run emits 9 transitions + `run_complete`.

## 5. Verified end-to-end (committed fixtures, no keys)

`siftmesh run <case> --evidence <ev> --auto` over the public fixtures (Security.evtx + prefetch +
NTUSER.DAT) reaches `done` with 4 real tasks (all success), writes `run_state.json`, and logs 9
transitions; `siftmesh status` reads it back. `--review-only` ends at plan with no `results/`;
`--auto-human-loop` halts at the plan gate → `approve --gate plan` → halts at report gate → `approve
--gate report` → done. The deterministic floor runs the real Epic-D tools (no mocks).

## 6. Deferred / next

- **REPORT state = Epic J seam** — the forensic report (`final_report.md`/`accuracy_report.md`) is Epic
  J (spine order H→K→J). The engine reaches `report`→`done` and logs `report_pending`; `run` tells the
  user to run `siftmesh report` (Epic J).
- **Hero self-correction demo = Epic K** — the engine implements the retry/follow_up/escalate loop; the
  demoable under-specified→retry→corrected scenario is Epic K (K3).
- **`hth.2` (open)** — re-ingest extracted/decompressed derived artifacts into the plannable input set
  (the manifest-vs-derived seam), so `run` drives image/memory cases end-to-end. P2; custody-sensitive
  (derived inputs kept distinct from the intake manifest).

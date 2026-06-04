# PLAN 04 — Orchestration Core & Self-Correction (Epics E, F, G, H)

_Phases 5–8 of the build, and the heart of the product. The deterministic state machine, the Planner, the Executor adapters, and — the **hero** — the Critic and self-correction loop. Serves criteria 1 (autonomous execution / self-correction — the **tiebreaker**), 2 (accuracy), 4 (constraints), 5 (audit)._

---

## Three architectural commitments (the load-bearing decisions)

**(C1) One engine; modes are config.** Exactly one state-machine engine (`orchestrator/state_machine.py`) with one frozen transition table. The four modes (`manual`, `review-only`, `auto-human-loop`, `auto`) are a `RunConfig` over three knobs: which gates are active, whether `DISPATCH` is reachable (review-only halts after PLAN), and the caps. **Manual = advance one transition per CLI call**; auto = advance until a gate or terminal state. Same transition code ⇒ manual artifacts equal auto artifacts (GUIDELINES §4.1).

**(C2) LLM proposes, deterministic code decides.** Five enforcement points where a hardcoded check can reject an LLM suggestion and log it:
1. **Transition legality** — frozen `TRANSITIONS: dict[State, set[State]]`; illegal proposal → `illegal_transition_rejected` in `orchestration_events.jsonl`.
2. **DECIDE table** — `orchestrator/decide.py` is a *pure function* implementing CLAUDE.md §12 verbatim (done/retry/escalate/human). No LLM in this path.
3. **Caps** — enforced in `workflow_runner.py` before every DISPATCH and iteration bump.
4. **Critic structural checks** — deterministic parse + checks before any LLM reasoning.
5. **Path/tool policy** — adapters refuse any tool not in the contract's `allowed_tools` and any out-of-run-dir write (reuses Epic B path policy).

**(C3) The self-correction hero is deterministic real-tool execution.** The guaranteed demo path uses the **deterministic real-tool executor** running the in-process MVP tools (`evtx`/`regipy`/`pyscca`/`mft` + own-code; see PLAN/08_REAL_TOOL_STACK.md §3) over **real committed evidence**. The "mistake" the hero corrects is a genuinely under-specified first-pass task contract — its `success_criteria` does **not yet** require binding `source_sha256` + `tool_call_id`, so the real tool's real claim genuinely lacks the required evidence binding. Every arrow in the correction chain is deterministic code over real tool output → reproduces every run, no live model, no randomness, cannot fail in the demo. Live agents swap in behind the same adapter interface as a best-effort upgrade.

---

## The hero sequence (designed so it cannot fail) — MVP, not stretch

```
Iteration 1 · TASK-002 attempt 1
  real-tool executor reads tasks/TASK-002.yaml (first-pass, under-specified contract)
  real in-process tool runs over the real committed evidence (e.g. evtx_security)
   → results/TASK-002.result.json with a real claim that genuinely lacks
     the required evidence binding (no tool_call_id) — because the contract's
     success_criteria did not yet make that binding mandatory
   → agent_calls.jsonl {attempt:1, contract:"under_specified", backend:"real"}

critique
  critic Layer-1 structural check: claim missing tool_call_id (deterministic)
   → CriticVerdict = retry_required, affected_claim_ids=[CLAIM-003]
   → unsupported_claims.jsonl + confidence_changes.jsonl

DECIDE (pure fn, CLAUDE.md §12)
  result-missing-reference & attempts(1) < max_attempts(2) → RETRY
   → retry contract TASK-002 attempt 2 (tightened success_criteria:
     "claim MUST include tool_call_id + source_sha256")
   → retries.jsonl + orchestration_events.jsonl

Iteration 1 · TASK-002 attempt 2
  real-tool executor re-runs the SAME real tool over the SAME real evidence
  under the tightened contract → emits the binding it is now required to
   → corrected claim WITH tool_call_id + source_sha256 + supporting_evidence_refs

critique
  all structural checks pass → accepted → promoted to claim_ledger.jsonl (confirmed)

report
  final_report.md: corrected evidence-backed claim
  accuracy_report.md: logs the rejected attempt-1 claim + the self-correction event
```

**Guaranteed path = the under-specified-contract → retry over REAL tool output** (simplest, most reliable; same real tool, same real evidence, only the contract tightens). **Stretch (marked, isolated): contradiction → escalate** (two real tools producing mutually contradictory rows across two tasks → `escalation_required` → DECIDE escalate). Stretch must never block the guaranteed path.

---

# EPIC E — Planner & Deep Context Agent

**Goal:** Produce a useful investigation plan and task contracts **deterministically**, so `plan` works with no live LLM. **Criteria:** 3 (breadth), 5 (audit), 6 (usability), 4 (privilege separation — planner proposes, never executes). **Deps:** A (run dir, CLI), B (manifest), C (TaskContract). Consumed by F, G, H.

| Task | Title | Description | Key files | Deps | Acceptance | Role | Eff | Risk |
|---|---|---|---|---|---|---|---|---|
| E1 | `plan` command | `siftmesh plan RUN_PATH [--review-only]`; load run dir/manifest/config; orchestrate E2–E6; log `plan_started/complete`. | `cli.py`, `orchestrator/planner.py` | A,B,C | `siftmesh plan RUN-001` exits 0, writes 5 context files + ≥2 task contracts. | Planner | M | low |
| E2 | Deep Context Agent (deterministic) | `context/context_pack.md` from manifest (case type, artifact families present, per-family tool guidance); LLM enrichment behind flag. | `orchestrator/deep_context.py`, `planner.py` | B | context_pack names every evidence family in manifest; no instruction echoed from evidence (spotlight check). | Deep Context | M | med (LLM optional) |
| E3 | Case brief + assumptions | `context/case_brief.md` (scope/objective/constraints) + `context/assumptions.md` (explicit assumptions, e.g. timezone). | `planner.py` | B | both exist; assumptions lists ≥1 explicit assumption. | Planner | S | low |
| E4 | Investigation plan YAML | `context/investigation_plan.yaml` — ordered step graph (deep_context, executor tasks per artifact, critique, report). | `planner.py`, `workflows/windows_initial_triage.yaml` | B,C | YAML parses; unique step ids; every executor step maps to a manifest artifact. | Planner | M | low |
| E5 | Tool map | `context/tool_map.md` mapping artifact families → allowed typed MCP tools (no raw shell). | `planner.py` | D | every tool listed is in the gateway allowlist; no forbidden tool. | Planner | S | low |
| E6 | Task contract generation | Emit `tasks/TASK-*.yaml` from template; each with all required fields, `allowed_tools` scoped per task, `safety_policy.evidence_is_hostile:true`, `write_allowed_only_under` run-dir paths. | `planner.py`, `schemas/task.py` | C | each `TASK-*.yaml` validates; missing `safety_policy` rejected at write. | Planner | M | low |
| E7 | Deterministic template `windows_initial_triage` | Fixed mapping: Security.evtx→evtx_security; powershell logs→evtx_powershell; Prefetch→prefetch; Run keys→registry. Zero-LLM. | `planner.py`, template data | C | with sample evidence, produces TASK-001..004 deterministically (byte-stable per manifest). | Planner | M | low |
| E8 | Review-only gate hook | `--review-only` sets `RunConfig.dispatch_reachable=false`; planner emits recommendations; engine stops after PLAN. | `planner.py`, `state_machine.py` | H1 | `test_review_only_stops_after_plan`: no `results/`; state ends at PLAN/DONE. | Planner | S | low (dep on H) |

**Design (E):** Deterministic templates per case type are the MVP path; an optional LLM Planner is a *post-processor* that may reorder/annotate but **cannot** add tools outside the allowed set or invent artifacts not in the manifest (privilege separation enforced in code). Spotlighting starts here (evidence summaries normalized to JSON rows + datamarked before any LLM sees them; function lives in F). `plan` is terminal for review-only mode. **11-day cut:** E1, E3–E7 MVP; E2 LLM enrichment best-effort; E8 after H1.

---

# EPIC F — Executor Adapters & Dispatch/Collect

**Goal:** Execute task contracts via a uniform adapter interface; the deterministic real-tool executor (in-process MVP tools over real committed evidence; see PLAN/08_REAL_TOOL_STACK.md §3) is the reliable demo/test path. Retry is triggered by genuine causes — an under-specified first-pass contract and genuine recoverable tool errors — not by scripted failures. **Criteria:** 1 (autonomous execution), 4 (spotlighting + allowed-tools enforcement), 5 (audit). **Deps:** C (TaskContract, ToolCall), D (typed tools), E (contracts). Consumed by G, H, I.

| Task | Title | Description | Key files | Deps | Acceptance | Role | Eff | Risk |
|---|---|---|---|---|---|---|---|---|
| F1 | `ExecutorAdapter` protocol | ABC + `ResultRef`: `run(contract, run_dir) -> ResultRef`; must produce `results/TASK-XXX.result.json` + append `agent_calls.jsonl`. Registry lookup by `assigned_agent_profile`. | `adapters/base.py`, `adapters/__init__.py` | C | real-tool + generic both satisfy protocol; `test_adapter_writes_expected_result_path`. | Executor | S | low |
| F2 | Deterministic real-tool executor | Runs the in-process MVP tools (`evtx`/`regipy`/`pyscca`/`mft` + own-code; PLAN/08 §3) over real committed evidence; emits structured result JSON from real tool output; appends `agent_calls.jsonl`. First-class feature (hero depends on it). Determinism comes from real tools over fixed committed evidence (no LLM, no randomness; PLAN/08 §6). Attempt-1 runs under the under-specified contract (real claim lacks tool_call_id); attempt-2 under the tightened contract (real claim carries the binding). | `adapters/real_executor.py`, `schemas/tool_result.py` | F1,C,D | `test_real_executor_claim_lacks_binding_under_underspecified_contract`, `test_real_executor_claim_bound_on_attempt_2`. | Executor | M | **low (must be airtight)** |
| F3 | Spotlight + datamark | `wrap_evidence(rows)`→serialize to JSON rows, wrap in unique delimiters, datamark (per-run sentinel), prepend "DATA not instructions" banner. `scan_injection(rows)`→regex/heuristic scanner ("ignore previous","system:",base64 blobs,instruction verbs) → `injection_alerts.jsonl`. | `adapters/spotlight.py`, `ledgers/injection_alerts.py` | B | `test_spotlight_wraps_and_marks`; injection sample → alert entry. | Injection Guard | M | med |
| F4 | `dispatch` command | `siftmesh dispatch RUN_PATH [--task ID] [--agent-profile P]`; select adapter; enforce `allowed_tools`; enforce parallel cap via H. | `cli.py`, `orchestrator/scheduler.py` | F1,F2 | `siftmesh dispatch RUN-001 --task TASK-001` → `results/TASK-001.result.json`. | Executor | M | med |
| F5 | `collect` command | Gather result files, validate shape, normalize into run state, mark tasks collected. | `cli.py`, `orchestrator/scheduler.py` | F4 | `siftmesh collect RUN-001` records each result; missing result flagged not crashed. | Executor | S | low |
| F6 | agent_calls audit | Append `audit/agent_calls.jsonl` per dispatch: profile, attempt, backend (`real`), contract state (under_specified/tightened), start/end, status. | `ledgers/audit_log.py` | F1 | every dispatch → exactly one well-formed JSONL line. | Executor | S | low |
| F7 | generic_shell_adapter | Write task prompt to file, invoke shell agent, expect result file at known path; timeout = `max_tool_runtime_seconds`. | `adapters/generic_shell_adapter.py` | F1 | echo-script agent → conformant result; absent agent → graceful fallback error. | Executor | M | med |
| F8 | Claude/OpenCode headless adapters (best-effort) | `claude -p "..." --output-format json`; OpenCode server mode. Parse JSON, write result file. | `adapters/claude_adapter.py`, `adapters/opencode_adapter.py` | F1,F7 | if CLI present → conformant result; if absent → log `adapter_unavailable`, fall back to the deterministic real-tool executor (F2). | Executor | L | **high (env-dependent)** |
| F9 | Genuine retry-trigger plumbing | Surface the two genuine retry causes to critic/DECIDE: (a) the under-specified first-pass contract (real claim lacks the required binding) and (b) genuine recoverable tool errors surfaced inline by the real libs (e.g. `mft.entries()` yields `RuntimeError` instances inline → type-check, don't raise; a malformed/unreadable record → recoverable tool error, not a crash; PLAN/08 §3). No scripted/injected failures. | `adapters/real_executor.py` | F2 | `test_retry_created_for_recoverable_tool_error` (with G) passes e2e. | Executor | S | low |

**Design (F):** The `ExecutorAdapter` protocol is the seam (real-tool/shell/claude/opencode/cao all implement it; demo runs on the deterministic real-tool executor; live agents swap in with zero engine change). The real-tool executor over real committed evidence is a first-class feature, not a test stub — its determinism comes from real tools over fixed committed evidence (no LLM, no randomness; PLAN/08 §6), and the retry it exercises is driven by genuine causes (under-specified contract + genuine recoverable tool errors), never scripted ones. Spotlighting + injection scanning live here and are called by E (prompts) and G (critic hook). Privilege/structural separation: adapter refuses any `tool_name` not in `allowed_tools`; tool output is parsed deterministically and **cannot** alter control flow. **11-day cut:** F1–F6, F9 MVP; F7 MVP-light; **F8 best-effort/stretch — demo never depends on it.**

---

# EPIC G — Critic & Self-Correction Loop (HERO)

**Goal:** Validate results/claims against evidence discipline, emit verdicts, feed deterministic DECIDE rules. **Criteria:** the tiebreaker (1), 2 (accuracy/hallucination), 4 (architectural guardrails), 5 (audit). **Deps:** C (Claim, CriticVerdict), F (results), E (contracts), D9 (`validate_claim_evidence`). Consumed by H.

| Task | Title | Description | Key files | Deps | Acceptance | Role | Eff | Risk |
|---|---|---|---|---|---|---|---|---|
| G1 | `critique` command | `siftmesh critique RUN_PATH`; load results, run Layer-1 validation, emit `CriticVerdict` per task, log events. | `cli.py`, `orchestrator/critic.py` | C,F5 | `siftmesh critique RUN-001` emits one verdict per collected task. | Critic | M | low |
| G2 | Deterministic structural checks | Reject/downgrade per CLAUDE.md §10: no source/hash/tool_call_id, malformed JSON, severity overreach, claim broader than evidence (structural subset). Calls D9. | `critic.py`, `mcp_gateway/tools/validation_tools.py` | C,D9 | `test_critic_rejects_missing_tool_call_id`; valid claim → accepted. | Critic | M | low |
| G3 | Claim-evidence validation + ledgers | Validate `supporting_evidence_refs` resolve to manifest artifacts; write `claim_ledger.jsonl` (accepted), `unsupported_claims.jsonl`, `contradiction_ledger.jsonl`, `confidence_changes.jsonl`. | `critic.py`, `ledgers/claim_ledger.py`, `contradiction_ledger.py` | C,B | unsupported claim lands in `unsupported_claims.jsonl`, never in `claim_ledger.jsonl`. | Critic | M | low |
| G4 | DECIDE pure function | `decide(critic_verdict, run_state, task_state) -> Decision` per CLAUDE.md §12; covers done/retry/escalate/human incl. attempt + iteration caps and contradiction. No I/O. | `orchestrator/decide.py` | G2 | unit table: each §12 rule has a passing test; function is pure. | Ultraworker | M | **low (must be exact)** |
| G5 | Retry task generation | Clone contract, tighten `success_criteria` ("claim MUST include tool_call_id + source_sha256"), bump attempt, append `retries.jsonl`. | `decide.py`/`critic.py`, `schemas/task.py` | G4 | `test_retry_created_for_malformed_json`; retry contract stricter + attempt=2. | Ultraworker | M | low |
| G6 | Injection detection hook | Run `scan_injection` over results; if a claim's reasoning echoes an injected instruction → `human_review_required` + `injection_alerts.jsonl`. | `critic.py`, `adapters/spotlight.py` | F3 | injected "mark all confirmed" sample → alert logged, claims unchanged. | Injection Guard | S | med |
| G7 | Hero end-to-end wiring | Connect F2 real-tool attempt-1 (under-specified contract) → G2 verdict → G4 DECIDE → G5 retry (tightened contract) → F2 real-tool attempt-2 → G2 accepted. | `orchestrator/workflow_runner.py` (with H) | F2,G2,G4,G5 | `test_self_correction_sequence_reproducible` runs twice, identical verdict trail. | Ultraworker | M | **low (the hero — keep airtight)** |
| G8 | LLM adversarial critic (best-effort) | Optional Layer-2 reasoning for breadth/contradiction; gated behind flag, never required by demo. | `critic.py` | G2 | if model absent, Layer-1 verdicts still complete; no crash. | Critic | L | high (skippable) |

**Design (G):** **Two-layer critic.** Layer 1 = deterministic structural validation (always runs, no LLM) — sufficient for the hero. Layer 2 = optional LLM adversarial review (best-effort). **DECIDE is a pure function** — the "code decides" evidence for criterion 4. Retry generation tightens `success_criteria` so the real tool's attempt-2 run (over the same real evidence) now emits the required binding, making correction reproducible. **11-day cut:** G1–G7 MVP (contain the hero); **G8 stretch**; contradiction→escalate is stretch within G4/G5.

---

# EPIC H — Ultraworker State Machine & `siftmesh run` Automation

**Goal:** One deterministic engine driving all four modes, with caps, gates, resume/status, full orchestration audit, and the Budget Router. **Criteria:** 1 (autonomous execution/self-correction), 4 (caps/guardrails), 5 (audit), 6 (usability). **Deps:** E, F, G.

| Task | Title | Description | Key files | Deps | Acceptance | Role | Eff | Risk |
|---|---|---|---|---|---|---|---|---|
| H1 | `RunState` schema + atomic persistence | Model: `run_id, current_state, mode, iteration, max_iterations, per_task{attempt,max_attempts,status}, caps_consumed, gates{plan,dispatch,retry,report:{status}}, terminal`. Persist atomically (temp+rename) on every transition to `run_state.json`. | `schemas/run.py`, `orchestrator/state_machine.py` | C | `test_runstate_roundtrip`; partial write never corrupts. | Ultraworker | M | **low (linchpin)** |
| H2 | Transition table + engine | Frozen `TRANSITIONS`; `step(run_state)->next_state`; illegal-transition rejection + log. | `orchestrator/state_machine.py` | H1 | `test_legal_transition_allowed`, `test_illegal_transition_rejected`. | Ultraworker | M | low |
| H3 | Workflow runner loop | Drive INIT→…→DONE; call E/F/G/decide; enforce caps before DISPATCH and on iteration bump. | `orchestrator/workflow_runner.py`, `ultraworker.py` | H2,E,F,G | full pipeline reaches DONE with hero correction on sample case. | Ultraworker | L | med |
| H4 | Caps enforcement | `max_iterations`, `max_agent_tasks`, `max_parallel_tasks`, `max_tool_runtime_seconds` checked in loop. | `workflow_runner.py`, `scheduler.py` | H3 | `test_auto_mode_stops_at_max_iterations` (global); `test_task_attempt_cap_escalates` (per-task). | Ultraworker | M | low |
| H5 | Approval gates + approve/reject CLI | Gates plan/dispatch/retry/report; `siftmesh approve/reject RUN --gate G`; blocked engine persists state + exits. | `orchestrator/human_gate.py`, `cli.py` | H1,H3 | `test_guided_mode_requires_approval_at_plan_gate`; reject halts cleanly. | Ultraworker | M | med |
| H6 | `siftmesh run` + modes | `--mode manual / --review-only / --auto-human-loop / --auto --max-iterations N`; one engine, config-driven. | `cli.py`, `workflow_runner.py` | H3,H4,H5 | all four CLAUDE.md §4 invocations run; manual artifacts == auto artifacts. | Ultraworker | M | med |
| H7 | `resume` + `status` | `resume` reloads `RunState`, continues from `current_state`; `status` prints state/gates/caps. | `cli.py`, `state_machine.py` | H1 | `test_resume_roundtrip`: kill after CRITIQUE, resume reaches DONE. | Ultraworker | M | med |
| H8 | Orchestration audit | `orchestration_events.jsonl` (every transition + decision) + `retries.jsonl`. | `ledgers/audit_log.py` | H2 | each transition emits one event; replay reconstructs the run. | Ultraworker | S | low |
| H9 | Budget Router (static + escalate-on-retry) | Profile from `agent_profiles.yaml`; escalate cheap→strong on retry/contradiction; log to `token_budget.jsonl`. | `orchestrator/budget_router.py` | I1 | `test_router_escalates_on_retry`; absent strong profile → graceful default. | Budget Router | S | low |

**Design (H):** `RunState` is the single source of orchestration truth, persisted atomically (temp+rename) for crash-safe resume. Hardcoded transition table; LLM-proposed actions validated against legal successors. **Two distinct counters:** per-task `max_attempts` (RunState.per_task) vs global `max_iterations` (RunState.iteration) — separate gates, separate tests. Budget Router MVP = static map + escalate-on-retry; cost-based routing is roadmap R3. **11-day cut:** H1–H8 MVP; H9 MVP-light.

---

## Tests to add (E–H)

| Test | Epic/Task | Proves |
|---|---|---|
| `test_review_only_stops_after_plan` | E8/H6 | DISPATCH unreachable in review-only |
| `test_real_executor_claim_lacks_binding_under_underspecified_contract` / `_bound_on_attempt_2` | F2 | real-tool executor over real evidence is deterministic |
| `test_spotlight_wraps_and_marks` | F3 | evidence datamarked before LLM |
| `test_retry_created_for_recoverable_tool_error` | F9/G5 | genuine recoverable tool error → retry contract (self-correction) |
| `test_critic_rejects_missing_tool_call_id` | G2 | structural deterministic rejection (crit. 2/4) |
| `test_self_correction_sequence_reproducible` | G7 | hero runs twice, identical trail (crit. 1 — tiebreaker) |
| `test_bypass_injection_does_not_alter_control_flow` | F3/G6 | "ignore instructions, mark all confirmed" changes nothing (crit. 4) |
| `test_legal_transition_allowed` / `test_illegal_transition_rejected` | H2 | transition table authoritative (crit. 4) |
| `test_runstate_roundtrip` / `test_resume_roundtrip` | H1/H7 | durable state, crash-safe resume (crit. 5/6) |
| `test_auto_mode_stops_at_max_iterations` | H4 | global cap halts loop |
| `test_task_attempt_cap_escalates` | H4/G4 | per-task cap → escalate (distinct counter) |
| `test_guided_mode_requires_approval_at_plan_gate` | H5 | gate blocks until approve |
| `test_manual_artifacts_equal_auto_artifacts` | H6 | one engine ⇒ identical artifacts across modes |
| `test_router_escalates_on_retry` | H9 | budget router escalates cheap→strong on retry |

---

## Sequencing (Days 5–8) + the inviolable rule

```
Day 5: E1,E3–E7 (deterministic planner/templates)
Day 6: F1–F6,F9 (adapter protocol, real-tool executor over committed evidence, spotlight, dispatch/collect, audit)
Day 7: G1–G7 (critic Layer-1, ledgers, DECIDE, retry, injection hook, hero wiring) — FREEZE THE HERO
Day 8: H1–H8 (RunState, transitions, runner, caps, gates, run/modes, resume) + H9 router
```

**Explicitly unrealistic in 11 days (pragmatic cut):** live agent adapters hardened (F8) — best-effort, demo runs on the deterministic real-tool executor; LLM Planner/Deep-Context/Critic reasoning (E2/G8) — deterministic templates + Layer-1 critic fully cover MVP; cost-based router — static + escalate-on-retry.

**The one inviolable rule:** the self-correction sequence (Epic G hero) depends on nothing nondeterministic. If the deterministic real-tool executor + under-specified contract (F2/F9; real tools over fixed committed evidence, no LLM/randomness — PLAN/08 §6) and the pure DECIDE function (G4) are airtight and frozen by Day 7, the graded tiebreaker is secured regardless of what else slips.

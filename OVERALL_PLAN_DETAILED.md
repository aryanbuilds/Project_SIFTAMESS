# OVERALL_PLAN_DETAILED.md

# SIFTMesh Detailed Build Plan

_Last updated: 2026-06-11 (Epics A–N core + L + M complete, **plus Epic Q** (agent-neutral connectors, `PLAN/13`) **and Epic O** (Textual cockpit + unified `setup`, `PLAN/14`)). Executed epic order: …H→I→K→J→L→M, then the maintainer-directed refinements. **ROCBA refinement:** autonomous objective-driven run in one command — `--brief`/`--objective` ingests the incident document as the TRUSTED objective (threaded into planner/agent-prompt/report), `run --auto` auto-decompresses+ingests archive evidence and quarantines a single critic-flagged task instead of halting. **Agent neutrality (Epic Q):** one config-driven headless connector — `--agent claude|gemini|codex|opencode|deterministic` — with fail-closed sandboxing + onboarding (`agents list`/`doctor --agents`); ACP client + permission gate is round 2. **Cockpit + setup (Epic O):** `siftmesh tui` (Textual, read-only over run files) + `siftmesh setup` (install + probe + multi-agent pick + persist to global/project config). **Scale:** per-family task aggregation (~10 tasks for a disk image, not 200+), executor tiering, `heavy_tool_timeout_seconds`. **Orchestration ADR `PLAN/12`:** keep the native deterministic FSM — LangGraph + CAO evaluated and rejected; harvest only an advisory Tier-2 judge + Sigma. PLAN/11 (space estimator/prune/merge) + the Tier-2 judge shipped.)_

> **REAL-ONLY (FINAL):** SIFTMesh ships real, working tools — **no mocks, no placeholder backends, no synthetic/seeded outputs**. The "wrapper-or-placeholder / mock executor / scripted self-correction / failure-simulation" language below is **superseded** by the confirmed real stack in [`PLAN/08_REAL_TOOL_STACK.md`](PLAN/08_REAL_TOOL_STACK.md) and the rule in `CLAUDE.md §2B`. All 8 MVP tools have a real in-process backend buildable now; self-correction is a deterministic engine over **real** tool output (an under-specified first-pass contract makes a real claim fail the Critic; a tightened retry makes the 2nd real attempt pass). Real evidence + integration/e2e are maintainer-provided and human-gated.

## 1. Final product definition

SIFTMesh is a CLI-first control plane for autonomous digital forensics and incident response on SANS SIFT and Protocol SIFT.

It combines:

```text
- autonomous/guided/manual CLI workflows
- CAO-compatible terminal-agent orchestration
- task contracts and context packets
- evidence-safe typed SIFT MCP tools
- evidence vault and hash manifest
- claim ledger and contradiction ledger
- critic validation and retry/escalation loop
- human-review gates
- reproducible reports and replay logs
- optional TUI last
```

The project should be built as a practical hackathon product, not a research-only concept.

## 2. Architectural layers

### Layer 0: SANS SIFT / Protocol SIFT environment

Purpose:

```text
Run real DFIR tools and provide the official hackathon-aligned environment.
```

Expected tools/artifacts:

```text
SIFT Workstation
Protocol SIFT
SleuthKit
Plaso/log2timeline
Volatility
RegRipper
EVTX parsing tools
Prefetch/Amcache/Registry tools
YARA
bulk_extractor
```

### Layer 1: SIFT MCP Gateway / AegisSIFT runtime

Purpose:

```text
Expose typed, evidence-safe forensic functions to agents.
```

MVP functions:

```text
compute_hash_manifest()
create_readonly_evidence_vault()
parse_evtx_security()
parse_evtx_powershell()
analyze_prefetch()
extract_registry_run_keys()
build_timeline()
validate_claim_evidence()
```

Critical requirement:

```text
No generic raw shell tool.
No destructive tools.
No write access to original evidence.
```

### Layer 2: Filesystem investigation bus

Purpose:

```text
Keep shared state out of chat history and inside inspectable artifacts.
```

Stores:

```text
context files
task contracts
agent results
claim ledgers
contradiction ledgers
audit logs
reports
```

### Layer 3: SIFTMesh orchestration core

Purpose:

```text
Own the investigation state machine and automate or guide the workflow.
```

Components:

```text
Planner
Deep Context Agent
Ultraworker
Executor Agents
Critic / Advisor
Evidence Manager
Budget Router
Prompt-Injection Guard
```

### Layer 4: Terminal-agent harness adapter

Purpose:

```text
Run Claude Code, OpenCode, Codex, Gemini, Kimi, Hermes, or other agents.
```

Preferred harness:

```text
CAO — EVALUATED AND NOT PURSUED (ADR 12, PLAN/12). CAO puts an LLM supervisor in the routing seat,
which conflicts with "LLM proposes, code decides". The native deterministic FSM is kept; LangGraph
was likewise evaluated and rejected (the FSM already provides its value). The simplest headless
`claude -p` adapter is the live-agent path; cao_adapter (I5) is closed won't-do.
```

Fallback:

```text
Generic shell-agent adapter that writes task instructions and expects result files.
```

Agent interoperability (optional, stretch — Epic P in /PLAN):

```text
A2A (Agent2Agent, Apache 2.0) Agent Card discovery + remote delegation.
Protocol stack: MCP = agent-to-tool; A2A = agent-to-agent; CAO = local terminal harness.
A2A-discovered agents are untrusted by default and governed by the SIFTMesh
x_siftmesh policy overlay; their output still passes the critic and claim validation.
```

### Layer 5: CLI

Purpose:

```text
User-facing source of truth.
Manual, guided, and automatic operation.
```

### Layer 6: TUI cockpit — ✅ shipped (Epic O, `PLAN/14`)

Purpose:

```text
Operator cockpit and demo visualization.
```

Status:

```text
SHIPPED as `siftmesh tui` using Textual (Python, MIT — chosen over the originally-planned Ratatui;
reuses the existing readers, no Rust). READ-ONLY over the run files (renders run_state.json + the
ledgers); launching a run reuses the governed engine in a worker thread. Contains no core logic.
Optional `tui` extra; lazy-imported with an install hint.
```

## 3. Target repo structure

```text
siftmesh/
  README.md
  LICENSE
  PROJECT_CONTEXT.md
  GUIDELINES.md
  CLAUDE.md
  AGENTS.md
  OVERALL_PLAN_DETAILED.md
  pyproject.toml

  docs/
    architecture.md
    threat_model.md
    evidence_integrity.md
    dataset_documentation.md
    accuracy_report_template.md
    judge_runbook.md

  siftmesh_core/
    __init__.py
    cli.py
    config.py

    orchestrator/
      __init__.py
      state_machine.py
      planner.py
      ultraworker.py
      scheduler.py
      critic.py
      budget_router.py
      workflow_runner.py
      human_gate.py

    schemas/
      __init__.py
      run.py
      task.py
      claim.py
      audit.py
      workflow.py
      agent_profile.py
      tool_result.py

    evidence/
      __init__.py
      vault.py
      manifest.py
      readonly.py
      hash_utils.py
      path_policy.py

    mcp_gateway/
      __init__.py
      server.py
      tools/
        evidence_tools.py
        evtx_tools.py
        prefetch_tools.py
        registry_tools.py
        timeline_tools.py
        validation_tools.py

    ledgers/
      __init__.py
      task_ledger.py
      claim_ledger.py
      contradiction_ledger.py
      audit_log.py
      injection_alerts.py

    adapters/                       # CAO/a2a adapters were planned but NOT built (ADR PLAN/12: CAO rejected; A2A = stretch Epic P)
      __init__.py
      base.py                       # ExecutorAdapter ABC + registry + resolve_profile/get_adapter
      deterministic_executor.py     # the real-tool floor (always available)
      claude_adapter.py
      opencode_adapter.py
      headless.py                   # config-driven agent-neutral connector: gemini/codex/… (Epic Q)
      generic_shell_adapter.py
      sandbox.py                    # cwd-pin + env-minimization for agent subprocesses (Epic Q)
      prompt_builder.py · agent_result.py · profiles.py · spotlight.py · agent_profiles.yaml

    reports/
      __init__.py
      final_report.py
      accuracy_report.py
      replay.py
      templates/
        final_report.md.j2
        accuracy_report.md.j2

  workflows/
    windows_initial_triage.yaml
    windows_powershell_triage.yaml

  skills/
    claude/
    opencode/
    cursor/
    codex/
    hermes/

  examples/
    demo_case/
      README.md
      expected_findings.md
      run_demo.sh

  tests/
    test_evidence_vault.py
    test_task_contracts.py
    test_claim_validation.py
    test_critic.py
    test_state_machine.py
    test_cli_modes.py
    test_path_policy.py

  siftmesh_core/tui/              # the TUI is PYTHON/Textual (Epic O) — NOT a separate Rust crate
    __init__.py                  # lazy launch + require_textual()
    snapshot.py                  # tested, Textual-free CockpitSnapshot builder (the data layer)
    app.py · cockpit.py · setup_screen.py · launcher_screen.py · widgets.py · runner.py
    cockpit.tcss
```

## 4. CLI command design

### Core commands

```bash
siftmesh init-case CASE_PATH --evidence EVIDENCE_PATH [--run-name NAME]
siftmesh plan RUN_PATH
siftmesh dispatch RUN_PATH [--task TASK_ID] [--agent-profile PROFILE]
siftmesh collect RUN_PATH
siftmesh critique RUN_PATH
siftmesh report RUN_PATH
siftmesh replay RUN_PATH
```

### Automation + onboarding/cockpit commands

```bash
siftmesh setup [--no-tui] [--scope global|project] [--yes]      # one-command onboarding (Epic O)
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --mode manual
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --auto-human-loop
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --auto --max-iterations 3
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --auto --max-agent-tasks 400   # raise the dispatch cap for a real disk image
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --agent claude|gemini|codex|opencode   # agent-neutral (Epic Q)
siftmesh run CASE_PATH --evidence EVIDENCE_PATH --review-only
siftmesh resume RUN_PATH
siftmesh status RUN_PATH
siftmesh tui [RUN_PATH]                                         # live Textual cockpit (Epic O)
```

### Inspection commands

```bash
siftmesh tasks list RUN_PATH
siftmesh tasks show RUN_PATH TASK-001
siftmesh claims list RUN_PATH
siftmesh claims show RUN_PATH CLAIM-001
siftmesh audit tail RUN_PATH
siftmesh retry RUN_PATH TASK-001
siftmesh approve RUN_PATH --gate plan
siftmesh reject RUN_PATH --gate retry
```

## 5. Workflow YAML design

Example: `workflows/windows_initial_triage.yaml`

```yaml
workflow_id: windows-initial-triage
mode: guided
max_iterations: 3
max_parallel_tasks: 3
max_agent_tasks: 10
max_tool_runtime_seconds: 300

approval_gates:
  plan: true
  dispatch: true
  retry: true
  report: true

safety:
  evidence_mode: read_only
  raw_shell: false
  allow_destructive_tools: false
  treat_evidence_as_hostile: true
  restrict_writes_to_run_directory: true

agents:
  planner:
    profile: claude_high_reasoning
  deep_context:
    profile: claude_sonnet_or_equivalent
  default_executor:
    profile: opencode_low_cost
  critic:
    profile: claude_high_reasoning

retry_policy:
  malformed_json: retry
  missing_evidence_reference: retry
  contradiction_detected: escalate
  tool_failure: retry
  max_attempts_per_task: 2

steps:
  - id: evidence_vault
    type: deterministic
    command: create_readonly_evidence_vault

  - id: deep_context
    role: deep_context_agent
    output: context/context_pack.md

  - id: plan
    role: planner
    output: context/investigation_plan.yaml

  - id: evtx_security
    role: executor
    task_template: templates/evtx_security_task.yaml

  - id: powershell_logs
    role: executor
    task_template: templates/powershell_task.yaml

  - id: prefetch
    role: executor
    task_template: templates/prefetch_task.yaml

  - id: registry_run_keys
    role: executor
    task_template: templates/registry_run_keys_task.yaml

  - id: critique
    role: critic

  - id: report
    type: deterministic
    command: generate_report
```

## 6. Implementation phases

## Phase 1: Project skeleton and config

Goal:

```text
Create the minimal repo structure and runnable Python package.
```

Tasks:

```text
- Create pyproject.toml.
- Add Apache 2.0 LICENSE.
- Add CLI entrypoint.
- Add config loader.
- Add run directory generator.
- Add base JSONL logger.
- Add initial tests.
```

Acceptance:

```bash
siftmesh --help
pytest
```

## Phase 2: Evidence vault and run directory

Goal:

```text
Initialize a case safely and produce evidence manifest.
```

Tasks:

```text
- Implement init-case command.
- Hash evidence files/directories.
- Generate evidence_manifest.json.
- Generate hashes.sha256.
- Generate evidence_policy.md.
- Create audit/orchestration_events.jsonl.
- Enforce path policy.
```

Acceptance:

```bash
siftmesh init-case ./case01 --evidence ./evidence
```

Expected output:

```text
case_runs/RUN-*/evidence/evidence_manifest.json
case_runs/RUN-*/evidence/hashes.sha256
case_runs/RUN-*/audit/orchestration_events.jsonl
```

## Phase 3: Schemas and ledgers

Goal:

```text
Make task, claim, contradiction, and audit schemas reliable.
```

Tasks:

```text
- Pydantic schema for TaskContract.
- Pydantic schema for Claim.
- Pydantic schema for ToolCall.
- Pydantic schema for CriticVerdict.
- JSONL append/read utilities.
- Validation errors with useful messages.
```

Acceptance:

```text
Invalid claim without tool_call_id is rejected.
Invalid task without safety_policy is rejected.
```

## Phase 4: Typed tool layer / MCP gateway MVP

Goal:

```text
Expose safe deterministic functions.
```

Tasks:

```text
- compute_hash_manifest implementation.
- create_readonly_evidence_vault implementation.
- parse_evtx_security real backend: evtx (pyevtx-rs) in-process, pin evtx==0.11.1.
- parse_evtx_powershell real backend: evtx (pyevtx-rs) in-process (4103/4104), pin evtx==0.11.1.
- analyze_prefetch real backend: libscca-python (pyscca) in-process, pin 20250915.
- extract_registry_run_keys real backend: regipy in-process, pin regipy==6.2.1 (`regipy[full]` is fine to add for shell-item parsing — license is not a blocker; see PLAN/08 §0.1, §3).
- build_timeline real: own merge over real rows + $MFT via mft==0.7.0 (Plaso optional gated).
- validate_claim_evidence implementation.
```

Acceptance:

```text
Every tool call writes tool_calls.jsonl.
Every tool output includes source artifact/hash.
No raw shell MCP tool exists.
```

## Phase 5: Planner and task generation

Goal:

```text
Generate a useful initial investigation plan and tasks.
```

Tasks:

```text
- Implement plan command.
- Generate context/case_brief.md.
- Generate context/investigation_plan.yaml.
- Generate initial TASK-*.yaml files.
- Generate context/tool_map.md.
- Support review-only mode.
```

Acceptance:

```bash
siftmesh plan case_runs/RUN-001
```

Expected output:

```text
context/investigation_plan.yaml
tasks/TASK-001.yaml
tasks/TASK-002.yaml
```

## Phase 6: Generic executor adapter

Goal:

```text
Allow tasks to be executed by a local deterministic or shell-agent adapter before CAO is ready.
```

Tasks:

```text
- Implement generic_shell_adapter.
- Implement deterministic real-tool executor (real in-process tools over real evidence; see PLAN/08) for tests/demo.
- Write TASK result JSON.
- Append agent_calls.jsonl.
- Drive self-correction by GENUINE causes (under-specified first-pass contract + recoverable real-tool errors), never simulated failures.
```

Acceptance:

```bash
siftmesh dispatch case_runs/RUN-001 --task TASK-001
siftmesh collect case_runs/RUN-001
```

## Phase 7: Critic and validation loop

Goal:

```text
Reject unsupported claims and create retry/escalation recommendations.
```

Tasks:

```text
- Implement critique command.
- Validate result JSON.
- Validate claim evidence references.
- Create unsupported_claims.jsonl.
- Create contradiction_ledger.jsonl.
- Create retry tasks when needed.
```

Acceptance:

```text
A result missing tool_call_id is rejected.
A retry task is created.
Critic verdict is logged.
```

## Phase 8: `siftmesh run` automation

Goal:

```text
Run full pipeline automatically with modes.
```

Tasks:

```text
- Implement state machine.
- Implement --mode manual.
- Implement --review-only.
- Implement --auto-human-loop.
- Implement --auto.
- Implement max iteration cap.
- Implement approval gates.
- Implement resume.
```

Acceptance:

```bash
siftmesh run ./case01 --evidence ./evidence --auto-human-loop
siftmesh run ./case01 --evidence ./evidence --auto --max-iterations 3
```

## Phase 9: CAO and agent profiles

Goal:

```text
Integrate external terminal agents through CAO or fallback adapters.
```

Tasks:

```text
- Add agent_profiles.yaml.
- Add cao_adapter.
- Add Claude Code profile.
- Add OpenCode profile.
- Add generic local profile.
- Generate task prompts from task contracts.
- Require executor output schema.
```

Acceptance:

```text
SIFTMesh can assign TASK-002 to an external agent profile.
Agent output is collected from the expected result path.
```

## Phase 9.5: A2A interoperability (optional / stretch — Epic P)

Goal:

```text
Discover and govern agents via the A2A (Agent2Agent) standard, on top of the existing adapter seam.
A2A replaces remote-agent discovery + the remote-worker API only. It is the envelope; the SIFTMesh
task contract is the payload (SIFTMesh creates the contract, A2A carries it, SIFTMesh validates the result).
SDK: a2a-sdk (Apache 2.0, Python 3.10+; JSON-RPC / HTTP+JSON-REST / gRPC). Agent Card at /.well-known/agent-card.json.
NOT MVP-mandatory. Ranks above the TUI but below CAO. Never on the demo critical path.
```

Tasks:

```text
- Add a2a_adapter (fetch + validate Agent Card from /.well-known/agent-card.json).
- Store discovered capabilities in context/agent_capabilities.json.
- Add x_siftmesh policy overlay schema; merge into a hybrid registry (static + CAO + A2A).
- Treat discovered agents as untrusted by default; require a conformance gate before dispatch.
- CLI: `siftmesh agents discover --a2a <url>`; optional `siftmesh dispatch --via-a2a`.
```

Acceptance:

```text
A discovered A2A agent appears in the capability map with an untrusted-by-default policy overlay.
Any A2A agent output still passes spotlighting, the critic, and claim validation (governance not bypassed).
```

## Phase 10: Reports and replay

Goal:

```text
Generate judge-ready artifacts.
```

Tasks:

```text
- final_report.md generator.
- accuracy_report.md generator.
- dataset_documentation.md generator/template.
- replay command.
- tool execution appendix.
- self-correction summary.
```

Acceptance:

```bash
siftmesh report case_runs/RUN-001
siftmesh replay case_runs/RUN-001
```

## Phase 11: Demo case and self-correction

Goal:

```text
Create a reliable demo showing autonomous correction.
```

Demo event:

```text
Executor produces a claim with missing evidence reference.
Critic rejects it.
Ultraworker creates retry task.
Executor produces corrected claim.
Final report includes corrected evidence-backed claim.
```

Optional prompt-injection event:

```text
Evidence contains instruction-like string.
Prompt-Injection Guard flags it.
Agent treats it as evidence only.
```

## Phase 12: TUI cockpit — ✅ shipped (Epic O, `PLAN/14`; Textual, not Ratatui)

Goal:

```text
Only after CLI works, build a read-only or thin-control TUI.  ✅ done with Textual (Python, MIT).
```

Minimum panels:

```text
State machine status
Current approval gate
Agent sessions
Task queue
Claim ledger
Critic feedback
Audit log
Token/budget usage
Report preview
```

Acceptance:

```bash
siftmesh tui case_runs/RUN-001
```

TUI must read existing run files and optionally call CLI commands. It must not duplicate core logic.

## 7. 12-day schedule

### Day 1: Skeleton and docs ✅ COMPLETE (Epic A)

Deliver:

```text
Repo structure
Apache 2.0 license
CLI package skeleton
PROJECT_CONTEXT.md
GUIDELINES.md
CLAUDE.md
OVERALL_PLAN_DETAILED.md
```

### Day 2: Evidence vault ✅ COMPLETE (Epic B)

Deliver:

```text
init-case command
evidence manifest
hashes.sha256
path policy
audit logger
```

### Day 3: Schemas and ledgers ✅ COMPLETE (Epic C)

Deliver:

```text
TaskContract schema
Claim schema
ToolCall schema
CriticVerdict schema
JSONL ledgers
schema tests
```

### Day 4: Tool gateway MVP ✅ COMPLETE (Epic D; allowlist now 10)

Deliver:

```text
hash tool
evidence vault tool
EVTX real backend (evtx / pyevtx-rs, in-process)
Prefetch real backend (libscca-python / pyscca, in-process)
Registry real backend (regipy, in-process)
tool call logging
```

### Day 5: Plan and task generation ✅ COMPLETE (Epic E, 2026-06-08)

Deliver:

```text
plan command                  # siftmesh plan RUN_DIR [--review-only] (real, deterministic)
case brief                    # context/case_brief.md
investigation plan            # context/investigation_plan.yaml (typed InvestigationPlan)
initial task contracts        # tasks/TASK-*.yaml (one per actionable artifact + timeline)
review-only mode foundation   # --review-only flag (engine-stop enforcement -> Epic H)
```

Also delivered: `context/{context_pack,tool_map,assumptions}.md`, `orchestrator/artifact_router.py`
(family→tool router), `workflows/windows_initial_triage.yaml`. Planner reads only manifest metadata
(privilege separation). See PLAN/04 "EPIC E DONE".

### Day 6: Dispatch and collect ✅ COMPLETE (Epic F, 2026-06-08)

Deliver:

```text
generic executor adapter
dispatch command
collect command
agent_calls.jsonl
result collection
```

### Day 7: Critic and retry ✅ COMPLETE (Epic G, 2026-06-09)

Deliver:

```text
critique command
unsupported claim rejection
retry task generation
contradiction ledger
confidence downgrade
```

### Day 8: Full run automation ✅ COMPLETE (Epic H, 2026-06-09)

Deliver:

```text
siftmesh run                  # one deterministic engine, four modes
manual/guided/auto/review-only modes
approval gates                # plan/dispatch/retry/report + approve/reject CLI
max iteration cap             # global iteration vs per-task attempt (distinct counters)
resume foundation             # RunState persisted atomically -> resume/status
```

Also delivered: `orchestrator/{state_machine,workflow_runner,ultraworker,human_gate,budget_router,run_state_store}.py`,
`run_state.json` durable snapshot, orchestration transition audit, static budget router (H9). The REPORT
state is the Epic-J seam (forensic report deferred). `hth.2` (derived re-ingest) remains open.

### Day 9: Agent/CAO integration ✅ CORE COMPLETE (Epic I, 2026-06-09)

> **Note:** per the bd graph (source of truth), Epic I runs **before** Epic K (K's self-correction
> needs the live agent; PLAN/08 §6) — i.e. `…H → I → K → J …`, not the stale §spine text order.

Deliver:

```text
agent_profiles.yaml           # packaged; 4 profiles keyed by registered adapter id (I1)
Claude Code task instructions  # claude_headless adapter + spotlighted prompt builder (I3/I6)
OpenCode task instructions     # opencode_headless adapter (I6 flag fixes)
fallback adapter               # registry falls closed to the deterministic floor + audits it (I2)
output-schema enforcement      # malformed agent result -> retry_required (I4)
```

Also delivered: `adapters/{profiles.py,prompt_builder.py}`. The live invocation is **human-gated**
(CLI + key; CI mocks the subprocess). **I5 (CAO adapter) is optional/best-effort — left open.**

### Day 10: Reports and replay ✅ COMPLETE (Epic J, 2026-06-10)

Deliver:

```text
final_report.md               # deterministic, code-built; anchored findings + ATT&CK + appendices
accuracy_report.md            # honest self-assessment; diff mode when expected_findings.md exists
dataset_documentation.md      # + architecture_notes.md + replay.html (self-contained)
replay command                # siftmesh replay (text + --html); siftmesh report
self-correction summary       # retries/verdicts narrative section in final_report.md
```

Also delivered: byte-deterministic rendering (no LLM at report time), the unsupported-only-in-appendix
firewall, and REPORT-state auto-generation in `siftmesh run` auto modes (fail-soft). See PLAN/06.

### Day 11: Demo hardening (self-correction ✅ Epic K; demo evidence maintainer-gated)

Deliver:

```text
stable demo case (real maintainer-provided evidence; integration-gated — Epic K1 open)
real EMERGENT self-correction ✅ (live agent + deterministic critic + retry feedback; Epic K3)
prompt-injection alert ✅ (injection_alerts.jsonl + critic human-review consequence; bypass-tested in L)
clean install instructions (Epic N)
```

### Day 12: Polish and submission assets

Deliver:

```text
README
architecture diagram
try-it-out guide
execution logs sample
demo video plan
final license check
```

TUI only if the CLI and reports are already stable before Day 12.

## 8. MVP acceptance criteria

SIFTMesh MVP is successful if the following works:

```bash
siftmesh run ./examples/demo_case --evidence ./examples/demo_case/evidence --auto-human-loop
```

And produces:

```text
evidence_manifest.json
tasks/TASK-*.yaml
results/TASK-*.result.json
claims/claim_ledger.jsonl
claims/unsupported_claims.jsonl
claims/contradiction_ledger.jsonl
audit/agent_calls.jsonl
audit/tool_calls.jsonl
audit/retries.jsonl
reports/final_report.md
reports/accuracy_report.md
```

The run must show at least one self-correction sequence.

## 9. Final demo narrative

Narration:

```text
SIFTMesh starts by hashing and protecting evidence.
It creates a compact context pack and investigation plan.
The Ultraworker breaks the case into task contracts.
Executor agents receive only narrow context, not the whole case.
Typed SIFT MCP tools extract evidence safely.
The Critic rejects unsupported claims.
The Ultraworker retries or escalates.
The final report includes only evidence-backed claims.
Every action is replayable through JSONL audit logs.
```

Demo command:

```bash
siftmesh run ./examples/demo_case --evidence ./examples/demo_case/evidence --auto-human-loop
```

Optional TUI command:

```bash
siftmesh tui ./case_runs/RUN-001
```

## 10. Final non-negotiables

```text
CLI before TUI.
Evidence safety before agent polish.
Claim ledger before final report.
Critic loop before demo polish.
Typed MCP tools before raw tool access.
Manual stages before full automation.
Guided mode before full auto.
Max iteration cap always.
No destructive tools.
No unsupported claim in final report as fact.
A2A is optional and governed by the policy overlay; it never overrides SIFTMesh forensic decisions.
```

# PROJECT_CONTEXT.md

# SIFTMesh Project Context

_Last updated: 2026-06-09 (Epics A–H complete; deterministic state machine + `siftmesh run`/resume/status/approve/reject shipped)_

## 1. Project identity

**Project name:** SIFTMesh

**Working subtitle:** Agent-agnostic orchestration and evidence-safe autonomous DFIR runtime for Protocol SIFT.

**One-line pitch:**

> SIFTMesh coordinates Claude Code, OpenCode, Codex, Gemini, Hermes, and other terminal/MCP-capable agents through task contracts, evidence-safe SIFT MCP tools, critic validation, human-review gates, and replayable audit logs.

SIFTMesh is not just another AI forensic chatbot. It is a **CLI-first DFIR control plane** for autonomous incident response on SANS SIFT and Protocol SIFT.

The project combines three ideas into one product:

```text
1. Multi-agent orchestration
   Planner, Ultraworker, Deep Context Agent, Executors, Critic/Advisor, Budget Router.

2. Evidence-safe DFIR runtime
   Read-only evidence vault, hash manifest, claim ledger, contradiction ledger, prompt-injection alerts, audit logs.

3. Typed SIFT MCP gateway
   Safe structured access to SANS SIFT / Protocol SIFT tools without exposing raw destructive shell commands.
```

## 2. Hackathon context

The target event is **Find Evil!**, a SANS/Devpost hackathon focused on building autonomous AI agents for defensive incident response on **SANS SIFT Workstation** and **Protocol SIFT**.

The event asks participants to improve how Protocol SIFT processes case data such as disk images, memory captures, remote endpoints through MCP, log files, and network captures. The mission is not merely to run tools; it is to teach an AI agent to think like a senior analyst: sequence investigation steps, notice when findings do not add up, correct itself, and produce evidence-backed reports.

Important hackathon requirements and expectations:

- Build on or integrate with SANS SIFT Workstation.
- Improve Protocol SIFT or the way agents use SIFT tools through MCP.
- Use an agentic architecture; Claude Code/OpenClaw are preferred, but comparable approaches are allowed.
- Show autonomous execution and at least one self-correction sequence.
- Produce traceable findings tied to tool executions.
- Submit a public GitHub repo with MIT or Apache 2.0 license.
- Submit a demo video, architecture diagram, project story, dataset documentation, accuracy report, try-it-out instructions, and agent execution logs.

## 3. Why SIFTMesh is different

Most teams may build:

```text
AI Agent -> SIFT tools -> report
```

SIFTMesh builds:

```text
CLI-first autonomous DFIR controller
        +
CAO terminal-agent harness
        +
Claude/OpenCode/Codex/Gemini/Hermes adapters
        +
typed read-only SIFT MCP tools
        +
evidence vault and hash manifest
        +
task contracts and context packets
        +
claim ledger and contradiction ledger
        +
critic validation and retry/escalation loop
        +
human-review gates
        +
replayable audit logs
```

The important distinction:

```text
CAO runs and coordinates agent sessions.
SIFTMesh controls the DFIR investigation logic.
```

CAO does not know which forensic claims are supported, unsupported, or contradicted. SIFTMesh owns that logic.

## 4. Current final direction

The product should be built in this order:

```text
Priority 1: Fully working CLI engine.
Priority 2: Evidence runtime, claim ledger, critic loop, and reports.
Priority 3: CAO/agent adapter integration.
Priority 4: Guided and full autonomous modes.
Priority 5: Optional A2A Agent Card discovery and delegation (governed by the SIFTMesh policy overlay).
Priority 6: Optional Ratatui TUI cockpit after CLI works.
```

The TUI is optional and last. It should never contain core investigation logic. The CLI must be the source of truth.

## 5. Final architectural principle

Every stage must satisfy both requirements:

```text
1. Callable manually for control, debugging, and judge reproducibility.
2. Callable automatically through `siftmesh run` for autonomy.
```

Core rule:

```text
Every automatic decision must be logged.
Every high-risk decision must support human approval.
Every final claim must trace to evidence.
```

## 6. Operating modes

SIFTMesh must support four modes.

### 6.1 Manual staged mode

For analysts and judges who want maximum control:

```bash
siftmesh init-case ./case01 --evidence ./evidence
siftmesh plan ./case_runs/RUN-001
siftmesh dispatch ./case_runs/RUN-001
siftmesh collect ./case_runs/RUN-001
siftmesh critique ./case_runs/RUN-001
siftmesh report ./case_runs/RUN-001
```

Use cases:

- Debugging.
- Judge reproducibility.
- Analyst-controlled workflow.
- Demo fallback if full automation fails.

### 6.2 Guided autonomous mode

Recommended hackathon demo mode:

```bash
siftmesh run ./case01 --evidence ./evidence --auto-human-loop
```

Meaning:

```text
SIFTMesh runs automatically until meaningful approval gates appear.
```

Human gates:

- After evidence hash/manifest creation.
- After investigation plan generation.
- Before dispatching multiple agents.
- Before retry/escalation when critic finds unsupported or contradictory claims.
- Before final report generation.

### 6.3 Full autonomous mode

For repeatable benchmark-style execution:

```bash
siftmesh run ./case01 --evidence ./evidence --auto --max-iterations 3
```

Required limits:

```text
--max-iterations 3
--max-agent-tasks 10
--max-tool-runtime 300
--evidence-mode read-only
--no-raw-shell
```

No unlimited autonomous loop is allowed.

### 6.4 Review-only mode

For conservative users:

```bash
siftmesh run ./case01 --evidence ./evidence --review-only
```

Meaning:

```text
The system creates plan and recommendations, but does not dispatch tools or agents.
```

## 7. Automation state machine

SIFTMesh should implement a deterministic state machine:

```text
INIT
  -> CREATE_EVIDENCE_VAULT
  -> DEEP_CONTEXT
  -> PLAN
  -> HUMAN_GATE_PLAN?       only in guided mode
  -> DISPATCH
  -> COLLECT
  -> CRITIQUE
  -> DECIDE
      -> RETRY       -> DISPATCH
      -> ESCALATE    -> DISPATCH
      -> HUMAN_REVIEW -> HUMAN_GATE_RETRY
      -> REPORT
  -> FINAL_HUMAN_GATE?      only in guided mode
  -> DONE
```

The LLM can recommend actions, but the deterministic Ultraworker state machine decides whether an action is legal.

## 8. Agent roles

### Planner ✅ (Epic E, shipped 2026-06-08)

Creates the investigation strategy, scope, constraints, expected artifacts, initial task graph, and evidence policy. Implemented deterministically in `siftmesh_core/orchestrator/planner.py` (+ `artifact_router.py`): `siftmesh plan` writes `context/{case_brief,context_pack,investigation_plan,tool_map,assumptions}` and `tasks/TASK-*.yaml` from manifest metadata only — it proposes, it never executes.

### Deep Context Agent ✅ (Epic E, deterministic)

Runs once near the beginning. Creates a compact context pack that explains the case type, relevant artifact families, tool usage guidelines, and likely investigation angles. Deterministic builder in `orchestrator/deep_context.py`; an optional LLM enrichment pass is deferred to the Epic F agent adapter.

### Ultraworker ✅ (Epic H, shipped 2026-06-09)

The main controller. Chooses next task, chooses agent/tool, handles retries, tracks token budget, reads critic advice, and decides whether to mark done, retry, escalate, or request human review. Implemented as a deterministic state machine in `orchestrator/{state_machine,workflow_runner,ultraworker,human_gate,budget_router,run_state_store}.py`: a frozen transition table + pure `step()`, `RunState` persisted atomically (temp+fsync+rename) to `run_state.json` for crash-safe `resume`, caps enforced in the loop (global `iteration` vs per-task `attempt`), and the four `siftmesh run` modes (manual/review-only/auto-human-loop/auto) over one engine. The forensic report (REPORT state) is the Epic-J seam.

### Executor Agents

Do narrow artifact-specific work. They must not produce broad incident conclusions or final severity. They only extract, normalize, and summarize evidence for assigned tasks.

### Advisor / Critic

Validates outputs, rejects unsupported claims, finds contradictions, lowers confidence, and recommends retry or escalation.

### Evidence Manager

Hashes evidence, enforces read-only handling, records derived artifacts, and maps every claim to evidence references.

### Budget Router

Uses expensive models only where judgment matters. Uses cheaper/open/local agents for repetitive extraction, formatting, and schema repair.

### Prompt-Injection Guard

Treats all case data as hostile. Detects instruction-like content inside logs, filenames, registry values, malware strings, command lines, and other evidence fields.

## 9. CAO role

CAO is a candidate harness layer for terminal-agent execution. It can run agents such as Claude Code, OpenCode, Codex, Gemini, Kimi, and others in isolated sessions. SIFTMesh should call CAO only during the dispatch stage.

Correct relationship:

```text
SIFTMesh creates task contract.
SIFTMesh chooses agent profile.
SIFTMesh asks CAO or another adapter to run worker.
Worker writes structured result.
SIFTMesh collects result.
Critic validates result.
```

CAO must not decide forensic truth, evidence policy, or final report content.

## 9a. A2A role (agent-to-agent interoperability)

A2A (Agent2Agent) is an open, Apache 2.0 standard (Linux Foundation / Google-originated) for agent-to-agent communication. It is **complementary to MCP and CAO**, not a replacement for SIFTMesh's orchestration or governance:

```text
MCP      = agent -> tool      (typed SIFT forensic tools)
A2A      = agent -> agent     (Agent Card discovery + remote delegation)
CAO      = local terminal-agent harness (Claude Code / OpenCode / Codex / Gemini / Kimi)
SIFTMesh = DFIR control plane (policy, evidence, claims, retries, reports)
```

A2A agents publish an Agent Card at `/.well-known/agent-card.json` (name, skills, endpoint, version). SIFTMesh can discover them and build a capability map instead of hand-maintaining every agent profile.

Governance rule:

```text
Agent Card = advertised capabilities.
SIFTMesh x_siftmesh policy overlay = governed permissions.
```

An Agent Card does not enforce read-only evidence, no-raw-shell, the claim schema, the confidence model, contradiction rules, retry/escalation, chain of custody, or unsupported-claim rejection. SIFTMesh adds those via the policy overlay: remote/opaque A2A agents are **untrusted by default**, must pass a conformance gate, and their output still flows through spotlighting, the critic, and claim validation. A2A is optional and not MVP-mandatory (Priority 5, above the TUI).

Boundary (what A2A does and does not replace):

```text
A2A replaces: custom remote-agent discovery + custom remote-worker API/messaging.
A2A does NOT replace: task contracts, evidence vault, claim/contradiction ledgers,
  critic, retry/escalation, human gates, the SIFT MCP gateway, or CAO local orchestration.
Envelope/payload: A2A is the envelope; the SIFTMesh task contract is the payload.
  SIFTMesh creates the contract -> A2A carries it -> SIFTMesh validates the result against it.
```

Verified vs a2a-protocol.org + the a2a-sdk README: package `a2a-sdk`, Apache 2.0, Python 3.10+, transports JSON-RPC / HTTP+JSON-REST / gRPC; Agent Card at `/.well-known/agent-card.json` per RFC 8615 (early A2A versions used `/.well-known/agent.json`).

## 10. MCP role

MCP is the compatibility boundary between agents and tools. SIFTMesh should expose typed forensic functions rather than generic shell execution.

Good MCP tools:

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

Forbidden MCP tools:

```text
execute_shell_command()
arbitrary_python()
rm()
dd_write()
mount_rw()
curl_arbitrary()
scp_arbitrary()
```

## 11. Filesystem-first run format

SIFTMesh should write all run state to disk so agents, humans, CLI, and future TUI can inspect it.

```text
case_runs/
  RUN-YYYYMMDD-HHMMSS/
    context/
      case_brief.md
      context_pack.md
      investigation_plan.yaml
      evidence_policy.md
      tool_map.md
      assumptions.md

    evidence/
      evidence_manifest.json
      hashes.sha256
      readonly_mounts.json
      derived_artifacts.json

    run_state.json            # Epic H: durable state-machine snapshot (atomic temp+rename)

    tasks/
      TASK-001.yaml
      TASK-002.yaml
      TASK-003.yaml

    results/
      TASK-001.result.json
      TASK-002.result.json
      TASK-003.result.json

    claims/
      claim_ledger.jsonl
      contradiction_ledger.jsonl
      unsupported_claims.jsonl
      confidence_changes.jsonl
      injection_alerts.jsonl

    audit/
      agent_calls.jsonl
      tool_calls.jsonl
      token_budget.jsonl
      retries.jsonl
      orchestration_events.jsonl

    reports/
      final_report.md
      accuracy_report.md
      dataset_documentation.md
      architecture_notes.md
      replay.html
```

## 12. CLI command target

High-level commands:

```bash
siftmesh run
siftmesh resume
siftmesh status
siftmesh tui
```

Stage commands:

```bash
siftmesh init-case
siftmesh plan
siftmesh dispatch
siftmesh collect
siftmesh critique
siftmesh report
siftmesh replay
```

Debug/inspection commands:

```bash
siftmesh tasks list RUN-001
siftmesh claims list RUN-001
siftmesh claims show CLAIM-003
siftmesh audit tail RUN-001
siftmesh retry TASK-003
siftmesh approve RUN-001 --gate plan
siftmesh reject RUN-001 --gate retry
```

## 13. TUI status

TUI is optional and last.

When built, it should be a Ratatui cockpit that reads the same run files written by the CLI and optionally triggers CLI commands. It should not contain orchestration, evidence, or validation logic.

Minimum TUI panels:

```text
- State machine status
- Current approval gate
- Agent sessions
- Task queue
- Claim ledger
- Critic feedback
- Audit log
- Token/budget usage
```

## 14. License policy

Project license (the one constraint that remains — a hackathon submission requirement: public repo under MIT or Apache-2.0):

```text
Apache 2.0
```

Dependency / tool-backend license posture (see PLAN/08 §0.1):

```text
License is NOT a blocker. Tool and connector licenses (e.g. LGPL libscca,
VSL Volatility 3, regipy[full], libyal/TSK in Plaso's tree) are replaceable
and not a gating concern — depend on the best real backend at runtime, and
swap later only if a license ever actually matters.
Do NOT COPY source code from restrictive projects (code-reuse rule, distinct
from depending on them at runtime).
```

Conceptual inspiration and runtime dependencies are fine; copying source code from another project must still pass license review.

## 15. Non-goals

Do not do these in the MVP:

```text
- Do not build a generic chatbot.
- Do not build a full SOC platform.
- Do not wrap all 200+ SIFT tools.
- Do not build the TUI before CLI is stable.
- Do not expose generic shell through MCP.
- Do not claim court-ready forensic soundness.
- Do not hide hallucinations or unsupported claims.
- Do not build a pure LangGraph/CrewAI demo without DFIR-specific evidence controls.
```

## 16. External references to keep in mind

- Find Evil Devpost: https://findevil.devpost.com/
- Find Evil Rules: https://findevil.devpost.com/rules
- Find Evil Resources: https://findevil.devpost.com/resources
- SANS SIFT Workstation: https://www.sans.org/tools/sift-workstation
- Protocol SIFT installer: https://raw.githubusercontent.com/teamdfir/protocol-sift/main/install.sh
- Model Context Protocol docs: https://modelcontextprotocol.io/
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- AWS CLI Agent Orchestrator: https://github.com/awslabs/cli-agent-orchestrator
- Microsoft Conductor: https://github.com/microsoft/conductor
- mcp-agent: https://github.com/lastmile-ai/mcp-agent
- A2A Protocol: https://a2a-protocol.org/
- A2A GitHub (Linux Foundation / a2aproject): https://github.com/a2aproject/A2A
- Ratatui: https://github.com/ratatui/ratatui

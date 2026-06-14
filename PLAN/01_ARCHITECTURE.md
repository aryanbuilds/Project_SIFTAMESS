# SIFTMesh — Architecture (Hybrid)

_Companion to `00_INDEX_AND_ROADMAP.md`. Defines the realistic, build-in-11-days architecture and the extension points the product roadmap grows into._

> **Real-only rule (refined):** SIFTMesh ships **no mock forensic backends, no placeholder tool backends, no synthetic integration outputs, and no scripted self-correction.** Pure **unit tests MAY use fixtures / golden JSON** (schema, path-policy, forbidden-tool, claim-validation checks); any **integration/e2e** behaviour shown in the demo must use **real artifacts and real tool output**. A missing backend **fails closed** with a dependency error (`siftmesh doctor`) — it must **never** fall back to a fake backend (*missing backend = OK; fake backend = not OK*). The MCP tool gateway has a `RealBackend` (in-process typed Python library calls) plus an optional gated `SiftLaneBackend` (fixed-argv CLIs on SANS SIFT) — there is **no `PlaceholderBackend`.** Confirmed tool/version facts are authoritative in **`PLAN/08_REAL_TOOL_STACK.md`**; this document defers to it.
>
> **Purpose & autonomy (the point of the product):** SIFTMesh is a **genuinely autonomous DFIR investigator** — handed a *black-box* dataset it was never told about, it decides what to examine, runs the typed tools, forms evidence-anchored claims, and **catches and corrects its own mistakes**. *Autonomy lives in the agent* — a real LLM plans, investigates, and self-corrects **emergently**. *Determinism lives in the governance* — the critic, `decide()`, caps, evidence-safety, and replayable audit are hardcoded so **code decides truth and safety**. Ground truth is **held out**: used only to score the agent's findings in the accuracy report, **never shown to the agent**. The deterministic path is the product's **reliability floor + regression/replay harness** — a golden snapshot of a *real recorded* agent run (real ledgers, **not a mock**) — not a substitute for the agent's intelligence.
>
> **Build priority (P1 first; the autonomous agent is core / never cut):** **P1** CLI + run-dir + schemas + evidence vault + real typed tools + critic + report + the **autonomous executor loop**; **P2** the **agent-neutral headless live-agent connector** (Epic Q — *not* CAO; CAO was evaluated and rejected, ADR `PLAN/12`) + the recorded-golden regression run; **P3** A2A Agent Card discovery/delegation (optional/stretch); **P4** read-only TUI. **Status (2026-06): P1–P4 all SHIPPED** — the Textual cockpit (Epic O) shipped, so the "TUI last" framing is now history. First legal cuts (last → first to survive): **A2A → extra tools beyond the core**. The live autonomous agent and the deterministic governance are both non-cuttable.

---

## 1. Architectural thesis

SIFTMesh is **not** a chatbot over forensic tools. It is a **deterministic DFIR control plane** in which:

```
The LLM proposes.  The deterministic code decides.
```

Every action an agent suggests is validated by hardcoded policy before it executes; every finding becomes an evidence-anchored claim; every claim is critiqued; every state transition is logged and replayable. The CLI is the source of truth — all state lives in inspectable files under a run directory, not in chat history.

The agent's **intelligence is genuine** — it investigates an unknown (black-box) dataset on its own, choosing what to examine and which tools to run, and **self-corrects emergently** when the critic rejects an unsupported or over-broad claim. Its **authority is bounded** — nothing it proposes becomes fact until deterministic code validates it. That split (genuine autonomy, bounded by deterministic governance) is the whole design.

### The hybrid decision (why this shape)

Research established that Protocol SIFT is best understood as a Claude Code config + skill library + tool allowlist, and that SIFT Workstation already bundles 200+ forensic tools. Reimplementing parsers is wasteful; depending entirely on a *live* full SIFT environment makes the demo fragile if a specific tool/version is missing. So SIFTMesh is built **Linux-first** (dev + target = SANS SIFT / Ubuntu) in two layers that share **one typed interface**:

- **Autonomous agent (the headline, core/never-cut)** — a real LLM agent plans and investigates the evidence *blind*, calls the typed tools, forms claims, and self-corrects emergently under the deterministic critic. This genuine autonomy is the product's core value; it requires an LLM/agent at run time.
- **Deterministic governance + tool spine (the reliability floor)** — the typed forensic tools are an **internal Python typed service** (the FastMCP server is a *thin adapter* over it; the CLI calls the service **directly** for reliability, agents reach it via MCP). The spine **targets** in-process Python backends (`hashlib`/stdlib + `evtx` + `regipy` + `pyscca` + `mft`); `siftmesh doctor` verifies each on the active host and a **missing backend fails closed** with a dependency error — **never** a fake. A **golden snapshot of a real recorded agent run** (real ledgers, not a mock) is the reproducible regression + demo safety net. The critic / `decide()` / caps / evidence-safety run with no LLM, so governance is deterministic even though the agent is not.
- **Optional SIFT lane** — on a SANS SIFT Workstation, the same typed tools swap their backends to orchestrate the real 200+ tools / Protocol SIFT skills. No interface change; a config flip.

This is robust whether or not Protocol SIFT exposes MCP, and it aligns with the hackathon's "improve how agents use SIFT tools" framing without betting the demo on the environment.

**Submission framing (keep Protocol SIFT central):** SIFTMesh **improves Protocol SIFT** — it wraps SIFT / Protocol-SIFT workflows in deterministic governance, typed evidence-safe execution, claim validation, and replayable audit, so an autonomous agent can use SIFT tools *safely and accountably*. The standalone spine exists for **reliability and reproducibility, not to avoid SIFT**; on a SANS SIFT host the SIFT lane drives the real toolset behind the same typed interface.

**SIFTMesh inspects and governs Protocol SIFT** (it is a Claude Code config/skill layer in `~/.claude`, **not** an MCP server — confirmed; see `PLAN/09_PROTOCOL_SIFT_INTEGRATION.md`): `siftmesh doctor --protocol-sift` / `siftmesh protocol-sift inspect` detect Claude Code, the global "Principal DFIR Orchestrator" config, the 5 skills, and the SIFT tool paths, then the SIFT-lane drives those real tools behind the same typed interface. Protocol SIFT's own `settings.json` allowlist/deny + Stop-hook audit is the *prompt/permission* version of SIFTMesh's constraints; SIFTMesh enforces them **in code**.

**The moat (designed against looking generic):** the field's agents pipe tool output into an LLM and trust it — the SANS reference *Valhuntir* "more than likely hallucinates" if simply told to "find evil," guarded only by a **human** approval gate. SIFTMesh's edge is a **deterministic critic _before_ the human**: (a) the **claim ledger is schema-enforced + deterministically validated** (not free-form logs); (b) the **Layer-1 critic is deterministic code + evidence-hash matching** (not another LLM — and the optional **Tier-2 LLM judge** that ships in `adapters/judge.py` is **provider-flexible** (claude/gemini/codex/opencode/`litellm:<model>`), **advisory + fail-soft**: it may only lower confidence / flag corroboration / annotate, **never promotes** — Tier-1 stays the sole promoter); (c) **constraints are architectural** (typed tools + allowlist registry + path policy + reject gates), not prompt text; (d) a **replayable chain-of-custody** ledger (`evidence/custody_log.jsonl`) aligned to **NIST SP 800-86 / ISO 27037** (auditability, repeatability, reproducibility; explicit non-goal: *not court-admissible*). Governance gates **quality, not quantity** — the agent still surfaces multiple candidate findings; the critic downgrades/labels rather than silently dropping, so breadth/depth is not starved.

---

## 2. Layered architecture (Layers 0–6)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Layer 6 — Textual TUI cockpit (read-only over run files + governed engine)│  SHIPPED (Epic O; Python/Textual, not Ratatui)
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 5 — CLI (Typer)  ── source of truth; manual / guided / auto modes   │
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 4 — Agent harness + interop adapters                                │
│   local harness:  deterministic(real-tool) · generic_shell · claude ·     │  determ. = reliable; rest = upgrade
│                   opencode · headless(gemini/codex/… agent-neutral)        │  (CAO evaluated + REJECTED — ADR PLAN/12)
│   advisory:       Tier-2 judge (tool-less; claude/gemini/codex/opencode/   │  adapters/judge.py — never promotes (fail-soft)
│                   litellm) · safety tiers T0–T3 (honest labels)            │
│   agent interop:  A2A Agent Card discovery + delegation (optional/stretch) │  governed by SIFTMesh policy overlay
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 3 — SIFTMesh orchestration core                                     │
│   Planner · Deep-Context · Ultraworker(state machine) · Critic ·          │
│   Budget Router · Prompt-Injection Guard · Evidence Manager               │
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 2 — Filesystem investigation bus (case_runs/RUN-*/…)                │
│   context · evidence · tasks · results · claims · audit · reports         │
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 1 — Typed MCP forensic gateway (FastMCP, stdio)                     │
│   10 typed tools · provenance · allowlist · audited execution             │
│   backend = real (in-process evtx/regipy/pyscca/mft) | SIFT-lane (gated)  │
│   (+ governed Sleuthkit image extraction + Volatility-3 memory triage)    │
├──────────────────────────────────────────────────────────────────────────┤
│ Layer 0 — SANS SIFT / Protocol SIFT environment (optional, target host)   │
│   SleuthKit · Plaso · Volatility3 · RegRipper · EZ Tools · YARA · …       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Boundary rule:** higher layers may call lower layers only through typed interfaces. The TUI (L6) never touches L1–L3 logic; it only reads L2 run files (launching a run reuses the governed L3 engine in a worker thread). A live agent harness (L4) never decides forensic truth (L3).

**Layer 1 is an internal Python typed service first; MCP is a thin adapter over it.** The forensic tools are implemented as plain typed Python functions/service; the FastMCP server merely exposes those same functions to agents. The **CLI calls the Python service directly** (CLI-first — no MCP round-trip required for deterministic stages); **agent clients call them via MCP**. Build the Python service first, the MCP adapter second — so the CLI never blocks on MCP.

---

## 2.1 Protocol stack — MCP · headless connector · A2A (who does what)

SIFTMesh speaks distinct protocols/harnesses, each at a different boundary. They are **complementary, not alternatives**:

| Layer | Standard | Boundary | Used for | License |
|---|---|---|---|---|
| **MCP** (Model Context Protocol) | open | agent → **tool** | typed SIFT forensic tools (Epic D) | — |
| **Headless connector** (Epic Q) | this project | controller → **agent runtime** | launch ANY CLI agent (claude/opencode/gemini/codex…) from a config `launch_argv` recipe — agent-neutral, sandboxed, fail-closed | Apache-2.0 |
| **A2A** (Agent2Agent) | open (Linux Foundation / Google-originated) | agent → **agent** | discovery of + delegation to remote/opaque agents via **Agent Cards** (optional/stretch) | Apache-2.0 |
| **SIFTMesh** | this project | **DFIR control plane** | policy, evidence, claims, retries, reports | Apache-2.0 |

> Mental model: **MCP = agent→tool · headless connector = controller→agent runtime (agent-neutral) · A2A = agent→agent (optional) · SIFTMesh = DFIR controller.** Each removes boilerplate only at its own boundary — **MCP replaces custom tool-calling; the headless connector replaces a bespoke per-agent adapter (one YAML profile row adds an agent); A2A replaces custom remote-agent discovery + remote-agent task API** — and none replaces SIFTMesh's DFIR governance. *(Verified vs `a2a-protocol.org` + `a2a-sdk`: A2A is Apache-2.0, Linux-Foundation-governed, complementary to MCP.)*
>
> **CAO (CLI Agent Orchestrator) was evaluated and REJECTED** (ADR `PLAN/12`): it puts an LLM supervisor in the routing seat, the opposite of "LLM proposes, code decides." The native deterministic FSM is kept; the live-agent path is the agent-neutral headless connector (`adapters/headless.py` + `agent_profiles.yaml`), not CAO. LangGraph was likewise evaluated and rejected.
>
> **Agent safety tiers (honest labels, never a gate).** Every connector carries a `safety_tier` derived purely from its probed capability facts (`schemas/agent_capabilities.py`, `doctor._agent_safety_tier`): **T0** deterministic floor (real tools, no LLM execution — the safe default); **T1** constrained live (sandboxed **and** typed tools via strict-MCP — Claude today); **T2** unconstrained live (capable but unsandboxed or tool-reach unproven — opencode/gemini/codex; explicit `--agent` opt-in, never described as sandboxed); **T3** advisory LLM (the tool-less Tier-2 judge — never promotes). Surfaced in `agents list`/`doctor --agents`/the cockpit + `context/agent_capabilities.json`; see `docs/architecture.md §2a`.

### A2A Agent Cards + the SIFTMesh policy overlay (the governance line)

An A2A agent publishes an **Agent Card** at `/.well-known/agent-card.json` (name, skills, endpoint, modalities, version). SIFTMesh can fetch it and route a task to the right agent at runtime — so we no longer hand-maintain every agent profile forever.

But an Agent Card only advertises **claimed** capabilities. It does **not** enforce read-only evidence, no-raw-shell, the claim schema, the confidence model, contradiction rules, retry/escalation, chain-of-custody, source-hash requirements, unsupported-claim rejection, or prompt-injection handling. **That stays SIFTMesh's job.** SIFTMesh attaches an `x_siftmesh` **policy overlay** to every discovered agent:

```json
{
  "name": "siftmesh-evtx-executor",
  "skills": [{ "id": "parse_evtx_security", "name": "Parse Security.evtx" }],
  "url": "http://localhost:8102/",
  "version": "1.0.0",
  "x_siftmesh": {
    "role": "executor",
    "trust_tier": "untrusted",          // remote/opaque agents are untrusted by default
    "cost_tier": "low",
    "can_make_final_claims": false,
    "can_use_raw_shell": false,
    "requires_readonly_evidence": true,
    "output_schemas": ["task_result.v1", "claim_ledger_entry.v1"],
    "allowed_claim_statuses": ["inferred", "unsupported"],
    "passed_conformance_tests": false
  }
}
```

**Rule: Agent Card = advertised capabilities; SIFTMesh policy overlay = governed permissions.** And **A2A is the *envelope*; the SIFTMesh task contract is the *payload*** — SIFTMesh creates the contract, A2A carries it to the remote agent, SIFTMesh validates the returned result against the contract. Every A2A agent's output still passes through spotlighting, the critic, claim validation, and the bypass-tested guardrails — exactly like a local agent. A2A *adds discovery*; it never *removes governance*. The new remote-agent attack surface is therefore one the existing architectural guardrails already contain — a **plus for criterion 4 (Constraint Implementation)**, not a risk.

A2A is **optional and not MVP-mandatory** — build priority is P1 core → P2 headless connector (Epic Q) → P3 A2A → P4 TUI (all shipped except A2A; see `00_INDEX_AND_ROADMAP.md`); the A2A work lives in **Epic P** (`05_PLAN_agents_automation.md`).

---

## 3. Data-flow (one investigation)

```
init-case ─► Evidence Manager hashes evidence (SHA-256) ─► evidence_manifest.json + hashes.sha256
   │                                                         (chain of custody starts here)
   ▼
Deep-Context (template/LLM) ─► context_pack.md
   ▼
Planner (deterministic template ± LLM) ─► investigation_plan.yaml + tasks/TASK-*.yaml
   ▼  [HUMAN_GATE_PLAN?]
Ultraworker.dispatch ─► ExecutorAdapter(deterministic|shell|claude|opencode|headless) runs TASK with SPOTLIGHTED evidence
   │                       └─► calls typed MCP tools ─► tool_calls.jsonl (provenance)
   ▼
collect ─► results/TASK-*.result.json
   ▼
Critic.critique ─► structural validation ─► CriticVerdict
   │   ├─ accepted          ─► claim_ledger.jsonl
   │   ├─ retry_required    ─► unsupported_claims.jsonl + confidence_changes.jsonl
   │   └─ contradiction     ─► contradiction_ledger.jsonl
   ▼
decide() (pure fn, CLAUDE.md §12) ─► {DONE | RETRY | ESCALATE | HUMAN_REVIEW}
   │      RETRY ─► new TASK (tightened) ─► back to dispatch       (THE SELF-CORRECTION LOOP)
   ▼  [FINAL_HUMAN_GATE?]
report ─► final_report.md + accuracy_report.md   ·   replay ─► replay.html
   │                              (all generated deterministically from JSONL ledgers)
   ▼
audit/orchestration_events.jsonl  ── every transition, fully replayable
```

---

## 4. The deterministic state machine (Layer 3 core)

```
INIT
 └─► CREATE_EVIDENCE_VAULT
      └─► DEEP_CONTEXT
           └─► PLAN
                └─► [HUMAN_GATE_PLAN]        (guided modes only)
                     └─► DISPATCH ◄────────────────┐
                          └─► COLLECT             │
                               └─► CRITIQUE       │
                                    └─► DECIDE ────┤
                                         ├─► RETRY ┘   (per-task max_attempts)
                                         ├─► ESCALATE ─► DISPATCH (strong profile)
                                         ├─► HUMAN_REVIEW ─► [HUMAN_GATE_RETRY]
                                         └─► REPORT
                                              └─► [FINAL_HUMAN_GATE]
                                                   └─► DONE
```

- The transition table is a **frozen `dict[State, set[State]]`** in `orchestrator/state_machine.py`. An LLM-proposed next-state not in the legal set is **rejected and logged** as `illegal_transition_rejected`.
- **Two distinct counters:** per-task `max_attempts` (default 2) lives in `RunState.per_task[id].attempt`; global `max_iterations` (default 3) lives in `RunState.iteration`. They gate different transitions.
- **Modes are config, not separate code** — see §6.

---

## 5. Security boundaries (artifact #3 diagram source)

Five boundaries the architecture enforces in code (the diagram in `docs/diagrams/security_boundaries.*` labels each):

```
        ┌── Evidence-vault boundary ──────────────────────────────┐
        │ originals are read-only; SHA-256 at ingest; derived      │
        │ artifacts written only into the run dir, never to source │
        └─────────────────────────────────────────────────────────┘
        ┌── Run-directory write boundary ─────────────────────────┐
        │ ALL writes route through path_policy.safe_write_path();  │
        │ any path escaping the run dir raises PathPolicyViolation │
        └─────────────────────────────────────────────────────────┘
        ┌── Typed-tool (MCP) boundary ────────────────────────────┐
        │ allowlist-only registry; forbidden tools un-registerable;│
        │ core real path = IN-PROCESS typed Python lib calls       │
        │ (8/10 tools, no subprocess → no command string to inject │
        │ into at all); fixed-argv subprocess (shell=False) only   │
        │ for image extraction (Sleuthkit) + memory triage (Vol-3) │
        │ + gated Plaso/Docker + SIFT-lane CLIs; no evidence       │
        │ string ever interpolated into a command (PLAN/08)        │
        └─────────────────────────────────────────────────────────┘
        ┌── Evidence-as-hostile boundary ─────────────────────────┐
        │ evidence normalized to JSON rows + spotlighted/datamarked│
        │ before any LLM sees it; injection-like content → alert,  │
        │ never executed; logged to injection_alerts.jsonl         │
        └─────────────────────────────────────────────────────────┘
        ┌── Claim/critic boundary ────────────────────────────────┐
        │ a Claim cannot exist without tool_call_id + source_sha256│
        │ unsupported claims never enter the final report as fact  │
        └─────────────────────────────────────────────────────────┘
```

**"LLM proposes / code decides" — five enforcement points:** (1) transition legality, (2) the pure `decide()` table, (3) caps in the run loop, (4) critic structural checks before any LLM reasoning, (5) adapter refusal of any tool not in `allowed_tools` / any out-of-run-dir write. Each has a bypass test (Epic L5).

---

## 6. Modes as configuration (one engine)

There is **one** state-machine engine. The four modes are a `RunConfig` over three knobs:

| Mode | Active gates | DISPATCH reachable? | Loop behavior |
|---|---|---|---|
| `manual` | all gates block until explicit `approve` | yes | advance exactly one transition per CLI call |
| `review-only` | plan | **no** (halts after PLAN) | stop after producing plan + recommendations |
| `auto-human-loop` (guided) | plan, dispatch, retry, report | yes | run until a gate or terminal state |
| `auto` | none | yes | run until terminal state; caps enforced |

Because all modes run the *same* transition code, **manual mode produces byte-identical artifacts to auto mode** (GUIDELINES §4.1) — verified by `test_manual_artifacts_equal_auto_artifacts`.

**Hard caps (auto):** `max_iterations=3`, `max_agent_tasks=10`, `max_parallel_tasks=3`, `max_tool_runtime_seconds=300`, `evidence_mode=read_only`, `raw_shell=false`, `allow_destructive_tools=false`.

---

## 7. Agent roles → multi-agent patterns

Mapped to Anthropic's "Building Effective Agents" patterns (research-confirmed):

| Role | Pattern | Responsibility | MVP backing |
|---|---|---|---|
| Planner | prompt-chaining + orchestrator decomposition | plan + task graph; never executes tools | **LLM-driven planning (autonomous)** + deterministic template fallback |
| Deep-Context | single-shot summarizer | compact reusable context pack | **LLM (autonomous)** + deterministic fallback |
| Ultraworker | orchestrator-workers + state machine | task order, dispatch, retry/escalate/human, caps | deterministic engine (always — governance) |
| Executor | tool-use loop | one narrow task; extract/normalize; cite evidence; no final severity | **live LLM agent (autonomous — PRIMARY)** via the agent-neutral **headless connector** (claude=T1 strict-MCP; opencode/gemini/codex=T2 opt-in) + deterministic real-tool floor (T0; regression floor) / generic shell |
| Critic | evaluator-optimizer | reject unsupported, find contradictions, drive retry | deterministic structural (always; sole promoter) + **advisory Tier-2 LLM judge** (`adapters/judge.py`, provider-flexible, fail-soft, never promotes) |
| Budget Router | routing | cheap-vs-strong selection; escalate on retry/contradiction | static map + escalate-on-retry |
| Prompt-Injection Guard | — | spotlight + scan evidence; alert, never execute | deterministic scanner (always) |
| Evidence Manager | — | hashes, read-only, derived registry, claim↔evidence map | always real |

---

## 8. Tech stack (confirmed)

| Concern | Choice | Note |
|---|---|---|
| Language | Python 3.11+ | Linux-first (dev + target = SANS SIFT / Ubuntu); SIFT-native |
| Packaging / deps | **uv** (Astral) | env + lockfile (`uv.lock`) + `uv run`; CI via `astral-sh/setup-uv`; **not** pip/venv |
| CLI | **Typer** | type-hint driven, low boilerplate, built on Click |
| Schemas | **Pydantic v2** | validation + `model_json_schema()` export for agent contracts |
| MCP server | **MCP Python SDK / FastMCP**, **stdio** transport | local forensic gateway; typed tools |
| Agent interop (optional) | **A2A Python SDK** (`a2a-sdk`, Apache 2.0, Python 3.10+; JSON-RPC / HTTP+JSON-REST / gRPC) | Agent Card discovery + delegation; governed by `x_siftmesh` policy overlay (Epic P) |
| Reports | **Jinja2** | deterministic, snapshot-testable templates |
| Logging | **structlog → JSONL** | UTC ISO-8601, one event/line, append-only |
| Config | TOML + env | `siftmesh.toml`, `Settings` model |
| Workflows/tasks | YAML | task contracts, workflow specs |
| Ledgers | JSONL | validate-before-write |
| Testing | **pytest** (+ snapshot/golden), **ruff**, **mypy/pyright** | CI primary runner = `ubuntu-latest` (= SIFT target); Windows CI optional/not required |
| Health check | **`siftmesh doctor`** | verifies Python/OS, each tool backend, run-dir writability, evidence readability, raw-shell disabled; **fails closed** on a missing backend (never a fake) |
| TUI (optional) | **Textual (Python, MIT)** — SHIPPED (Epic O; chosen over the originally-penciled Ratatui — reuses the existing readers, no Rust) | read-only over run files; `tui` extra |
| Tier-2 judge (optional) | vendor CLI (tool-less) or **LiteLLM SDK** (`llm` extra) | advisory; fail-soft; never promotes |

**License posture:** the **project source stays Apache-2.0** (submission requires a public MIT/Apache-2.0 repo; keep `LICENSE` Apache-2.0). **Runtime dependency licenses are acceptable after review and must be documented in a dependency/license audit (NOTICE + SBOM, Epic N6)** — prefer MIT/Apache/BSD; **GPL/LGPL/VSL tools may be used as *external runtime tools* only when compatible with the distribution/Docker plan and recorded in NOTICE/SBOM.** Do **not** vendor or copy restrictive source (Hayabusa/Chainsaw = inspiration only; Sigma rules = reusable data, DRL). Licenses are **not a hard blocker** (tools are replaceable) but they are **tracked, not ignored** (PLAN/08 §0.1, §5).

---

## 9. Target repo structure (greenfield → build order)

```
siftmesh/
  README.md   LICENSE(Apache-2.0)   pyproject.toml
  CLAUDE.md  AGENT.md  GUIDELINES.md  PROJECT_CONTEXT.md  OVERALL_PLAN_DETAILED.md
  PLAN/                         # this plan set
  docs/
    architecture.md  threat_model.md  evidence_integrity.md
    dataset_documentation.md  accuracy_report.md  try_it_out.md
    judge_runbook.md  project_description.md  submission_checklist.md
    diagrams/security_boundaries.{drawio,svg,png}
  siftmesh_core/
    __init__.py  cli.py  config.py  run_dir.py  logging.py
    orchestrator/ state_machine.py planner.py deep_context.py ultraworker.py
                  scheduler.py critic.py decide.py budget_router.py
                  workflow_runner.py human_gate.py
    schemas/      run.py task.py claim.py audit.py workflow.py agent_profile.py tool_result.py
                  evidence.py agent_capabilities.py critic_records.py custody.py decision.py
                  injection_alert.py plan.py protocol_sift.py agent_call.py yaml_io.py _base.py
    evidence/     vault.py manifest.py readonly.py hash_utils.py path_policy.py derived.py policy.py
    mcp_gateway/  server.py registry.py audit_exec.py
                  backends/ __init__.py real.py sift_lane.py
                  tools/ evidence_tools.py evtx_tools.py prefetch_tools.py registry_tools.py
                         timeline_tools.py validation_tools.py image_tools.py memory_tools.py _common.py
    ledgers/      task_ledger.py claim_ledger.py contradiction_ledger.py audit_log.py
                  injection_alerts.py  (+ confidence_changes, critic_verdicts, followups, retries, agent_calls, tool_call_ledger)
    adapters/     base.py deterministic_executor.py generic_shell_adapter.py claude_adapter.py
                  opencode_adapter.py headless.py judge.py            # headless = agent-neutral (Epic Q); judge = Tier-2 (no cao_adapter — ADR PLAN/12)
                  profiles.py agent_result.py sandbox.py spotlight.py prompt_builder.py agent_profiles.yaml
    reports/      __init__.py loader.py render.py final_report.py accuracy_report.py
                  dataset_documentation.py architecture_notes.py replay.py attack.py
                  templates/ *.j2
    tui/          __init__.py app.py cockpit.py setup_screen.py launcher_screen.py    # Textual cockpit (Epic O) — NOT a Rust crate
                  widgets.py snapshot.py runner.py theme.py cockpit.tcss
  workflows/      windows_initial_triage.yaml  windows_powershell_triage.yaml
  examples/demo_case/  README.md evidence/ expected_findings.md run_demo.sh
  tests/          EPIC_*_TESTS/  REFINEMENT_TESTS/  conftest.py  fixtures/  golden/
  .github/workflows/ci.yml
```

---

## 10. Platform strategy (Linux-first — dev + target = SANS SIFT / Ubuntu)

The plan is authored on Windows, but **all code is built and run on Linux** (SANS SIFT / Ubuntu) — dev and target are the same platform. Windows is **not** a constraint (PLAN/08 §0.1).

| Concern | Approach |
|---|---|
| Paths | `pathlib` everywhere; never string-concatenate paths; `safe_write_path` canonicalizes — kept as good hygiene. |
| CI | GitHub Actions primary runner = `ubuntu-latest` (= SIFT target). Windows CI is **optional / not required**. |
| Real tool availability | The MVP spine **targets** in-process Python backends (`evtx`/`regipy`/`pyscca`/`mft`); **`siftmesh doctor` verifies each on the active host** and a **missing backend fails closed** with a dependency error — never a placeholder (*missing = OK; fake = not OK*). EZ Tools / Plaso (native on Linux via `uv pip` / `apt install python3-plaso` / preinstalled on SIFT) are optional gated enrichment behind config (SIFT-lane / Docker). |
| Demo reproducibility | the **live autonomous agent** is the demo headline (needs an LLM/agent at run time); a **recorded-golden run** (real ledgers, not a mock) is the reproducible regression + safety net — Linux-native (PLAN/08 §6). |
| Final validation | Day 11a on a SANS SIFT VM (the native demo target; judges run on Linux/SIFT). The **only real gate is real evidence** (maintainer-provided EVTX / prefetch / registry hive / `$MFT`), not tool buildability — every backend installs on Linux now (PLAN/08 §0.1, §4). |

---

## 11. Extension points (how the roadmap plugs in)

- **New forensic tool** → add a `tools/*.py` typed wrapper + a `backends/real.py` entry; the registry, audit, and provenance come for free. (R1/R4)
- **SIFT-lane real orchestration** → implement `backends/sift_lane.py` per tool; flip config on the SIFT host. (R2)
- **New agent** → add a `kind: headless` **profile row** in `adapters/agent_profiles.yaml` (a `launch_argv` + `native_tool_argv` sandbox recipe) — the agent-neutral `HeadlessAdapter` runs it; no new adapter class (Epic Q). A genuinely different harness shape still implements `adapters/base.ExecutorAdapter`. (R3)
- **Remote / opaque agent** → discover its **A2A Agent Card**, attach an `x_siftmesh` policy overlay, register it in the hybrid registry; its output still flows through spotlighting + critic + claim validation. (Epic P / R3)
- **Detection rules** → drop Sigma rules (data) into a rules dir consumed by the critic/timeline tools. (R4)
- **Scale/search** → add an indexer that streams ledgers into OpenSearch/Timesketch; planner queries it. (R5)
- **TUI** → SHIPPED as the Textual cockpit (`siftmesh_core/tui/`, Epic O): reads `case_runs/RUN-*/` files; launching a run reuses the governed L3 engine in a worker thread; never duplicates core logic. (was R6)

# PLAN 05 — Agent Profiles, Adapters & Automation (Epic I)

_Phase 9 of the build, plus the automation surface that ties the engine to real agents, plus **Epic P — A2A interoperability** (agent-to-agent discovery/delegation). Profile-driven agent selection, task-prompt generation, output-schema enforcement, graceful fallback when a CLI is absent, and a hybrid registry (static + CAO + A2A + policy overlay). **CAO, live agents, and A2A are a best-effort upgrade lane — never on the demo critical path.** Serves criteria 3 (breadth), 6 (usability), with 4 (schema enforcement + the governance overlay)._

---

## Positioning (research-grounded)

- **AWS CAO** (cli-agent-orchestrator, Apache-2.0, tmux-based, supports Claude Code / Codex / Gemini / OpenCode) is **moderate maturity** — useful as a reference and an optional adapter, **not a hard dependency**.
- **PRIMARY path:** the **live autonomous agent** — the simplest headless adapter (`claude -p --output-format json` / OpenCode) is the core path; it investigates the real evidence and self-corrects emergently under SIFTMesh's **deterministic governance** (critic/decide/caps/evidence-safety, which SIFTMesh fully controls). The **deterministic real-tool executor (F2) is the regression/safety-net floor** (replays a real recorded run), not the headline. CAO and A2A are optional additional harnesses/interop.
- **Headless invocation patterns** (confirm against each tool's current docs before wiring): Claude Code `claude -p "<task>" --output-format json`; Codex `codex exec --json`; Gemini `gemini -p "<task>" --output-format json`; OpenCode server/run mode.
- **mcp-agent** (lastmile-ai) and **Microsoft Conductor** are pattern references for deterministic routing — inspiration, not dependencies.
- **A2A (Agent2Agent)** is the agent-to-agent interop standard (Apache 2.0; Linux-Foundation-governed; Agent Cards at `/.well-known/agent-card.json`). It **complements** MCP (tools) and CAO (local harness): **MCP = agent→tool · A2A = agent→agent · CAO = local terminal harness · SIFTMesh = DFIR controller.** Each removes boilerplate at its own boundary — **MCP replaces custom tool-calling; CAO replaces custom local terminal spawning/session management; A2A replaces custom remote-agent discovery + remote-agent task API** — and none replaces SIFTMesh governance. A2A is an **optional stretch (Epic P below)**, never on the demo critical path. *(Verified against `a2a-protocol.org` + the `a2a-sdk` README: package `a2a-sdk`, Apache 2.0, Python 3.10+, transports JSON-RPC / HTTP+JSON-REST / gRPC; Agent Card path `/.well-known/agent-card.json` per RFC 8615 — early A2A versions used `/.well-known/agent.json`.)*

The differentiator vs harness-only enforcement (CAO/Valhuntir): SIFTMesh's **forensic policy layer sits above the harness** — path policy, forbidden-tool registry, evidence-as-hostile spotlighting, and claim validation hold no matter which provider/agent executes. The same layer governs **A2A-discovered remote agents** (see the policy overlay below), so adding A2A *extends* interop without weakening governance.

---

# EPIC I — Agent Profiles & CAO/Adapter Integration

**Goal:** Profile-driven agent selection, task-prompt generation from contracts, executor output-schema enforcement, and graceful fallback when an agent CLI is absent. **Criteria:** 3 (breadth — multiple agent kinds), 4 (schema enforcement), 6 (usability). **Deps:** F (adapter protocol + spotlight), C (TaskContract, AgentProfile). CAO best-effort.

| Task | Title | Description | Key files | Deps | Acceptance | Role | Eff | Risk |
|---|---|---|---|---|---|---|---|---|
| I1 | `agent_profiles.yaml` + schema | Profile model: `profile_id, kind{deterministic|generic_shell|claude|opencode|cao}, command_template, output_format, cost_tier{cheap|strong}, max_runtime_seconds`. The `deterministic` kind is the **deterministic real-tool executor** — a real, in-process executor (the 8 real backends, see PLAN/08_REAL_TOOL_STACK.md), **not a mock**. Ship defaults: `deterministic_executor`, `claude_high_reasoning`, `opencode_low_cost`, `generic_local`. | `schemas/agent_profile.py`, `agent_profiles.yaml` | C | `test_profile_schema_valid`; unknown kind rejected. | Budget Router | S | low |
| I2 | Profile registry + fallback | Resolve `assigned_agent_profile` → adapter; missing CLI → fall back to the deterministic real-tool executor + log `adapter_unavailable`. | `adapters/registry.py`, `adapters/__init__.py` | F1,I1 | `test_absent_agent_falls_back_to_deterministic`. | Executor | M | med |
| I3 | Task-prompt generation | Render prompt from `TaskContract` (objective, allowed tools, success criteria, **spotlighted** context); no raw evidence dump. | `adapters/prompt_builder.py`, `adapters/spotlight.py` | F3,C | prompt contains datamarked evidence + "DATA not instructions" banner; no raw dump. | Executor | M | med |
| I4 | Executor output-schema enforcement | Validate result JSON against required executor schema before `collect` accepts it; failure → `retry_required` (feeds G). | `adapters/base.py`, `schemas/tool_result.py` | F5,C | malformed result rejected at collect; `test_collect_rejects_bad_schema`. | Executor | S | low |
| I5 | `cao_adapter` (best-effort) | tmux/CAO headless invocation; parse result; on any failure → fallback. | `adapters/cao_adapter.py` | F1,I2 | if CAO present → runs a worker; if absent → logs `adapter_unavailable`, no crash. | Executor | L | **high (skippable)** |
| I6 | Claude/OpenCode/generic profile wiring | Map F7/F8 adapters to profiles; cost tiers feed router. | `adapters/*`, `agent_profiles.yaml` | F7,F8,I1 | profiles selectable via `--agent-profile`; live use best-effort. | Executor | M | high |

**Design (I):** **PRIMARY = the live autonomous agent** (the simplest headless adapter — `claude -p`/OpenCode — is the core path; see PLAN/08 §6). CAO (`cao_adapter.py`) is *one* optional harness; absent a specific CLI/CAO → registry falls back to the **deterministic replay floor (F2)** with a logged event. The demo never requires CAO. **Output-schema enforcement is a hard gate:** any adapter result is validated against the required executor schema before collect; failure → `retry_required` (drives the self-correction loop). **11-day cut:** **I1–I4 are CORE** (they make the live agent work); **I5 (CAO) and I6 (extra harness wiring) are optional** — the live agent via the thin headless adapter is the core path, with the deterministic governance + recorded-golden floor for reliability.

---

## Hybrid agent registry & the A2A policy overlay

The single static registry becomes a **hybrid registry** with four sources, all subject to the same SIFTMesh policy overlay:

1. **Static local profiles** — `agent_profiles.yaml` (deterministic real-tool executor, claude, opencode, generic).
2. **CAO-discovered local terminal agents** — Claude Code / OpenCode / Codex / Gemini in tmux.
3. **A2A Agent Cards** — remote/wrapped agents discovered at `/.well-known/agent-card.json`.
4. **SIFTMesh policy overlay** — applied to every entry from sources 1–3.

**Agent Card = advertised capabilities; SIFTMesh `x_siftmesh` policy overlay = governed permissions.** A discovered card states what an agent *claims*; the overlay states what SIFTMesh *allows*:

```yaml
agents:
  - id: evtx_executor_local
    source: static
    harness: cao
    command: opencode
    role: executor

  - id: evtx_executor_a2a
    source: a2a
    agent_card_url: http://localhost:8102/.well-known/agent-card.json
    policy_overlay:                 # x_siftmesh — SIFTMesh-governed, NOT taken from the card
      trust_tier: untrusted         # remote/opaque agents are untrusted by default
      can_make_final_claims: false
      requires_readonly_evidence: true
      allowed_tools: [parse_evtx_security]
      allowed_claim_statuses: [inferred, unsupported]
```

**Governance invariant:** an A2A agent never gains a power the overlay denies. Its output still passes through spotlighting, the critic, claim validation, and the bypass-tested guardrails — identical to a local agent. A2A *adds discovery*; it never *removes governance*.

---

## What A2A replaces vs. what it does NOT (engineering-time boundary)

A2A is worth adding **only where it removes boilerplate we would otherwise write ourselves** — remote-agent discovery and remote-agent messaging. It never touches the DFIR logic that is SIFTMesh's actual value. This boundary is precisely why A2A is a stretch epic, not the core.

| SIFTMesh component | A2A replace it? | Why |
|---|---|---|
| Manual remote-agent registry | **Partially** | Agent Cards advertise capabilities; we still apply a policy overlay |
| Remote-agent capability schema | **Mostly** | Use Agent Card base fields + an `x_siftmesh` extension |
| Custom remote-worker HTTP API | **Yes** | `a2a-sdk` gives server/client + task lifecycle over JSON-RPC / HTTP+JSON-REST / gRPC |
| Remote result polling / streaming | **Mostly** | A2A task-lifecycle + streaming primitives |
| Plugin / agent discovery system | **Mostly** | Agent Cards become the discovery format |
| Audit logging | **Partially** | A2A logs *communication*; SIFTMesh still logs *forensic* audit events |
| **Task contract schema** | **No** | DFIR-specific; A2A only transports it |
| **Evidence vault / read-only enforcement** | **No** | SIFTMesh must enforce it |
| **Claim & contradiction ledgers** | **No** | SIFTMesh forensic schema |
| **Critic validation** | **No** | A2A does not know forensic truth |
| **Retry / escalation / human gates** | **No** | SIFTMesh controller logic |
| **SIFT MCP gateway (tool access)** | **No** | MCP's job (agent→tool) |
| **Local Claude/OpenCode terminal orchestration** | **No** | CAO's job (unless we write A2A wrappers — Epic P, P7) |

**The envelope/payload rule (the key correction):** A2A is the *envelope*; the SIFTMesh task contract is the *payload*. A2A transports contracts and results; it never defines, relaxes, or judges them.

```text
SIFTMesh creates the task contract
   (objective · allowed_tools · input artifacts + sha256 · required output schema
    · success criteria · retry/safety policy)
      │
      ▼   A2A carries the contract to the remote agent     (transport only)
remote agent returns a result
      │
      ▼   SIFTMesh validates the result AGAINST the contract
          (output schema · evidence refs · claim validation · critic)   ← governance unchanged
```

---

# EPIC P — A2A Interoperability Layer (stretch, ranked above TUI)

**Goal:** Standardize agent discovery + remote delegation via A2A Agent Cards, governed by the SIFTMesh policy overlay. **Criteria:** 3 (breadth — dynamic remote agents), 4 (the governance overlay holds over untrusted remote agents), 6 (interop story). **Deps:** Epic I (adapter protocol, registry, output-schema enforcement), Epic G (critic governs all output). **NOT MVP-mandatory; never on the demo critical path.**

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| P1 | Agent Card client + schema | Fetch + validate an A2A Agent Card from `/.well-known/agent-card.json` (Pydantic: identity/name, service endpoint `url`, capabilities, auth requirements, skills, version). Use the `a2a-sdk` client. | `adapters/a2a_adapter.py`, `schemas/agent_profile.py` | I1 | valid card parses; malformed card rejected with clear error. | M | low — path confirmed (`agent-card.json`, RFC 8615); pin `a2a-sdk` version |
| P2 | Capability-map storage | Store discovered cards + capabilities into `case_runs/RUN-*/context/agent_capabilities.json`. | `adapters/a2a_adapter.py`, `evidence/path_policy.py` | P1 | discovery writes a validated capability map under the run dir (via path policy). | S | — |
| P3 | `x_siftmesh` policy-overlay schema + registry merge | Pydantic `PolicyOverlay`; merge each discovered card into the hybrid registry; **untrusted-by-default**; overlay authoritative over card claims. | `schemas/agent_profile.py`, `adapters/registry.py` | I2, P1 | discovered agent gets `trust_tier=untrusted` + `can_make_final_claims=false` unless explicitly overridden; `test_a2a_overlay_untrusted_by_default`. | M | overlay bypass → overlay applied in code, never read as authoritative from the card |
| P4 | `agents` discovery CLI | `siftmesh agents discover --a2a <url>` (→P1+P2+P3), `siftmesh agents list`, `siftmesh agents inspect <id>`. **No remote dispatch needed** — discovery alone is the high-value, low-risk slice and the interop pitch. | `cli.py`, `adapters/a2a_adapter.py` | P1–P3 | all three commands work; `agent_capabilities.json` written; `inspect` shows discovered skills + applied overlay. | S | — |
| P5 | Conformance gate | Before a discovered agent is trusted for dispatch, validate a probe result against the required executor schema (reuses I4); fail → `passed_conformance_tests=false`, keep untrusted, fall back to the deterministic real-tool executor. | `adapters/registry.py`, `schemas/tool_result.py` | I4, P3 | agent failing conformance cannot be dispatched as executor; `test_a2a_conformance_gate`. | M | — |
| P6 | Optional `dispatch --via-a2a` | `siftmesh dispatch --via-a2a TASK-XXX --agent <id>`: render the task contract, delegate over A2A, collect result; result passes critic/claim validation like any other. | `cli.py`, `adapters/a2a_adapter.py`, `orchestrator/scheduler.py` | P1–P5, F4 | delegated result lands in `results/`, passes the same critique path; absent agent → graceful fallback. | L | **stretch-of-stretch; env-dependent** |
| P7 | Optional A2A server wrappers | Expose SIFTMesh's own agents (planner/critic/evtx/registry executor) as A2A servers publishing Agent Cards, so other systems can discover them. | `adapters/a2a_server/*` | P1 | each SIFTMesh agent serves a valid Agent Card; interop demoable. | L | **deep stretch / roadmap R3** |

**Design (P):** A2A bolts onto the *existing* adapter seam (Epic I) — no engine change. A2A is the **envelope**; the SIFTMesh task contract is the **payload** (SIFTMesh creates the contract → A2A carries it → SIFTMesh validates the result against it). The critical safety property: the **policy overlay is applied by SIFTMesh code, never read as authoritative from the remote card**, and remote-agent output is governed by the same critic/claim/bypass guardrails as everything else — so the new attack surface is already contained (a criterion-4 plus). **Discovery (P1–P4) needs no remote dispatch** — it fetches + governs cards, so it ships even with no live remote agent; full dispatch (P6) is stretch-only, built only if the core pipeline is already stable. SDK: `a2a-sdk` (Apache 2.0, Python 3.10+; JSON-RPC / HTTP+JSON-REST / gRPC). **11-day cut:** the whole epic is stretch. If any A2A ships, do **P1–P4** (discovery only — highest value, lowest risk: "SIFTMesh discovers agents via A2A Agent Cards and governs them with a policy overlay"). P5–P7 are stretch-of-stretch. A2A sits **above TUI but below CAO** in survival priority; cut it entirely before it can threaten the frozen hero.

---

## Automation surface (how Epic H's modes are exercised end-to-end)

The automation commands live in Epic H (`siftmesh run`, `resume`, `status`, `approve`, `reject`), but their *user-facing behavior* is summarized here as the operational contract this PLAN owns:

| Command | Mode/flags | Behavior |
|---|---|---|
| `siftmesh run CASE --evidence EV --mode manual` | manual | one transition per CLI call; every gate blocks until explicit approve; identical artifacts to auto |
| `siftmesh run CASE --evidence EV --review-only` | review-only | produce plan + recommendations; DISPATCH unreachable; no tools/agents run |
| `siftmesh run CASE --evidence EV --auto-human-loop` | guided | run automatically until a meaningful gate (plan/dispatch/retry/report) |
| `siftmesh run CASE --evidence EV --auto --max-iterations 3` | auto | run to terminal; enforce all caps; no gates |
| `siftmesh resume RUN-001` | — | reload `RunState`, continue from `current_state` |
| `siftmesh status RUN-001` | — | print state, gates, caps consumed, per-task attempts |
| `siftmesh approve RUN-001 --gate plan` / `reject … --gate retry` | — | advance/halt a blocked gate |
| `siftmesh tasks list/show`, `claims list/show`, `audit tail`, `retry TASK-003` | — | inspection/debug surface over run files |
| `siftmesh agents discover --a2a <url>` | — | fetch an A2A Agent Card → `context/agent_capabilities.json`; apply `x_siftmesh` policy overlay (Epic P, stretch) |
| `siftmesh agents list` / `siftmesh agents inspect <id>` | — | list discovered agents / show one agent's skills + applied policy overlay (Epic P, stretch) |
| `siftmesh dispatch --via-a2a TASK-XXX --agent <id>` | — | delegate a task contract to a discovered A2A agent; output still passes spotlighting/critic/claim validation (Epic P, stretch-of-stretch) |

**Approval-gate UX rule (GUIDELINES §4.2):** guided mode must not ask for trivial approvals — only the four meaningful gates. Gate prompts present approve / edit / skip for the plan gate and approve / reject for the rest.

**Hard limits enforced in auto (re-stated for operator clarity):** `max_iterations=3`, `max_agent_tasks=10`, `max_parallel_tasks=3`, `max_tool_runtime_seconds=300`, `evidence_mode=read_only`, `raw_shell=false`, `allow_destructive_tools=false`.

---

## Tests to add (I + P)

- `test_profile_schema_valid` — valid profile passes; unknown `kind` rejected.
- `test_absent_agent_falls_back_to_deterministic` — missing CLI → deterministic real-tool executor + `adapter_unavailable` logged, no crash.
- `test_collect_rejects_bad_schema` — malformed adapter result rejected at collect, drives retry.
- `test_prompt_builder_spotlights_evidence` — generated prompt contains datamarked evidence + banner, no raw dump.
- (best-effort) `test_cao_adapter_graceful_when_absent` — no exception when CAO/tmux unavailable.
- (Epic P) `test_a2a_card_parses` — valid Agent Card parses; malformed rejected.
- (Epic P) `test_a2a_overlay_untrusted_by_default` — a discovered A2A agent is `trust_tier=untrusted`, `can_make_final_claims=false` unless explicitly overridden by the overlay.
- (Epic P) `test_a2a_conformance_gate` — an A2A agent failing output-schema conformance cannot be dispatched as executor and falls back to the deterministic real-tool executor.
- (Epic P) `test_a2a_output_passes_critic` — output delegated via A2A still flows through spotlighting + critic + claim validation (governance not bypassed).

---

## Sequencing (Day 9) + cut discipline

```
Day 9 (spine-lock day):
  I1–I4  (profile schema, registry+fallback, prompt builder, schema enforcement)  ← MVP
  I5/I6 + F7/F8 live/CAO  ← best-effort, time-boxed; HARD-CUT if they threaten the frozen hero
```

**Cut rule:** the **live autonomous agent is core and never cut** — it is the product's whole point. CAO and *extra* harnesses are optional (the simplest `claude -p`/OpenCode adapter is the core path); A2A and TUI are the early cuts. The deterministic governance + recorded-golden run is the floor that protects the demo if a live run misbehaves — not a replacement for the agent.

---

## Roadmap hooks (post-hackathon)

- **R3 — Live-agent integration:** harden Claude Code / OpenCode / Codex / Gemini adapters and CAO; add real cost-based Budget Router and parallel multi-agent fan-out; **graduate A2A** from discovery-only (Epic P, P1–P4) to full delegation + exposing SIFTMesh's own agents as A2A servers (P6–P7).
- New harnesses plug in by implementing `adapters/base.ExecutorAdapter` and registering a profile in `agent_profiles.yaml` — no engine change.
- New **remote/opaque agents** plug in via A2A: discover the Agent Card, attach an `x_siftmesh` policy overlay, register in the hybrid registry — output still governed by the critic.

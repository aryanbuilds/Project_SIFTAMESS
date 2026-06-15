# PROJECT_CONTEXT.md

# SIFTMesh Project Context

_Last updated: 2026-06-11 (Epics A–N core + L + M complete; **+ Epic Q** agent-neutral connectors and **+ Epic O** Textual cockpit & unified `setup`. ROCBA e2e refinement - autonomous, objective-driven, one command: `--brief` ingests the incident document as the TRUSTED objective and threads it into the planner/agent-prompt/report; `run --auto` auto-decompresses archives (the memory zip) + auto-ingests the derived image, and quarantines a single critic-flagged task instead of halting the whole run. **Agent neutrality (Epic Q, PLAN/13):** one config-driven headless connector - `--agent claude|gemini|codex|opencode|deterministic` - with fail-closed sandboxing + onboarding via `agents list`/`doctor --agents`. **Cockpit + setup (Epic O, PLAN/14):** `siftmesh tui` Textual cockpit (read-only over run files) + `siftmesh setup` one-command onboarding (install + probe + multi-agent pick + persist to global/project config). **Scale fixes:** per-family task aggregation (a disk image yields ~10 tasks, not 200+), executor tiering (heavy tool-bound tasks → deterministic floor; `--all-live` overrides; `heavy_tool_timeout_seconds=1800`). Orchestration engine: **keep the native FSM - no LangGraph, no CAO** (ADR `PLAN/12`); harvest only an advisory Tier-2 LLM judge + Sigma breadth. Pre-flight space estimator + partition plan + `prune` + cross-run `merge` (PLAN/11); advisory Tier-2 LLM judge on the G8 seam (`run_tier2_judge`; never promotes - Tier-1 stays sole promoter).)_

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

The product was built in this order (status as of 2026-06-11):

```text
Priority 1: Fully working CLI engine.                                        ✅ shipped
Priority 2: Evidence runtime, claim ledger, critic loop, and reports.        ✅ shipped
Priority 3: Agent adapter integration - agent-neutral headless connectors (Epic Q).  ✅ shipped
            CAO + LangGraph evaluated and REJECTED - native deterministic FSM kept (ADR PLAN/12).
Priority 4: Guided and full autonomous modes (one engine, four modes).       ✅ shipped
Priority 5: Optional A2A Agent Card discovery + delegation (policy overlay).  ⏳ stretch (Epic P)
Priority 6: Textual TUI cockpit after the CLI works (Epic O).                 ✅ shipped (Textual, not Ratatui)
```

The TUI is optional and last, and never contains core investigation logic - it is a thin read-only
cockpit over the run files (launching a run reuses the governed engine). The CLI is the source of truth.

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

In `--auto` the engine prepares archive evidence itself (auto-decompress + auto-ingest of the derived image) and **never halts on a single task**: a task the critic sends to human-review/escalation is *quarantined* (recorded in `RunState.quarantined_tasks`, surfaced in the report; its claims are never promoted to facts) and the run completes to `done`. The `max_iterations` cap is the one genuine "stop and ask a human" (CLAUDE §12). Use `--auto-human-loop` when you instead want it to halt at the meaningful gates for `approve`/`reject`.

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

Creates the investigation strategy, scope, constraints, expected artifacts, initial task graph, and evidence policy. Implemented deterministically in `siftmesh_core/orchestrator/planner.py` (+ `artifact_router.py`): `siftmesh plan` writes `context/{case_brief,context_pack,investigation_plan,tool_map,assumptions}` and `tasks/TASK-*.yaml` from manifest metadata only - it proposes, it never executes.

**Incident objective (`--brief`).** A real engagement starts from an incident briefing (e.g. `ROCBA-BACKGROUND.pptx`) that states the TARGET. `--brief PATH` on `init-case`/`run` ingests that operator-designated document as **TRUSTED** context (`siftmesh_core/intake/brief.py` → `context/incident_brief.md` + manifest `incident_objective` metadata) - distinct from HOSTILE evidence: it is never in the evidence `files` set, never routed to a tool, never spotlighted. The objective is threaded into the case brief, the context pack, every executor task's prompt (so the live agent investigates *toward* it), and an "Answer to the incident objective" section in `final_report.md`. Designated explicitly only - a document merely found in the evidence dir is never auto-promoted to trusted instructions.

### Deep Context Agent ✅ (Epic E, deterministic)

Runs once near the beginning. Creates a compact context pack that explains the case type, relevant artifact families, tool usage guidelines, and likely investigation angles. Deterministic builder in `orchestrator/deep_context.py`; an optional LLM enrichment pass is deferred to the Epic F agent adapter.

### Ultraworker ✅ (Epic H, shipped 2026-06-09)

The main controller. Chooses next task, chooses agent/tool, handles retries, tracks token budget, reads critic advice, and decides whether to mark done, retry, escalate, or request human review. Implemented as a deterministic state machine in `orchestrator/{state_machine,workflow_runner,ultraworker,human_gate,budget_router,run_state_store}.py`: a frozen transition table + pure `step()`, `RunState` persisted atomically (temp+fsync+rename) to `run_state.json` for crash-safe `resume`, caps enforced in the loop (global `iteration` vs per-task `attempt`), and the four `siftmesh run` modes (manual/review-only/auto-human-loop/auto) over one engine. The REPORT state now generates the deterministic reports (Epic J) in auto modes.

### Executor Agents ✅ (Epics F + I, deterministic floor + live agents)

Do narrow artifact-specific work. They must not produce broad incident conclusions or final severity. They only extract, normalize, and summarize evidence for assigned tasks. Selected by `assigned_agent_profile` (Epic I: `adapters/profiles.py` + `agent_profiles.yaml`); each gets a spotlighted prompt from its task contract (`adapters/prompt_builder.py` - no raw evidence dump). The deterministic real-tool floor is the always-available default + fall-back; the live claude/opencode headless adapters are human-gated (CLI + key), and the registry audits an `adapter_unavailable` event whenever it falls closed.

**Multi-agent selection + fallback chain (Epic I).** `resolve_profile(role, settings, cli_override)` picks the profile to attempt first - precedence: explicit `--agent` override → `executor_selection=deterministic` (the **default** → floor) → a per-role pin (`role_profiles`) → the head of `agent_preference` when live/auto. `get_adapter` then walks the chain (requested → rest of `agent_preference` → floor) and returns the first `available()`, auditing each skip. Each adapter pins its **model** from `agent_profiles.yaml` (claude/opencode `--model`). Claude supports **both auth modes** - subscription token (`claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_AUTH_TOKEN`) or `ANTHROPIC_API_KEY`. End-user entry point: `siftmesh run … --agent claude|opencode|deterministic` (reorders the chain; live is opt-in). Each agent uses **its own native CLI + auth** - the Claude subscription only ever drives the real `claude` binary; it is never proxied to another client.

**Honest agent safety tiers (labels-only).** Every connector carries a `safety_tier` derived purely from the probed capability facts (so the label can never disagree with dispatch): **T0** `deterministic_floor` (real tools, no LLM execution - the safe default), **T1** `constrained_live` (sandboxed **and** typed tools via the strict-MCP boundary - Claude today), **T2** `unconstrained_live` (capable but unsandboxed or tool-reach unproven/native - opencode/gemini/codex; an explicit `--agent` opt-in, **never described as sandboxed**), **T3** `advisory_llm` (the tool-less Tier-2 judge - never promotes). The tier is surfaced in `agents list`/`agents inspect`/`doctor --agents`/the cockpit and written into `context/agent_capabilities.json`. It is a **label, not a gate** - `--agent opencode` runs exactly as before; the honesty is informational. The classification lives in `schemas/agent_capabilities.py` (`safety_tier` + `SAFETY_TIER_DESC`) and `doctor._agent_safety_tier`. This operationalizes the post-live-test posture: the deterministic floor is the safe default, Claude is the constrained live executor, opencode/codex/gemini are explicit unconstrained opt-ins, and LiteLLM is advisory-only.

**Agent neutrality + onboarding (Epic Q, round 1; PLAN/13).** SIFTMesh is not Claude-only. A single config-driven `HeadlessAdapter` (`adapters/headless.py`) launches **any** CLI agent from its `agent_profiles.yaml` `launch_argv` recipe - `gemini_headless`/`codex_headless` ship alongside claude/opencode, so adding an agent is a **profile row, not a new adapter**. `--agent gemini|codex|opencode|claude|deterministic` selects one (its only fallback is the deterministic floor - never a *different* live agent; unknown values error). **Evidence safety (audit-corrected 2026-06-11):** a headless recipe must carry native-tool deny/sandbox flags or it **fails closed** (codex `--sandbox read-only`, gemini `--approval-mode default`); every agent subprocess runs with a pinned run-scoped cwd (never the operator CWD - which auto-loads TRUSTED `GEMINI.md`/`AGENTS.md`) and a minimized env (only its own credentials). `claude_flag` injects the full Claude sandbox block; the Claude adapter gained `--tools ""`. Codex `exec --json` is parsed as a JSONL event stream (the naive whole-stdout parse always failed). **Onboarding:** `siftmesh doctor --agents` / `siftmesh agents list` / `agents inspect <id>` run `probe_agents()` → a typed `AgentCapabilityMap` (`schemas/agent_capabilities.py`, optionally `context/agent_capabilities.json`) reporting per-agent present/authed/**sandboxed**/tool-reachable; the default mirrors real dispatch (the floor under the deterministic default) and the ready live agent is surfaced separately as the `--agent` opt-in. Only Claude (`mcp_strategy=claude_flag`) reaches the typed tools today; gemini/codex are `verify-live`. (OpenClaw was researched and **dropped** - a personal-assistant gateway, not a coding agent.) Decision is **headless-first, ACP second**: round 2 adds the ACP client + `session/request_permission` permission gate.

**Cockpit (TUI) + unified setup (Epic O; PLAN/14).** `siftmesh setup` is the one-command onboarding (install all extras + `probe_agents` + multi-agent pick + persist via `config.save_agent_selection`); config now loads **global** (`~/.config/siftmesh/siftmesh.toml`) **then project** (`./siftmesh.toml` overrides) - a TOML *writer* was added (tomlkit). `siftmesh tui [RUN]` launches a **Textual** cockpit (optional `tui` extra; pure-Python, chosen over the originally-planned Ratatui - reuses our readers, no Rust). The cockpit is a **read-only** layer: `tui/snapshot.build_snapshot()` is a tested, Textual-free function that turns a run dir into a `CockpitSnapshot` by reusing `read_run_state` + `load_report_view` (+ task contracts), deriving timers from `updated_utc` (stage) + first/last event (total, frozen when terminal) with **no schema change**; the four-zone screen + nav tree poll it on a 1 s interval. Launching a run from the TUI drives the SAME governed engine in a `@work(thread=True)` worker (`tui/runner.py` mirrors `cli.run`); evidence safety is unchanged (no new write paths/tools/shell; agent subprocesses keep the Epic-Q cwd/env sandbox). The deterministic CLI commands all remain for scripting.

### Live self-correction loop ✅ (Epic K, K3)

The hero loop, **emergent not scripted**. The live adapter drives the agent to investigate via the typed MCP tools and respond with a JSON `{claims:[…]}` payload citing the `tool_call_id` + `source_sha256` each tool returned (`adapters/agent_result.parse_agent_result`). Two honesty rules: an **under-anchored claim is recorded `unsupported`** (never fabricate an anchor → it lands in `unsupported_claims.jsonl`), and **unparseable/empty output → `retry_required`**. The deterministic critic rejects the unsupported claim; the rejection reasons flow into the retry prompt (`build_task_prompt(critic_feedback=…)`); the agent revises against the real tool output and the corrected, anchored claim is promoted to the findings ledger. Claim IDs are **attempt-scoped** (`…-A{attempt}-CLAIM-NNN`) so a correction never collides with the claim it replaces. The MCP server is **run-scoped**: its agent-facing tools read `SIFTMESH_RUN_ROOT`/`SIFTMESH_EVIDENCE_ROOT` from the adapter-set environment (the agent cannot choose a root; missing env fails closed). The live run is human-gated (CLI + token); CI always mocks the agent subprocess and exercises the loop against the **real** critic + a **real** seeded tool call.

### Reports & Replay ✅ (Epic J)

Turns the run-dir ledgers into judge-ready, **byte-deterministic** artifacts - **no LLM at report time** (the replayable-audit differentiator, golden-tested). `siftmesh_core/reports/`: `loader.load_report_view` builds one frozen `ReportView` over every ledger (graceful-missing; corrupt line → `ReportLoadError`, `--tolerant` drops a trailing truncated line); `render.py` pins the Jinja env + a header/body sentinel split (`split_body()` so golden tests diff only the body) + a `MarkdownBuilder` (the markdown reports are code-built; only `replay.html` uses a template). Generators: `final_report.md` (confirmed/inferred findings each anchored to artifact+sha256+tool_call_id, MITRE ATT&CK table, contradictions, self-correction narrative, chain of custody, **complete** tool-execution appendix, **unsupported-only-in-appendix** firewall, mandatory "NOT court-ready" limitations), `accuracy_report.md` (honest self-assessment by default; precision/recall diff mode when `expected_findings.md` exists), `dataset_documentation.md`, `architecture_notes.md`, and a text + self-contained-HTML **replay**. Wired into `siftmesh report`/`replay` and the engine REPORT state (auto modes auto-generate, fail-soft - a report bug never strands a finished run). Every real-run edge case (failed tool, retry-only task, escalation, fell-back agent, empty/halted run, 400+ claims) degrades gracefully.

### Security & Threat Model ✅ (Epic L)

The constraints are **architectural and bypass-tested** (judged criterion 4), not prose.
`docs/threat_model.md` maps threats T1–T9 → OWASP LLM Top-10 2025 → real module → bypass test →
residual, with an **agentic overlay** (OWASP Top-10 for Agentic Apps ASI01–ASI10, MAESTRO, MITRE
ATLAS) and honest residuals (prompt injection is *contained + traceable, not prevented*; path policy
is posture-level + TOCTOU-bounded). Paired with `docs/architecture.md` (inline mermaid
security-boundary diagram) + `docs/evidence_integrity.md` (chain of custody). The proof is
`tests/EPIC_L_TESTS/` - **80 effect-asserting tests** that feed each gate a hostile input and assert
the *effect* (a raise / an appended injection alert / byte-identical originals / a critic verdict /
the launched argv): path-escape (incl. a Hypothesis property + the NUL-byte/`target==run` fixes),
forbidden-tool + live MCP surface-equality, injection (logged-not-executed → critic human-review,
no contagion), evidence read-only, claim-without-anchor rejection (end-to-end to the report
firewall), agent-sandbox argv, MCP confused-deputy, memory-poisoning, and audit non-repudiation.
Encodes the four real test-time bugs (5dh9/8tcx/bhyv/95q9) as permanent regressions. "LLM proposes,
code decides": a successful injection cannot exfiltrate (no network tool), write outside the run dir,
or become a reported fact without passing the deterministic critic.

### Testing & CI ✅ (Epic M)

**499 tests** (498 CI-run + 1 maintainer-gated live e2e), all real-fixture-driven. One consolidated
run factory in the root `tests/conftest.py` (`make_real_run` - manifest/readonly → plan → dispatch →
critique over the committed public fixtures; per-epic conftests are thin wrappers). **Recorded-golden
proof of Epic J's determinism** (`tests/golden/`): a REAL recorded run (real ledgers, §2B floor) +
committed report bodies; tests assert render-from-recorded == committed **byte-for-byte**, double-render
identity, and host-independence (regen only via `tests/golden/record.py --update`). **End-to-end**:
the §8 MVP artifact checklist over the genuine `vault init-case → run_engine --auto` path, a
subprocess smoke of the real module entrypoint, and a **skip-gated live property e2e**
(`SIFTMESH_LIVE_E2E=1` + claude CLI; asserts emergent self-correction as a property, never bytes -
maintainer-run only, §2B). **CI** (`.github/workflows/ci.yml`): Ubuntu matrix py3.11+3.12,
determinism env pins (TZ/LC_ALL/PYTHONHASHSEED), `uv sync --locked`, a **zizmor** Actions-security
job (clean), the **bypass suite as a named gate**, coverage gates (**92% overall, ≥90 enforced;
governance core schemas/evidence/critic/registry ≥95** - image/memory subprocess lanes honestly
omitted: they need maintainer evidence), coverage in the job summary, failure-only artifact upload,
every action SHA-pinned (verified live: checkout v6.0.3, setup-uv v8.2.0, upload-artifact v7.0.1).

### Advisor / Critic

Validates outputs, rejects unsupported claims, finds contradictions, lowers confidence, and recommends retry or escalation.

**Provider-flexible Tier-2 judge (post-Epic-Q).** The advisory Tier-2 judge + the cross-run merge synthesis now route through `adapters/judge.invoke_judge_text(prompt, settings)` (was Claude-only). `settings.judge` selects the backend: `None`/`cli:claude` (back-compat), `cli:gemini|codex|opencode` (the vendor CLI in **tool-less** mode - subscription OR API via the agent's own auth), or `litellm:<model>` (the **LiteLLM SDK**, optional `llm` extra - Gemini API/Vertex, OpenAI, Anthropic, Kimi, MiniMax). It is **fail-SOFT**: a missing CLI/key/extra or any error → skip + log `tier2_judge_skipped`, the run continues on Tier-1 (the deterministic critic stays the **sole promoter**; the judge still never promotes). Per-purpose selection: `--agent` picks the executor, `--judge` picks the judge (or pick both in `siftmesh setup`/`agents list`); off by default (`llm_critic_enabled`). Subscription stays on the vendor CLIs - LiteLLM is API-key/cloud only and is used **only** for the tool-less judge/synthesis, never the live executor (ADR research in `PLAN/13`). Kimi/MiniMax are flagged data-residency (operator opt-in).

### Evidence Manager

Hashes evidence, enforces read-only handling, records derived artifacts, and maps every claim to evidence references.

### Budget Router ✅ (Epic H9 static + Epic I profiles)

Uses expensive models only where judgment matters. Uses cheaper/open/local agents for repetitive extraction, formatting, and schema repair. Cost tiers come from the per-profile `cost_class`/`model_tier` in `agent_profiles.yaml` (Epic I); the static escalate-cheap→strong-on-retry router (`orchestrator/budget_router.py`, H9) logs each routing decision to `audit/token_budget.jsonl`. Real cost-based routing is roadmap R3.

### Prompt-Injection Guard

Treats all case data as hostile. Detects instruction-like content inside logs, filenames, registry values, malware strings, command lines, and other evidence fields.

## 9. CAO role

> **Decision (ADR 12, 2026-06-10): CAO evaluated and NOT pursued.** CAO puts an LLM supervisor in the
> routing/delegation seat - the opposite of SIFTMesh's "LLM proposes, code decides" thesis (it would
> weaken the constraint + audit criteria). The deterministic native FSM is kept; the optional
> `cao_adapter` (I5) is closed won't-do. The simplest headless `claude -p` adapter is the live-agent
> path. LangGraph was also evaluated and rejected (the shipped FSM already provides its value). See
> `PLAN/12_ADR_orchestration_engine.md`. The section below is retained as background.

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
siftmesh setup          # one-command onboarding: install + probe agents + pick a set + persist (Epic O)
siftmesh run
siftmesh resume
siftmesh status
siftmesh tui [RUN]       # live Textual cockpit (Epic O)
siftmesh agents list|inspect   # agent-neutral onboarding/inspection (Epic Q)
siftmesh doctor [--setup|--agents|--protocol-sift]
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

## 13. TUI status - ✅ shipped (Epic O, `PLAN/14`)

Built as a **Textual** cockpit (Python, MIT - chosen over the originally-penciled Ratatui; reuses the
existing readers, no Rust). `siftmesh tui [RUN]` is **read-only** over the run files (it renders
`run_state.json` + the ledgers on a 1 s poll via the tested, Textual-free `tui/snapshot.build_snapshot()`);
launching a run reuses the governed engine in a worker thread. It contains no orchestration, evidence,
or validation logic.

Cockpit zones (shipped):

```text
- Vitals bar: mode · stage(+spinner) · current gate · agent · tasks done/total · total + current-stage timers
- Pipeline ribbon: the FSM path (done/current/pending) + per-stage durations
- Task queue table (status · attempt · family · agent · claims · verdict)
- Side panels: claims/critic counters · agent sessions · budget
- Audit log ticker (live)
- Run-file navigation tree (open any results/claims/audit/report file)
```

## 14. License policy

Project license (the one constraint that remains - a hackathon submission requirement: public repo under MIT or Apache-2.0):

```text
Apache 2.0
```

Dependency / tool-backend license posture (see PLAN/08 §0.1):

```text
License is NOT a blocker. Tool and connector licenses (e.g. LGPL libscca,
VSL Volatility 3, regipy[full], libyal/TSK in Plaso's tree) are replaceable
and not a gating concern - depend on the best real backend at runtime, and
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
- Textual (the shipped TUI framework, Epic O): https://textual.textualize.io/
- Agent Client Protocol (ACP, Epic Q round 2): https://agentclientprotocol.com/
- Ratatui (evaluated, not used - Textual chosen): https://github.com/ratatui/ratatui

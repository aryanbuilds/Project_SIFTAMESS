# ADR 12 — Orchestration engine: keep the native deterministic FSM; harvest ideas, adopt no framework

_Status: **ACCEPTED** (maintainer-confirmed, 2026-06-10). Supersedes the "CAO if practical" framing in
OVERALL_PLAN §Layer-4 / PROJECT_CONTEXT §9._

## Context

While scaling the live ROCBA run we evaluated two external orchestration frameworks people reach for:
**CAO** (AWS `cli-agent-orchestrator` — an LLM *supervisor* delegating to CLI agents in tmux) and
**LangGraph** (a graph/state-machine agent runtime). The question: should SIFTMesh adopt either, or
keep its hand-built deterministic state machine?

## Decision

**Keep the native deterministic FSM. Adopt neither CAO nor LangGraph. Harvest only specific ideas.**

### Why not CAO
CAO puts an **LLM in the routing/delegation seat**. SIFTMesh's entire thesis is the opposite —
**"LLM proposes, code decides"** (PLAN/01): routing, promotion, retry, and safety are *deterministic*;
only the investigation is LLM-driven. Adopting CAO would move the exact decisions we architected to be
deterministic into a model, weakening criterion 4 (constraints) and criterion 5 (audit). CAO's audit
trail is tmux scrollback + inter-agent messages, not our byte-stable, schema-validated ledgers. CAO is
therefore **evaluated and not pursued**; the optional `cao_adapter` (Epic I5 / bd `hag`) is closed
won't-do. The simplest headless `claude -p` adapter remains the live-agent path.

### Why not LangGraph
LangGraph is a good fit *for a greenfield* "state-machine-guided agents" system — but SIFTMesh **already
is** one. The shipped FSM provides LangGraph's entire value with no dependency:
- typed state → `RunState` (`schemas/run.py`)
- conditional edges → `decide()` (`orchestrator/decide.py`) + the frozen `TRANSITIONS` table
- checkpointer / resume / time-travel → atomic `run_state.json` + `siftmesh resume`
- `interrupt()` / human gates → `orchestrator/human_gate.py`
- retry-with-feedback → the K3 critic-feedback loop

Porting would be a **high-churn refactor that adds a LangChain dependency and re-introduces
nondeterminism** (LLM-in-node, replay re-execution, checkpoint-id/wall-clock leakage) which we would
then spend effort re-mitigating — for **zero net capability**. It also contradicts a stated non-goal
(PROJECT_CONTEXT §15: "no pure LangGraph/CrewAI demo without DFIR-specific evidence controls"). The
golden/byte-determinism tests and the chain-of-custody story are easier to keep on the FSM we control.

### What we harvest (the genuinely-new ideas, built natively)
1. **Advisory Tier-2 LLM judge** — on the existing G8 seam (`critic.llm_adversarial_review`,
   `settings.llm_critic_enabled`). It may lower confidence / flag contradictions / suggest follow-ups /
   annotate uncertainty, logged verbatim to `audit/tier2_judgements.jsonl`; it **never promotes** —
   Tier-1 deterministic code stays the sole promoter. (Plan Phase 3.)
2. **Sigma breadth** — pySigma (LGPL, imported) + DRL-1.1 rules as an analysis-layer lead generator;
   never vendor Hayabusa (AGPL)/Chainsaw (GPL) source. (Roadmap R4.)

## Consequences

- The scale problem the ROCBA run exposed is fixed **inside the FSM**, not by swapping engines:
  per-family task aggregation (bd 1xy6: 429→~10 tasks), executor tiering (heavy tool-bound
  image/memory tasks run on the floor; the live agent does the rest), and adequate heavy-task
  timeouts. See the working plan + `tests/EPIC_F_TESTS/test_aggregation.py` / `test_executor_tiering.py`.
- CAO/LangGraph stay in the comparison record only. If a future need genuinely outgrows the FSM, this
  ADR is the place to revisit — but the bar is "a capability the FSM cannot express," not "a popular
  framework exists."
- Determinism, byte-stable goldens, and the chain-of-custody audit remain first-class and untouched.

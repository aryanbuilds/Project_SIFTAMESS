# SIFTMesh — Work, Commands & Features through Epic G

_Last updated: 2026-06-08 · branch `mvp_phase_1`_

Running reference for everything SIFTMesh has implemented through **Epic G** (the Critic &
Self-Correction Loop — the P0 "hero"). Builds on [`work_till_epicd.md`](work_till_epicd.md)
(Epics A–D) and [`epic_f_feature_sofar.md`](epic_f_feature_sofar.md) (Epic F); adds Epic G.

> **Status:** Epics **A, B, C, D, E, F** are complete and human-closed; **Epic G** is complete
> (**10/10** tasks closed) and its node is **open, eligible for the human close** (which unblocks
> Epic H). **306 tests pass; ruff/format/mypy clean (82 source files); `siftmesh doctor` ok
> (tool allowlist = exactly 10).** Build spine: `A → B → C → D → E → F → G → H → …` (strictly
> sequential; only a human closes an epic node).

---

## 1. What SIFTMesh is

A **CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR** on SANS SIFT
/ Protocol SIFT. It coordinates terminal agents through deterministic CLI workflows, task contracts,
context packets, an evidence vault, typed forensic MCP tools, a claim ledger, **deterministic critic
validation + self-correction**, human-review gates, and replayable audit logs.

**Load-bearing principles (enforced in code):**
- **CLI = source of truth.** Every stage writes inspectable files under `case_runs/RUN-*`.
- **"LLM proposes, code decides."** The agent is non-deterministic; the governance (critic,
  `decide()`, caps, evidence-safety, audit) is deterministic.
- **REAL-ONLY (CLAUDE §2B).** Every tool wraps a real, working library and produces genuine output;
  no mocks/placeholders/synthetic outputs. A missing backend **fails closed**, never a fake. Tests
  use real public fixtures / crafted-but-realistic inputs — never fabricated forensic output.
- **Privilege separation.** Planner proposes (never reads evidence bytes / never executes);
  executors run only the contract's one allowlisted tool; the critic governs deterministically; no
  raw shell anywhere.
- **Evidence is hostile.** Filenames and content are data, never instructions (datamarking +
  injection scanning + a critic injection consequence).

---

## 2. Architecture (layers) + package map

```
Layer 0  SANS SIFT host (Sleuthkit, Volatility 3, EZ Tools, 7-Zip, dotnet)
Layer 1  Typed MCP gateway — 10 evidence-safe forensic tools (Epic D)
Layer 2  Filesystem investigation bus — case_runs/RUN-* (context/evidence/tasks/results/claims/audit/reports)
Layer 3  Orchestration core — Planner+Deep-Context (E), Executor adapters+scheduler (F), Critic+decide (G), state machine (H)
Layer 4  Terminal-agent harness — claude/opencode headless (F8), generic shell (F7)
Layer 5  CLI — the user-facing source of truth (Typer)
Layer 6  Optional TUI (last; not started)
```

```
siftmesh_core/
  cli.py · config.py · run_dir.py · doctor.py · logging.py · protocol_sift.py
  schemas/    _base, tool_result, claim, task, task_result, audit (ToolCall+CriticVerdict),
              run, agent_profile, agent_call, injection_alert, workflow, plan,
              critic_records (Contradiction/ConfidenceChange/Retry/Followup), decision,
              evidence, custody, protocol_sift, yaml_io
  evidence/   vault, manifest, hash_utils, path_policy, readonly, derived, custody,
              image_access (Sleuthkit), memory_access
  mcp_gateway/ registry (allowlist) · audit_exec (run_tool) · server (FastMCP)
               backends/ real (in-process) + sift_lane (host CLIs)
               tools/ the 10 typed tools (+ validation_tools.grade_claim_against_run)
  ledgers/    jsonl_ledger · tool_call_ledger · claim_ledger · custody_ledger · audit_log
              agent_calls · injection_alerts · critic_verdicts · contradiction_ledger
              · confidence_changes · retries · followups
  orchestrator/ planner · deep_context · artifact_router (E) · scheduler (F)
                · critic · decide (G)
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
| `dispatch RUN_DIR [--task ID] [--agent-profile P] [--evidence DIR]` | **real (F)** | Runs each contract's tool; writes `results/TASK-*.result.json` + claims + `agent_calls`. |
| `collect RUN_DIR [--task ID]` | **real (F)** | Validates each result envelope; flags missing/malformed without crashing. |
| `critique RUN_DIR [--evidence DIR] [--followups/--no-followups]` | **real (G)** | Validates claims → one critic verdict per task; routes claims; detects contradictions; downgrades over-broad claims; injection consequence; **coverage-gap follow-up tasks**. |
| `retry RUN_DIR TASK-ID` | **real (G)** | Re-critique one task → `decide()`; if retry, tighten the contract + re-dispatch at attempt+1 (else refuse). |
| `doctor [--protocol-sift]` | **real (A/D)** | Verify host + every backend; fail closed; allowlist = 10. |
| `mcp-serve` | **real (D)** | FastMCP stdio gateway exposing exactly the 10 tools. |
| `extract-artifacts … --image …` / `analyze-memory … --memory …` | **real (D)** | Sleuthkit disk-image extraction / Volatility 3 memory triage (audited). |
| `protocol-sift inspect [--run-dir D]` / `protocol-sift skills list` | **real (D11)** | Inspect & govern the `~/.claude` Protocol SIFT layer. |
| `report` / `replay` | stub (J) | Final report / replay. |
| `run` / `resume` / `status` | stub (H) | State-machine automation (manual/review-only/auto-human-loop/auto). |
| `approve` / `reject` | stub (H) | Approve/reject a gate. |
| `tasks` / `claims` / `audit` | stub (debug) | Inspection sub-commands. |

---

## 4. The run-directory contract (`case_runs/RUN-YYYYMMDD-HHMMSS/`)

```
context/   case_brief.md  context_pack.md  investigation_plan.yaml  tool_map.md  assumptions.md
           evidence_policy.md  protocol_sift_capabilities.json  mcp_config.json
evidence/  evidence_manifest.json  hashes.sha256  readonly_mounts.json
           derived_artifacts.json  custody_log.jsonl
tasks/     TASK-001.yaml …                      (task contracts — Epic E; follow-ups — Epic G)
results/   TASK-001.result.json …               (executor envelopes — Epic F)
           TOOL-NNN.structured.json / .raw.json (tool provenance payloads — Epic D)
claims/    claim_ledger.jsonl  unsupported_claims.jsonl  injection_alerts.jsonl
           contradiction_ledger.jsonl  confidence_changes.jsonl                (Epic G)
audit/     tool_calls.jsonl  agent_calls.jsonl  orchestration_events.jsonl
           critic_verdicts.jsonl  retries.jsonl  followups.jsonl               (Epic G)
reports/   (final_report.md … — Epic J)
```
Every write routes through `evidence/path_policy.safe_write_path` (rejects traversal, run-dir escape,
and writes into the original evidence tree). Originals are never modified.

---

## 5. Feature summary by epic

- **Epic A — Project skeleton & config (closed, 59 tests):** `uv` package, Typer CLI, `RunPaths`
  generator, structlog JSONL logging, `SiftmeshSettings`, `doctor`.
- **Epic B — Evidence vault (closed, 34 tests):** real `init-case` — streaming SHA-256 → manifest +
  `sha256sum -c` hashes + readonly posture + chain-of-custody; `safe_write_path` gate.
- **Epic C — Schemas & ledgers (closed, 41 tests):** Pydantic v2 typed layer — `ToolResult`, `Claim`
  (the hallucination firewall), `TaskContract`, `CriticVerdict`, `RunState`, manifest, custody;
  validate-before-write JSONL ledgers.
- **Epic D — Typed MCP gateway (closed, 64 tests):** exactly **10** typed, audited, fail-closed
  forensic tools over FastMCP (evtx/prefetch/registry/timeline in-process; disk-image via Sleuthkit;
  memory via Volatility 3 subprocess — VSL never imported). Every call → `tool_calls.jsonl`.
- **Epic E — Planner & Deep Context (closed, 42 tests):** deterministic `siftmesh plan` — context
  files + task contracts from manifest metadata only; `artifact_router` family→tool routing;
  filename datamarking; investigation_plan acyclic step graph.
- **Epic F — Executor adapters (closed, 31 tests):** `ExecutorAdapter` ABC + registry (fall-closed
  to the floor); deterministic real-tool executor (real tools → anchored Claims); spotlight +
  injection alerts; `dispatch`/`collect`; agent_calls audit; generic-shell + claude/opencode thin
  adapters (live human-gated); genuine retry-cause recording.
- **Epic G — Critic & Self-Correction (complete, 35 tests; node open):** detailed below.

---

## 6. Epic G deep-dive — the deterministic critic + self-correction

The governance that makes findings trustworthy. **No LLM in the critic/decide path** (the live agent
self-correction hero is human-gated, Epic F8).

### 6.1 `critique` (G1/G2/G3/G6) — `orchestrator/critic.py`
`critique_run` reads each `results/TASK-*.result.json`, grades every Claim, and emits **one verdict
per task** (`accepted` / `accepted_with_downgrade` / `retry_required` / `escalation_required` /
`human_review_required`), persisted to `audit/critic_verdicts.jsonl`.
- **Grading (G2):** reuses `grade_claim_against_run` (extracted from the D9 tool — non-audited, so
  the critic doesn't spam `tool_calls.jsonl`): schema anchoring + manifest sha + tool_call_id in the
  ledger; over-broad/severity-overreach claims are **downgraded** (`accepted_with_downgrade` +
  `ConfidenceChange`), never silently dropped.
- **The double-write split (key correctness rule):** Epic F's deterministic floor already appended
  its claims to the ledger, so the critic **validates-only** (a claim_id membership guard prevents
  duplicates). Live-agent results (claims not yet in the ledger) → the critic **promotes** accepted/
  unsupported claims and never promotes rejected/human-review ones.
- **Contradiction (G3):** deterministic, low-false-positive — same artifact + digit-mask mismatch
  (e.g. "executed 3" vs "executed 9"), or `confirmed` vs `contradicted` on the same subject →
  `ContradictionRecord` + `escalation_required`.
- **Injection consequence (G6):** artifact-scoped — a claim tied to an injected artifact (or whose
  own text matches a signature) → `human_review_required` + a `source="critic"` alert; a benign claim
  with an *unrelated* alert is untouched (the "injection changes nothing it shouldn't" invariant).

### 6.2 `decide()` (G4) — `orchestrator/decide.py` (pure, no I/O; CLAUDE §12)
First-match truth table, precedence **human-stops > escalate > follow_up > done > retry**:

| condition | action |
|---|---|
| evidence mismatch · injection/human_review · max iterations · unsupported-affects-report | **human_review** |
| accepted/accepted_with_downgrade **with** a coverage/corroboration gap | **follow_up** |
| accepted/accepted_with_downgrade | **done** |
| contradiction / escalation_required · same task failed twice · retry budget exhausted · rejected | **escalate** |
| retry_required & attempt < max_attempts | **retry** (tighten success_criteria) |

### 6.3 Retry generation (G5)
On `decide → retry`: clone the contract, **tighten `success_criteria`** ("every claim MUST carry
tool_call_id + source_sha256; don't exceed the tool rows; no final severity"), overwrite
`tasks/TASK-XXX.yaml`, append a `RetryRecord` to `audit/retries.jsonl`, and re-dispatch at attempt+1
(the `retry` CLI). The auto-loop is Epic H.

### 6.4 Gap-detection + follow-ups (G9) — "recognize gaps and adjust"
- **Coverage gap:** an actionable manifest artifact **not covered by any task** → the critic creates
  a **follow-up task contract** (`reason="coverage_gap"` in `audit/followups.jsonl`), reusing the
  planner's contract builder. **Idempotent** — the new task covers the gap, so a re-run creates none;
  a fully-planned run raises zero.
- **Corroboration gap:** a high-risk single-source claim is **labelled** (`reason="corroboration_gap"`),
  never dropped.

### 6.5 §2B boundary
The deterministic governance (critic + decide + retry + gaps) is fully built and tested over real
fixtures + crafted-but-realistic `TaskResult` inputs. The **genuine live self-correction** (a real
agent makes a real over-broad claim → critic rejects → agent revises) is **human-gated** (Epic F8) —
wired, not run autonomously. **G8** (LLM adversarial Layer-2 critic) is a no-op identity seam behind
`config.llm_critic_enabled` (off by default; Layer-1 is sufficient).

---

## 7. How to run it (commands)

The full deterministic pipeline — **no API keys needed** (the floor runs real tools over real artifacts):

```bash
uv run siftmesh doctor                                    # verify host + backends (fails closed)
uv run siftmesh init-case ./case01 --evidence ./evidence  # hash + seal evidence
RUN=./case01/case_runs/RUN-*                               # the printed run id
uv run siftmesh plan "$RUN"                                # context files + task contracts
uv run siftmesh dispatch "$RUN"                            # real-tool execution -> anchored claims
uv run siftmesh collect "$RUN"                             # validate result envelopes
uv run siftmesh critique "$RUN"                            # critic verdicts + ledgers (+ coverage follow-ups)
uv run siftmesh retry "$RUN" TASK-003                      # tighten + re-dispatch (if decide says retry)

# Disk image / memory (Epic D, audited, fail-closed):
uv run siftmesh extract-artifacts "$RUN" --image disk.E01 --evidence ./evidence
uv run siftmesh analyze-memory   "$RUN" --memory mem.raw  --evidence ./evidence

# Expose the typed tools to an MCP agent (10 tools, no raw shell):
uv run siftmesh mcp-serve
```

**Live agent (F8) — human-gated, requires keys + CLI:** `export ANTHROPIC_API_KEY=…` then
`uv run siftmesh dispatch "$RUN" --agent-profile claude_headless` (falls closed to the floor if absent).

---

## 8. Configuration knobs (`SiftmeshSettings`, env `SIFTMESH_…` / `siftmesh.toml`)

`backend_mode` · `evidence_mode=read_only` · `raw_shell=False` · `allow_destructive_tools=False` ·
`caps.{max_iterations,max_agent_tasks,max_parallel_tasks,max_tool_runtime_seconds}` ·
`extraction_tools_enabled` · `vol_path` · `vol_symbol_dirs` · `ez_tools_dir` ·
`executor_selection` (deterministic/live/auto; deterministic default) · `default_agent_profile` ·
`claude_cli_path` · `opencode_cli_path` · `generic_agent_cmd` · `agent_timeout_seconds` ·
**`llm_critic_enabled`** (G8 Layer-2; default off). Nested caps via `SIFTMESH_CAPS__MAX_ITERATIONS=7`.

---

## 9. Testing & quality gates

- **306 tests pass**, per epic under `tests/EPIC_<X>_TESTS/` (unique basenames; no `__init__.py`):
  A=59, B=34, C=41, D=64, E=42, F=31, G=35.
- **CI-safe & real:** real tools over **committed public fixtures** in `tests/fixtures/forensic/`
  (never SANS evidence); subprocess/agent boundaries mocked; no API keys. Epic G tests run a real
  `dispatch` then `critique`, plus **crafted-but-realistic** `TaskResult` inputs for the rejection/
  retry/injection/gap paths (governance unit tests — not fabricated forensic output).
- **Gates (all green):** `uv run ruff check . && uv run ruff format --check . && uv run mypy &&
  uv run pytest && uv run siftmesh doctor` (82 source files; allowlist=10).
- **Epic G validation:** clean floor run → all-accepted verdicts, **zero re-appends** (double-write
  guard); delete a task → its artifact surfaces as a coverage gap → a follow-up task is created;
  `decide()` truth table has a test per row.

---

## 10. Hard rules / invariants (enforced)

- **REAL-ONLY**; missing backend fails closed. **Allowlist = exactly 10**; forbidden tools never register.
- **Volatility 3 is VSL → subprocess-only, never imported** (guard test).
- **No writes outside the run dir**; never modify/commit/CI SANS evidence; evidence treated as hostile.
- **Deterministic governance** (no LLM in critic/decide); the critic never re-appends F's claims;
  accepted/downgraded never silently dropped; injection logged → consequence only on the affected artifact.
- `decide()` is **pure**. **No AI co-authorship** on any commit. **Live agent self-correction is
  human-gated** — never run autonomously.
- **Strictly sequential epics**; only a human closes an epic node.

---

## 11. What's next — Epic H

Closing the Epic G node (`bd close Project_SIFTAMESS-uxr`) unblocks **Epic H — Ultraworker State
Machine & `siftmesh run`**: one deterministic engine (`RunState` + frozen transition table) driving
all four modes (manual / review-only / auto-human-loop / auto) with caps, approval gates, resume/
status, and the budget router. Epic H wires the stages already built —
`plan → dispatch → collect → critique → decide → retry/escalate/follow-up → report` — into one
governed loop, making the recommended demo command real:

```bash
siftmesh run ./case01 --evidence ./evidence --auto-human-loop
```
```
A✓  B✓  C✓  D✓  E✓  F✓  G(done, gate open)  →  H  →  K J L M N I P O
```

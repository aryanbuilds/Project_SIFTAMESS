# SIFTMesh — Work, Commands & Features through Epic I

_Last updated: 2026-06-09 · branch `mvp_phase_1`_

Running reference for everything SIFTMesh has implemented through **Epic I** (Live Agent Profiles &
Adapter Integration). Builds on [`work_till_epicd.md`](work_till_epicd.md) (A–D),
[`epic_f_feature_sofar.md`](epic_f_feature_sofar.md) (F), [`epic_g_feature_sofar.md`](epic_g_feature_sofar.md)
(G), and [`epic_h_feature_sofar.md`](epic_h_feature_sofar.md) (H); adds Epic I.

> **Status:** Epics **A, B, C, D, E, F, G, H** complete + human-closed. **Epic I** core is complete —
> **I1–I4 + I6 closed**; **I5 (CAO adapter) is optional and left open**, and the epic node `xvr` is
> **left OPEN for the human**. **349 tests pass; ruff/format/mypy clean (91 source files); `siftmesh
> doctor` ok (tool allowlist = exactly 10).**
>
> **⚠️ Spine-order correction (bd is the source of truth):** the real build order is
> `A → B → C → D → E → F → G → H → **I → K** → J → L → M → N → P → O`. The bd dependency graph has
> **Epic I before Epic K** (K's genuine self-correction needs the live agent — PLAN/08 §6), which
> *supersedes* the stale CLAUDE §2A spine text (`…H→K→J…I…`). Closing the Epic I node `xvr` unblocks K.

---

## 1. What SIFTMesh is

A **CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR** on SANS SIFT /
Protocol SIFT. Deterministic CLI workflows + task contracts + an evidence vault + typed forensic MCP
tools + a claim ledger + a deterministic critic/self-correction loop + a state-machine engine + human
gates + replayable audit — and now **profile-driven live agents** behind that governance.

**Load-bearing principles (enforced in code):** CLI = source of truth · "LLM proposes, code decides"
(the agent is non-deterministic; the governance is deterministic) · REAL-ONLY (no mocks/placeholders;
missing backend fails closed) · privilege separation · evidence-is-hostile (spotlighting) · the
**live agent is human-gated** (CLI + key) and always falls closed to the deterministic floor.

---

## 2. Architecture (layers) + package map

```
Layer 0  SANS SIFT host (Sleuthkit, Volatility 3, EZ Tools, 7-Zip, dotnet)
Layer 1  Typed MCP gateway — 10 evidence-safe forensic tools (Epic D)
Layer 2  Filesystem investigation bus — case_runs/RUN-* (run_state.json + context/evidence/tasks/results/claims/audit/reports)
Layer 3  Orchestration core — Planner (E) · Executors+scheduler (F) · Critic+decide (G) · state machine (H)
Layer 4  Terminal-agent harness — profile-driven adapters: deterministic floor + claude/opencode headless + generic shell (F + I)
Layer 5  CLI — the user-facing source of truth (Typer)
Layer 6  Optional TUI (last; not started)
```

```
siftmesh_core/
  cli.py · config.py · run_dir.py · doctor.py · logging.py · protocol_sift.py
  schemas/    _base, tool_result, claim, task (+InputArtifact.origin), task_result,
              audit, run (RunState/RunMode/PerTaskState), agent_profile (+AgentKind/OutputFormat),  ← Epic I
              agent_call, injection_alert, workflow, plan, critic_records, decision,
              evidence, custody, protocol_sift, yaml_io
  evidence/   vault, manifest, hash_utils, path_policy, readonly, derived (+read_derived),
              custody, image_access, memory_access, decompress
  mcp_gateway/ registry (allowlist) · audit_exec (run_tool) · server (FastMCP)
               backends/ real + sift_lane · tools/ the 10 typed tools
  ledgers/    jsonl_ledger · tool_call · claim · custody · audit_log · agent_calls · injection_alerts
              · critic_verdicts · contradiction · confidence_changes · retries · followups
  orchestrator/ planner · deep_context · artifact_router (+route_path) · scheduler · critic · decide
                · state_machine · workflow_runner · ultraworker · human_gate · budget_router · run_state_store
  adapters/   base (ABC + registry + get_adapter) · deterministic_executor · spotlight
              · claude_adapter · opencode_adapter · generic_shell_adapter
              · profiles.py (load_profiles) · prompt_builder.py · agent_profiles.yaml             ← Epic I
  reports/    (placeholder — Epic J)
workflows/    windows_initial_triage.yaml          examples/   (demo case — Epic K)
```

---

## 3. CLI command surface

`siftmesh <command>` — **real** = fully implemented; **stub** = prints, lands in its epic. (Epic I adds
no new command — it is the adapter layer behind `dispatch`/`run`; `--agent-profile` selects a profile.)

| Command | Status | What it does |
|---|---|---|
| `init-case CASE_DIR --evidence DIR` | **real (B)** | Streaming SHA-256 → manifest + hashes + readonly + custody; creates the run dir. |
| `plan RUN_DIR [--review-only]` | **real (E)** | Deterministic planner: context files + `tasks/TASK-*.yaml` from manifest metadata only. |
| `dispatch RUN_DIR [--task ID] [--agent-profile P] [--evidence DIR]` | **real (F + I)** | Runs each contract via its **profile-selected adapter** (falls closed to the floor); writes results + claims + `agent_calls`. |
| `collect RUN_DIR [--task ID]` | **real (F + I)** | Validates each result against the `TaskResult` schema; flags missing/malformed. |
| `critique RUN_DIR [--evidence DIR] [--followups/--no-followups]` | **real (G)** | One critic verdict per task; contradictions; downgrades; injection consequence; coverage + derived follow-ups. |
| `retry RUN_DIR TASK-ID` | **real (G)** | Re-critique → `decide()`; if retry, tighten + re-dispatch. |
| `decompress RUN_DIR --archive REL` | **real (D-H)** | Memory archive (zip/7z) → `evidence/extracted/` derived image. |
| `ingest-derived RUN_DIR` | **real (H)** | Make carved/decompressed derived artifacts plannable (origin=derived). |
| `run CASE_DIR --evidence DIR [--mode … / --review-only / --auto-human-loop / --auto]` | **real (H)** | One deterministic engine; init→plan→dispatch→collect→critique→decide→report→done. |
| `resume / status RUN_DIR` · `approve / reject RUN_DIR --gate G` | **real (H)** | Crash-safe resume / state inspection / gate approval. |
| `doctor [--protocol-sift]` · `mcp-serve` · `extract-artifacts` · `analyze-memory` · `protocol-sift inspect` | **real (A/D)** | Backends fail-closed; FastMCP stdio (10 tools); Sleuthkit/Volatility; Protocol SIFT inspect. |
| `report` / `replay` | stub (J) | Forensic report / replay (REPORT state is the Epic-J seam). |
| `tasks` / `claims` / `audit` | stub (debug) | Inspection sub-commands. |

---

## 4. The run-directory contract (additions visible by Epic I)

Unchanged from Epic H, plus the live-agent path writes: `context/mcp_config.json` (the per-run MCP
config pointing the Claude adapter at SIFTMesh's stdio FastMCP server — the 10 typed tools, no raw
shell), `results/TASK-*.prompt.txt` (the generic-shell agent's spotlighted prompt), and
`audit/token_budget.jsonl` (budget-router routing decisions). A fall-closed selection appends an
`adapter_unavailable` event to `audit/orchestration_events.jsonl`. All writes route through
`safe_write_path`; originals are never modified.

---

## 5. Feature summary by epic

- **Epic A — skeleton & config (closed, 56 tests):** `uv` package, Typer CLI, run-dir generator,
  structlog JSONL, settings, `doctor`.
- **Epic B — evidence vault (closed, 34):** real `init-case` (streaming SHA-256 → manifest + hashes +
  readonly + custody); `safe_write_path` gate.
- **Epic C — schemas & ledgers (closed, 41):** Pydantic v2 typed layer (Claim firewall, TaskContract,
  CriticVerdict, RunState, …); validate-before-write JSONL ledgers.
- **Epic D — typed MCP gateway (closed, 68):** exactly **10** typed, audited, fail-closed forensic
  tools over FastMCP; `decompress` CLI.
- **Epic E — planner & deep context (closed, 42):** deterministic `plan`; `artifact_router`.
- **Epic F — executor adapters (closed, 31):** the `ExecutorAdapter` ABC + registry (falls closed to
  the floor); deterministic real-tool floor; spotlight; `dispatch`/`collect`; thin claude/opencode
  adapters.
- **Epic G — critic & self-correction (closed, 35):** deterministic `critique` + pure `decide()` +
  retry + coverage/corroboration/derived follow-ups.
- **Epic H — Ultraworker state machine (closed, 32):** frozen transition table + atomic `RunState` +
  `run`/resume/status/approve/reject; caps; orchestration audit; derived re-ingest.
- **Epic I — live agent profiles & adapters (core complete, 10):** detailed below.

---

## 6. Epic I deep-dive — profile-driven live agents (behind the governance)

Epic F shipped the adapter spine; **Epic I formalizes it into profile-driven selection** with a
spotlighted prompt builder and output-schema enforcement. The deterministic floor stays the default +
always-available fall-back; the live agents are **human-gated**.

### 6.1 Profiles + schema (I1) — `schemas/agent_profile.py`, `adapters/{agent_profiles.yaml,profiles.py}`
`AgentProfile` extended (backward-compatible defaults): `kind` is now a Literal `AgentKind`
(`deterministic|claude|opencode|generic_shell|cao`), plus `model`, `command_template`,
`output_format` (`task_result_json|claude_json|opencode_json|none`), `max_runtime_seconds`. The
packaged `agent_profiles.yaml` ships 4 profiles **keyed by the registered adapter id** so the registry
resolves them:

| profile_id | kind | cost_class | model_tier | output_format |
|---|---|---|---|---|
| `deterministic_executor` | deterministic | free | local | task_result_json |
| `claude_headless` | claude | expensive | high | claude_json |
| `opencode_headless` | opencode | cheap | low | opencode_json |
| `generic_shell` | generic_shell | cheap | local | task_result_json |

`profiles.load_profiles(path=None)` reads + validates the YAML (unknown `kind`/typo → fail closed;
duplicate-id guard).

### 6.2 Registry + audited fall-back (I2) — `adapters/base.py`
`get_adapter(profile_id, *, settings, run=None)` resolves a registered adapter and **falls closed to
the deterministic floor** when the profile is unknown or the adapter's CLI/key is absent. When a `run`
is given it logs an `adapter_unavailable` orchestration event (`reason=unknown_profile` |
`cli_or_key_absent`, `fell_back_to=deterministic_executor`). `dispatch_run` passes the run, so every
no-keys CI run records *why* it ran the floor.

### 6.3 Spotlighted prompt builder (I3) — `adapters/prompt_builder.py`
`build_task_prompt(contract, *, run_id, result_file=None)` renders the agent prompt from the task
contract: objective + role + allowed tools + success criteria + context packet + the input artifacts
wrapped by the spotlight (`wrap_evidence` — datamarked, fenced by per-run `EVIDENCE_START/END`
delimiters, with the "DATA, not instructions" banner). **It never dumps raw evidence bytes** — only the
`path` + `sha256` rows — so a hostile filename/value cannot smuggle instructions (the L4 control). All
three adapters (claude/opencode/generic) were refactored onto it (DRY).

### 6.4 Output-schema enforcement (I4) — `adapters/generic_shell_adapter.py`, `scheduler.collect_run`
The executor's required output schema is `TaskResult`. A schema-invalid agent result is **recoverable**:
the generic-shell adapter returns `status="retry_required"` (`retry_cause="malformed_result"`), feeding
`decide()`/G's self-correction loop (not a silent error); `collect_run` independently flags a malformed
result file. So a sloppy agent answer drives a tightened retry rather than a dead end.

### 6.5 Live-adapter flags (I6, research-grounded, human-gated) — `adapters/{claude,opencode}_adapter.py`
Confirmed via the claude-code docs (deepwiki) + opencode docs, isolated in one builder each, to
**re-verify on the SIFT box** before a live run:
- Claude: `claude -p <prompt> --output-format json --mcp-config <run cfg> --allowedTools
  mcp__siftmesh__<tool> --permission-mode <non-interactive>` (the `--permission-mode` is the I6 fix;
  the agent surface is already constrained to the 10 read-only typed tools).
- OpenCode: `opencode run <prompt> --model <provider/model> --format json` (the I6 fix corrected the
  wrong `--output-format`). `available()` gates on the CLI (+ `ANTHROPIC_API_KEY` for Claude); absent →
  the registry falls closed to the floor. **CI mocks the subprocess; a live run is never executed
  autonomously.**

### 6.6 I5 (CAO adapter) — optional, left open
Per PLAN/05 "I5/I6 optional": the deterministic floor + the thin claude/opencode adapters are the core
path. The CAO (tmux harness) adapter is best-effort and remains an open bd task.

---

## 7. How to run it (commands)

No-keys deterministic path (the floor runs real tools over real artifacts):

```bash
uv run siftmesh doctor
uv run siftmesh init-case ./case01 --evidence ./evidence
RUN=./case01/case_runs/RUN-*
uv run siftmesh run "$RUN/.." --evidence ./evidence --auto      # one engine, all stages (floor)
# or the staged pipeline: plan → dispatch → collect → critique
uv run python -c "from siftmesh_core.adapters.profiles import load_profiles; print(sorted(load_profiles()))"
```

Live agent (Epic I) — **human-gated, requires the CLI + a key** (falls closed to the floor if absent):

```bash
export ANTHROPIC_API_KEY=…
uv run siftmesh dispatch "$RUN" --agent-profile claude_headless     # live Claude Code, constrained to the 10 MCP tools
uv run siftmesh dispatch "$RUN" --agent-profile opencode_headless   # live OpenCode (secondary)
```

The live agent investigates blind, constrained to the typed tools; its output still flows through the
critic + claim validation. Re-verify the headless flags with `claude --help` / `opencode run --help`
on the box first. **Do NOT run a live agent against real SANS evidence autonomously** (maintainer-gated).

---

## 8. Configuration knobs (`SiftmeshSettings`, env `SIFTMESH_…` / `siftmesh.toml`)

`backend_mode` · `evidence_mode=read_only` · `raw_shell=False` · `allow_destructive_tools=False` ·
`caps.{max_iterations,max_agent_tasks,max_parallel_tasks,max_tool_runtime_seconds}` ·
`extraction_tools_enabled` · `vol_path` · `vol_symbol_dirs` · `ez_tools_dir` ·
**`executor_selection`** (deterministic/live/auto; deterministic default) · **`default_agent_profile`**
· **`claude_cli_path`** · **`opencode_cli_path`** · **`generic_agent_cmd`** · **`agent_timeout_seconds`**
· `llm_critic_enabled`. The profile *metadata* (cost/tier/model/output_format) lives in
`agent_profiles.yaml`.

---

## 9. Testing & quality gates

- **349 tests pass**, per epic under `tests/EPIC_<X>_TESTS/` (unique basenames; no `__init__.py`):
  **A=56, B=34, C=41, D=68, E=42, F=31, G=35, H=32, I=10.**
- **CI-safe & real:** real tools over committed public fixtures; **no API keys** (the live agent's
  subprocess is mocked). Epic I tests: profile schema + YAML load + registered-adapter mapping;
  registry fall-back + `adapter_unavailable` audit (unknown profile + monkeypatched-unavailable CLI);
  prompt-builder spotlighting (banner + datamark + no raw dump); output-schema enforcement (collect
  flags malformed + generic-shell malformed → retry_required via a mocked subprocess).
- **Gates (all green):** `uv run ruff check . && uv run ruff format --check . && uv run mypy &&
  uv run pytest && uv run siftmesh doctor` (91 source files; allowlist 10).

---

## 10. Hard rules / invariants (enforced)

- **REAL-ONLY**; missing backend fails closed. **Allowlist = exactly 10**; forbidden tools never
  register; every adapter guards `allowed_tools`.
- **The live agent is human-gated** (CLI + key) — never run in CI/autonomously; the deterministic floor
  is the default + always-available fall-back, and every fall-back is audited.
- **Evidence is hostile** — every artifact handed to an agent goes through `wrap_evidence`
  (datamarked + banner); **no raw evidence dump**. `scan_injection` flags instruction-like agent output.
- **"LLM proposes, code decides"** — profiles/prompts feed the agent; the critic + `decide()` +
  path-policy + claim schema (all deterministic) govern the result.
- No writes outside the run dir; originals never modified. No AI co-author on any commit. Strictly
  sequential epics; only a human closes an epic node (the `xvr` node is left open).

---

## 11. What's next — Epic K (after a human closes `xvr`)

Closing the Epic I node (`bd close Project_SIFTAMESS-xvr`) unblocks **Epic K — Demo Case &
Self-Correction Scenario**. Epic K's hero is the **genuine live-agent self-correction** (now that the
live agent exists): a real LLM agent investigates real evidence blind, makes an over-broad/unsupported
claim, the deterministic critic rejects it, and the agent revises — emergent, not staged (PLAN/08 §6).
K1 (real evidence) + the live run are **maintainer-provided** (`§2B` STOP-and-ask). The §2B-safe
public-fixtures demo floor + `run_demo.sh` + ground truth are buildable now; **Epic J** (reports/replay)
follows K and fills the REPORT-state seam. **I5 (CAO)** remains an optional open task.

```
A✓ B✓ C✓ D✓ E✓ F✓ G✓ H✓ I (core done; I5 + gate open)  →  K  J  L  M  N  P  O
```

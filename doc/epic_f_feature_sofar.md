# SIFTMesh — Work, Commands & Features through Epic F

_Last updated: 2026-06-08 · branch `mvp_phase_1`_

This document is the running reference for everything SIFTMesh has implemented through **Epic F**.
It complements [`work_till_epicd.md`](work_till_epicd.md) (which covers Epics A–D in depth) and adds
Epic E (Planner) and Epic F (Executor Adapters & Dispatch/Collect).

> **Status:** Epics **A, B, C, D, E** are complete and human-closed; **Epic F** is complete (9/9
> tasks closed) and the epic node is **open pending the human gate**. The build spine is
> `A → B → C → D → E → F → G → H → …` (strictly sequential). **273 tests pass; ruff/format/mypy
> clean; `siftmesh doctor` ok (tool allowlist = exactly 10).**

---

## 1. What SIFTMesh is

A **CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR** on SANS SIFT
/ Protocol SIFT. It coordinates terminal agents through deterministic CLI workflows, task contracts,
context packets, an evidence vault, typed forensic MCP tools, a claim ledger, critic validation,
human-review gates, and replayable audit logs.

**Load-bearing principles (enforced in code):**
- **CLI = source of truth.** Every stage writes inspectable files under `case_runs/RUN-*`.
- **"LLM proposes, code decides."** The agent is non-deterministic; the governance (critic, decide,
  caps, evidence-safety, audit) is deterministic.
- **REAL-ONLY (CLAUDE §2B).** Every tool wraps a real, working library and produces genuine output
  from genuine input. No mocks, no placeholder backends, no synthetic/scripted outputs. A missing
  backend **fails closed** (`doctor`), never a fake fallback. Pure unit tests may use real public
  fixtures / golden JSON — that is normal testing, not a mock.
- **Privilege separation.** The planner proposes but never executes and never reads an evidence
  byte; executors run only the contract's allowlisted typed tool; no raw shell anywhere.
- **Evidence is hostile.** Filenames and content are treated as data, never instructions
  (datamarking + injection scanning).

---

## 2. Architecture (layers)

```
Layer 0  SANS SIFT / Protocol SIFT host (Sleuthkit, Volatility 3, EZ Tools, 7-Zip, dotnet)
Layer 1  Typed MCP gateway — 10 evidence-safe forensic tools (Epic D)
Layer 2  Filesystem investigation bus — case_runs/RUN-* (context/evidence/tasks/results/claims/audit/reports)
Layer 3  Orchestration core — Planner + Deep Context (E), Executor adapters + scheduler (F), Critic (G), state machine (H)
Layer 4  Terminal-agent harness — claude/opencode headless adapters (F8), generic shell adapter (F7)
Layer 5  CLI — the user-facing source of truth (Typer)
Layer 6  Optional TUI (last; not started)
```

### Package map (`siftmesh_core/`)
```
cli.py            Typer CLI (all commands)
config.py         SiftmeshSettings (env/toml/init precedence; caps; executor knobs)
run_dir.py        RunPaths — typed accessors for the run-dir contract
doctor.py         host + backend health checks (fails closed)
logging.py        structlog JSONL logging
protocol_sift.py  inspect/govern the ~/.claude Protocol SIFT layer (D11)

schemas/          Pydantic v2 typed contract layer (StrictModel, extra="forbid")
  _base, tool_result, claim, task, task_result, audit, run, agent_profile,
  agent_call, injection_alert, workflow, plan, evidence, custody, protocol_sift, yaml_io
evidence/         vault, manifest, hash_utils, path_policy, readonly, derived, custody,
                  image_access (Sleuthkit), memory_access (decompress + format detect)
mcp_gateway/      registry (allowlist), audit_exec (run_tool), server (FastMCP),
  backends/       real (in-process) + sift_lane (host CLIs)
  tools/          the 10 typed tools
ledgers/          jsonl_ledger, tool_call_ledger, claim_ledger, custody_ledger,
                  audit_log, agent_calls, injection_alerts
orchestrator/     planner, deep_context, artifact_router (E); scheduler (F)
adapters/         base (ABC + registry), deterministic_executor, spotlight,
                  generic_shell_adapter, claude_adapter, opencode_adapter (F)
reports/          (placeholder — Epic-J reports)
```

---

## 3. CLI command surface

`siftmesh <command>` — **real** = fully implemented; **stub** = prints, real behavior lands in its epic.

| Command | Status | What it does |
|---|---|---|
| `init-case CASE_DIR --evidence DIR [--run-name N] [--verify-after]` | **real (B)** | Streaming SHA-256 of all evidence → `evidence_manifest.json` + `hashes.sha256` + `readonly_mounts.json` + custody log; creates the run dir. |
| `plan RUN_DIR [--review-only]` | **real (E)** | Deterministic planner: reads the manifest, writes 5 `context/` files + `tasks/TASK-*.yaml`. No LLM, no evidence reads. |
| `dispatch RUN_DIR [--task ID] [--agent-profile P] [--evidence DIR]` | **real (F)** | Runs each task contract through its adapter; writes `results/TASK-*.result.json` + claims + `agent_calls.jsonl`. |
| `collect RUN_DIR [--task ID]` | **real (F)** | Validates each result envelope; flags missing/malformed without crashing. |
| `doctor [--protocol-sift]` | **real (A/D)** | Verifies host + every tool backend; fails closed on a missing dep; checks allowlist = 10. |
| `mcp-serve` | **real (D)** | Launches the FastMCP stdio gateway exposing exactly the 10 allowlisted tools. |
| `extract-artifacts RUN_DIR --image REL --evidence DIR [--keys …]` | **real (D)** | Sleuthkit extraction of Windows artifacts from a disk image into the run dir (audited). |
| `analyze-memory RUN_DIR --memory REL --evidence DIR [--plugins …] [--symbol-dirs …]` | **real (D)** | Volatility 3 memory triage via fixed-argv subprocess (VSL: never imported; audited). |
| `protocol-sift inspect [--run-dir D]` / `protocol-sift skills list` | **real (D11)** | Inspect & govern the `~/.claude` Protocol SIFT layer; optionally write a typed capability map. |
| `critique RUN_DIR` | stub (G) | Run the critic over collected claims. |
| `report RUN_DIR` | stub (J) | Render the final evidence-backed report. |
| `replay RUN_DIR` | stub (J) | Replay the audit trail. |
| `run CASE --evidence DIR [--mode …]` | stub (H) | High-level state-machine automation (manual/review-only/auto-human-loop/auto). |
| `resume` / `status` | stub (H) | Resume / show run state. |
| `retry` / `approve` / `reject` | stub (G/H) | Retry a task; approve/reject a gate. |
| `tasks` / `claims` / `audit` | stub (debug) | Inspection sub-commands. |

---

## 4. The run-directory contract (`case_runs/RUN-YYYYMMDD-HHMMSS/`)

```
context/   case_brief.md  context_pack.md  investigation_plan.yaml  tool_map.md
           assumptions.md  evidence_policy.md  protocol_sift_capabilities.json  mcp_config.json
evidence/  evidence_manifest.json  hashes.sha256  readonly_mounts.json
           derived_artifacts.json  custody_log.jsonl
tasks/     TASK-001.yaml …                      (task contracts — Epic E)
results/   TASK-001.result.json …               (executor envelopes — Epic F)
           TOOL-NNN.structured.json / .raw.json (tool provenance payloads — Epic D)
claims/    claim_ledger.jsonl  unsupported_claims.jsonl  injection_alerts.jsonl
audit/     tool_calls.jsonl  agent_calls.jsonl  orchestration_events.jsonl  (retries.jsonl — G)
reports/   (final_report.md … — Epic J)
```
Every write is routed through `evidence/path_policy.safe_write_path` (rejects traversal, run-dir
escape, and writes into the original evidence tree). Originals are never modified.

---

## 5. Feature summary by epic

### Epic A — Project skeleton & config (closed)
`uv`-managed package, Typer CLI surface, `RunPaths` run-dir generator (collision-safe UTC ids),
structlog JSONL logging, `SiftmeshSettings` (env `SIFTMESH_` / `siftmesh.toml` / init precedence,
`extra="forbid"`), `doctor` health checks. **61 tests.**

### Epic B — Evidence vault & run directory (closed)
Real `init-case`: streaming SHA-256 (constant memory at any size) → `evidence_manifest.json` +
`hashes.sha256` (`sha256sum -c`-compatible) + `readonly_mounts.json` (posture record) +
`derived_artifacts.json` + chain-of-custody `custody_log.jsonl`. Write-gate `safe_write_path`.
**34 tests.**

### Epic C — Schemas & ledgers (closed)
Pydantic v2 typed layer: `ToolResult` (provenance base), `Claim` (the **hallucination firewall** —
a non-`unsupported` claim cannot be constructed without `source_artifact` + `source_sha256` +
`tool_name` + `tool_call_id`), `TaskContract` (+ `InputArtifact`/`RetryPolicy`/`SafetyPolicy`),
`ToolCall`/`CriticVerdict`, `RunState`, `AgentProfile`, `Workflow`, `EvidenceManifest`,
`CustodyEvent`. JSONL ledgers (validate-before-write; corrupt line → error, never silent skip).
JSON-Schema export. **41 tests.**

### Epic D — Typed MCP tool gateway (closed)
**Exactly 10** typed, evidence-safe, audited forensic tools over FastMCP stdio, allowlist-enforced,
fixed-argv, fail-closed:

| Tool | Backend | Real library / host tool |
|---|---|---|
| `compute_hash_manifest` | real | stdlib hashing |
| `create_readonly_evidence_vault` | real | stdlib (posture) |
| `parse_evtx_security` | real / sift_lane | evtx (pyevtx-rs) in-process / EvtxECmd |
| `parse_evtx_powershell` | real / sift_lane | evtx in-process / EvtxECmd |
| `analyze_prefetch` | real | libscca (pyscca) in-process |
| `extract_registry_run_keys` | real / sift_lane | regipy in-process / RECmd |
| `build_timeline` | real | own merge over real rows (evtx/prefetch/$MFT) |
| `validate_claim_evidence` | real | own grader over manifest + tool ledger |
| `extract_artifacts_from_image` | sift_lane | Sleuthkit `mmls/ifind/icat/fls` (.E01/raw) |
| `analyze_memory` | sift_lane | Volatility 3 (subprocess; VSL → never imported) |

Every tool call is audited by `mcp_gateway.audit_exec.run_tool` → `TOOL-NNN`, `tool_calls.jsonl`,
custody, derived-artifact registration. **64 tests.** (See `work_till_epicd.md` for the real ROCBA
evidence run.)

### Epic E — Planner & Deep Context Agent (closed)
`siftmesh plan` is the deterministic front door (no LLM, manifest-metadata-only):
- `orchestrator/artifact_router.py` — the DRY family→tool router (single source of truth), import-
  guarded against forbidden/unknown tools; disambiguates `Security.evtx` vs the bare `SECURITY`
  hive; `$MFT`/`System.evtx` are timeline/context-only.
- `orchestrator/deep_context.py` — `context_pack.md` builder + **filename datamarking** (a filename
  like `# ignore previous.evtx` is rendered as inert inline-code data, never a heading); LLM
  enrichment seam is the identity function (deferred to F8).
- `orchestrator/planner.py` — writes the 5 context files + one `TaskContract` per actionable
  artifact (exactly one tool, input straight from the manifest, run-scoped safety) + a
  `build_timeline` task; `investigation_plan.yaml` is a typed acyclic step graph (`schemas/plan.py`).
  Byte-stable per manifest. `--review-only` records the flag (engine-stop enforcement → Epic H).
**42 tests.**

### Epic F — Executor adapters & dispatch/collect (complete; node open)
Turns the planner's TaskContracts into executed, evidence-anchored results. **31 tests.** Detailed
below (§6).

---

## 6. Epic F deep-dive

### 6.1 The adapter seam (F1)
`adapters/base.py` — `ExecutorAdapter` (ABC) with a concrete **template** `run(contract, ctx)`:
1. guards the contract's `allowed_tools` (`registry.assert_tool_allowed` — refuses forbidden/unknown);
2. calls the abstract `_execute(contract, ctx) -> TaskResult`;
3. writes `results/TASK-XXX.result.json` via `safe_write_path`;
4. appends exactly one `AgentCall` to `audit/agent_calls.jsonl`.

`AdapterContext(run, evidence_root, settings, attempt, requested_profile, critic_feedback)` carries
what the contract can't (`attempt`/`critic_feedback` are forward-compat for Epic G retries).
A **registry** resolves an adapter by `assigned_agent_profile` and **falls closed to the
deterministic floor** when the profile is unknown or a live adapter's CLI/key is absent.

### 6.2 Deterministic real-tool executor (F2) — the §2B floor
`adapters/deterministic_executor.py` runs the **real** Epic-D tool for the contract's tool and
derives **deterministic, evidence-anchored** Claims. It does not re-audit (the tool wrapper already
writes `tool_calls.jsonl`). Per-tool claim rules (fixed text/status/confidence):
- **security evtx** → one `confirmed` claim per high-signal EventID `{4624,4625,4672,4688,4720,4726}`
  + a parsed-count summary;
- **powershell evtx** → notable `{4103,4104}`; 0 rows → one `inferred` absence claim;
- **prefetch** → `"{exe} executed {n} time(s)."`;
- **registry** → one `confirmed` claim per Run key + a count summary;
- **timeline** → one `inferred` "unified timeline … N events across M sources";
- **memory** → counts + each malfind row as `inferred` + `requires_human_review` (the executor
  **never assigns final severity** — CLAUDE §10).
Every claim is anchored (`tool_call_id` + `source_sha256` + `tool_name`) or explicitly `unsupported`.
A recoverable tool error → `TaskResult.status="retry_required"` (`retry_cause`); a missing backend
fails closed as `error` (not retryable).

### 6.3 Spotlight + injection scanning (F3)
`adapters/spotlight.py` (pure): `wrap_evidence(rows, *, run_id)` (per-run delimiter sentinel +
token datamarking + "DATA, not instructions" banner — used only for live-agent prompts) and
`scan_injection(text)` (regex signatures: `ignore previous instructions`, `disregard above`,
`system:`, role tags, `you are now`, base64 blobs — excluding bare sha256). Hits →
`InjectionAlert` in `claims/injection_alerts.jsonl`. **Logged only** in Epic F — it never changes
control flow (criterion 4: "injection changes nothing"); the consequence is Epic G.

### 6.4 dispatch / collect (F4/F5) + audit (F6)
`orchestrator/scheduler.py`:
- `dispatch_run` recovers the evidence root from `readonly_mounts.json` (or `--evidence`), refuses a
  `review_only` plan (E8), enforces `caps.max_agent_tasks` (sequential — parallelism is Epic H),
  runs each task's adapter, and logs `task_dispatched`.
- `collect_run` validates each `TaskResult` envelope and reports missing/malformed without crashing.
- `AgentCall` (`AGENT-NNN`) is written once per dispatch (in the adapter template).

### 6.5 Live & shell adapters (F7/F8)
- `generic_shell_adapter.py` (F7) — fixed-argv `[cmd, prompt_file, result_file]`, `shell=False`,
  timeout; absent command → falls to the floor; failure/timeout/no-result → graceful `error`.
- `claude_adapter.py` / `opencode_adapter.py` (F8, **CORE** live executor) — thin wrappers. The
  Claude adapter writes a per-run MCP config pointing at `siftmesh mcp-serve` so the live agent is
  **constrained to the 10 typed tools (no raw shell)**, narrowed to the contract's single tool.
  `available()` requires the CLI **and** `ANTHROPIC_API_KEY`; otherwise the registry falls closed
  to the floor. **All CLI flags are isolated in `_build_claude_argv` and are UNVERIFIED — they must
  be re-confirmed (`claude --help` / docs) before any live run. Live validation against real
  evidence is HUMAN-GATED (§2B): unit tests mock the subprocess boundary only; no live agent is run
  autonomously against evidence.**

### 6.6 Genuine retry triggers (F9)
Epic F **records** genuine retry causes — a recoverable real-tool error, and (for the live agent) a
genuine unbound/over-broad claim — as `status` + `retry_cause` on the result. It never scripts a
failure and never decides the retry; the **decision** is Epic G's pure `decide()` function.

---

## 7. How to run it (commands)

All commands run under `uv`. The full deterministic pipeline (no API keys needed — the deterministic
floor runs real tools over real artifacts):

```bash
# 0. Verify the host + backends (fails closed on a missing dep)
uv run siftmesh doctor

# 1. Hash + seal evidence into a new run dir
uv run siftmesh init-case ./case01 --evidence ./evidence
#    -> case_runs/RUN-YYYYMMDD-HHMMSS/  (note the printed run id)

# 2. Generate the deterministic investigation plan + task contracts
uv run siftmesh plan ./case01/case_runs/RUN-*           # add --review-only to stop at planning

# 3. Execute the task contracts (deterministic real-tool floor by default)
uv run siftmesh dispatch ./case01/case_runs/RUN-*       # --task TASK-001 to run just one
#    -> results/TASK-*.result.json + claims/claim_ledger.jsonl + audit/agent_calls.jsonl

# 4. Validate the result envelopes
uv run siftmesh collect ./case01/case_runs/RUN-*

# (Disk image / memory — Epic D, audited, fail-closed)
uv run siftmesh extract-artifacts ./case01/case_runs/RUN-* --image disk.E01 --evidence ./evidence
uv run siftmesh analyze-memory   ./case01/case_runs/RUN-* --memory mem.raw  --evidence ./evidence

# Expose the typed tools to an MCP-capable agent (the 10 allowlisted tools, no raw shell)
uv run siftmesh mcp-serve
```

**Selecting the live agent (F8) — human-gated, requires keys + CLI:**
```bash
export ANTHROPIC_API_KEY=...           # the adapter falls closed to the floor if unset
uv run siftmesh dispatch ./case01/case_runs/RUN-* --agent-profile claude_headless
```
The exact `claude -p` flags must be re-confirmed before a live run; absent CLI/key → deterministic
floor automatically.

---

## 8. Configuration knobs (`SiftmeshSettings`, env `SIFTMESH_…` / `siftmesh.toml`)

`backend_mode` (real/sift_lane/auto) · `evidence_mode=read_only` · `raw_shell=False` ·
`allow_destructive_tools=False` · `caps.{max_iterations,max_agent_tasks,max_parallel_tasks,
max_tool_runtime_seconds}` · `extraction_tools_enabled` · `vol_path` · `vol_symbol_dirs` ·
`ez_tools_dir` · **(Epic F)** `executor_selection` (deterministic/live/auto; deterministic is the
safe default) · `default_agent_profile` · `claude_cli_path` · `opencode_cli_path` ·
`generic_agent_cmd` · `agent_timeout_seconds`. Nested caps via `SIFTMESH_CAPS__MAX_ITERATIONS=7`.

---

## 9. Testing & quality gates

- **273 tests pass**, organized per epic under `tests/EPIC_<X>_TESTS/` (unique basenames; no
  `__init__.py`): A=61, B=34, C=41, D=64, E=42, F=31.
- **CI-safe & real:** tests run real tools over **committed public fixtures** in
  `tests/fixtures/forensic/` (omerbenamram/evtx, EricZimmerman/Prefetch, omerbenamram/mft,
  mkorman90/regipy) — never SANS evidence. Subprocess/agent boundaries are mocked; no API keys.
- Epic F validation over the real fixtures: `dispatch` → real claims (`CMD.EXE executed 3 time(s)`,
  registry `Sidebar`, `EventID 4625`, a unified timeline) each bound to a real `TOOL-NNN`.
- **Gates (all green):** `uv run ruff check .` · `uv run ruff format --check .` ·
  `uv run mypy` (73 source files, strict) · `uv run pytest` · `uv run siftmesh doctor` (allowlist=10).

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run siftmesh doctor
```

---

## 10. Hard rules / invariants (enforced)

- **REAL-ONLY:** no mock/placeholder/synthetic forensic output; missing backend fails closed.
- **Allowlist = exactly 10 tools**; forbidden tools (raw shell / destructive) can never register.
- **Volatility 3 is VSL → invoked as a subprocess only, never imported** (guard test).
- **No writes outside the run dir**; never modify/commit/CI SANS evidence; evidence treated as hostile.
- **Privilege separation:** planner never executes/reads evidence; executor runs only the contract's
  one tool; live agent constrained to the typed tools via MCP config.
- **Strictly sequential epics**; only a human closes an epic node.
- **No AI co-authorship** on any commit (maintainer-authored).
- **Live agent validation is human-gated** — never run autonomously against forensic data.

---

## 11. What's next — Epic G (the P0 "HERO")

Closing the Epic F node (`bd close Project_SIFTAMESS-803`) unblocks **Epic G — Critic &
Self-Correction Loop**: the deterministic Layer-1 critic validates each result's claims (rejecting
unsupported/over-broad ones), the pure `decide()` function (CLAUDE §12) drives retry/escalate/human,
retry contracts tighten success criteria, the injection alerts gain their downgrade/human-review
consequence, and the **live agent's genuine self-correction** (attempt-1 unbound claim → critic
rejects → retry → revised claim) gets wired end-to-end. Then Epic H makes `siftmesh run`
(manual/review-only/auto-human-loop/auto) real over one deterministic state machine.
```
A✓  B✓  C✓  D✓  E✓  F(done, gate open)  →  G  →  H  →  K J L M N I P O
```

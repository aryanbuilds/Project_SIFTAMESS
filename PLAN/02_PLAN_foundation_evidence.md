# PLAN 02 - Foundation & Evidence Runtime (Epics A, B, C)

_Phases 1–3 of the build. These deliver the chassis (A), the evidence integrity boundary (B), and the type system + ledgers (C) that every later Epic stands on. Serves judging criteria 4 (constraints), 5 (audit trail), 2 (accuracy primitives)._

---

## Cross-cutting decisions (made once, reused everywhere)

- **D1 - Provenance is one base model.** A single Pydantic `ToolResult`/`ProvenanceMixin` base (C1) carries `tool_call_id, source_artifact, source_sha256, start_time_utc, end_time_utc, status, structured_result_path, raw_output_path, error_code, backend, tool_version`. Every tool return subclasses it; fields are never re-enumerated per tool.
- **D2 - Audited execution is one decorator.** "allocate `TOOL-NNN` → stamp start → run backend → stamp end → write output under run dir → append one `tool_calls.jsonl` line" is a single context manager (Epic D). Foundation provides its building blocks (logger, path policy, ledger writer).
- **D3 - One central write-gate.** All filesystem writes route through `evidence/path_policy.py::safe_write_path(run_dir, rel)`, which raises `PathPolicyViolation` if the resolved path escapes the run dir or touches original evidence.
- **D4 - UTC everywhere.** Run IDs, timestamps, and logs use UTC ISO-8601; the timezone choice is documented in `evidence_integrity.md`.
- **D5 - Schema-first.** Pydantic models are the contract; I/O modules serialize them. A model that fails validation is never written to disk.

---

# EPIC A - Project Skeleton & Config

**Goal:** A runnable, installable Python package exposing the `siftmesh` Typer CLI, with config loader, run-directory generator, base JSONL logger, baseline tests, and CI on Ubuntu (= the SANS SIFT / Ubuntu target).

**Judging criteria:** 6 (clean install + `--help`); foundation for 5 (logger). **Dependencies:** none (root epic).

| Task | Title | Description | Key files | Deps | Acceptance (testable) | Eff | Risk |
|---|---|---|---|---|---|---|---|
| A1 | Packaging & license | `pyproject.toml` (hatchling build backend), **`uv` for env/deps/install** (not pip/venv), Apache-2.0 `LICENSE`, metadata, `console_scripts` entry `siftmesh = siftmesh_core.cli:app`, deps added via `uv add` + pinned in `uv.lock` (typer, pydantic≥2, jinja2, structlog, pyyaml, mcp, pytest, regipy). | `pyproject.toml`, `uv.lock`, `LICENSE`, `siftmesh_core/__init__.py` | - | `uv sync` (or `uv pip install -e .`) succeeds; `uv run siftmesh --help` works / `siftmesh` on PATH; LICENSE is Apache-2.0. | S | dep drift → pin + commit `uv.lock` |
| A2 | CLI entrypoint skeleton | Typer `app` with all stage/automation/inspection commands registered as **stubs** that print "not implemented" and exit 0. Sub-typers `tasks`, `claims`, `audit`. | `siftmesh_core/cli.py` | A1 | `siftmesh --help` lists init-case, plan, dispatch, collect, critique, report, replay, run, resume, status, tasks, claims, audit; exit 0. | M | large surface - freeze early |
| A3 | Config loader | Defaults + optional `siftmesh.toml`/env → Pydantic `Settings`: caps (max_iterations=3, max_agent_tasks=10, max_parallel_tasks=3, max_tool_runtime_seconds=300), backend mode (`real`/`sift_lane`/`auto` - never `placeholder`; see PLAN/08), tool paths, platform detection. | `siftmesh_core/config.py` | A1 | `Settings()` returns documented defaults; override works; invalid config → clear error. | S | low |
| A4 | Run-directory generator | Create `case_runs/RUN-YYYYMMDD-HHMMSS/` with full subtree (context, evidence, tasks, results, claims, audit, reports); collision-safe (`-NN`); returns a `RunPaths` helper. | `siftmesh_core/run_dir.py` | A1,A3 | call yields all 7 subdirs; UTC timestamp format; same-second second call does not clobber. | S | tz → UTC, documented |
| A5 | Base JSONL logger | structlog append-only JSONL writer, UTC ISO-8601, one event/line `{ts,event,level,run_id,…}`. Backs `orchestration_events.jsonl` and later ledgers; routes through path policy once B lands. | `siftmesh_core/logging.py` | A4 | appends valid JSON-per-line; ts parse as UTC; concurrent appends don't corrupt. | M | append atomicity → write+flush per line |
| A6 | Initial tests + smoke | pytest config, `tests/` package, smoke tests (CLI help exit 0; run-dir tree; logger round-trip). | `tests/test_cli_modes.py`(smoke), `tests/conftest.py` | A2,A4,A5 | `pytest` green on baseline. | S | low |
| A7 | CI pipeline | GitHub Actions on `ubuntu-latest` (= the SANS SIFT / Ubuntu target; a Windows runner is optional and not required), Python 3.11, via **`astral-sh/setup-uv` + `uv sync`** then **`uv run`** pytest + ruff + mypy. | `.github/workflows/ci.yml` | A6 | CI green on Ubuntu. | S | path separators → pathlib discipline (kept as hygiene) |

**Design notes (A):** Typer over Click for typed params/auto-help and velocity. Stub-all-commands-now freezes the public CLI surface so docs/demo scripts don't churn. UTC run IDs + logs enforce forensic timestamp discipline (criterion 5). Linux-first (dev + target = SANS SIFT / Ubuntu; see PLAN/08 §0.1): CI runs on Ubuntu (= the deployment target), and `pathlib` discipline is kept from day one as good hygiene regardless of OS.

**Tests (A):** CLI `--help` exits 0 and lists required commands; run-dir tree created; JSONL logger round-trips a valid line.

---

# EPIC B - Evidence Vault & Run Directory

**Goal:** `init-case` safely ingests evidence - SHA-256 hashes every file, writes manifest + checksums + read-only/derived registries + policy doc, and guarantees all writes stay in the run dir while originals are never touched.

**Judging criteria:** 5 (chain of custody), 4 (architectural path policy + read-only), 2 (claims anchored to hashed artifacts). Honors ISO 27037, SWGDE, NIST SP 800-86 / IR 8387. **Dependencies:** Epic A; consumes C's `EvidenceManifest` schema (pull C1/C6 forward).

| Task | Title | Description | Key files | Deps | Acceptance (testable) | Eff | Risk |
|---|---|---|---|---|---|---|---|
| B1 | SHA-256 hash utils | Streaming (chunked) SHA-256 of files; recursive dir walk → `(rel_path, sha256, size, mtime_utc)`; symlink-safe; deterministic ordering. | `evidence/hash_utils.py` | A1 | fixture hashes match `sha256sum`; large file no OOM; stable ordering. | S | symlink loops → realpath + visited set |
| B2 | Path policy (write-gate) | `safe_write_path(run_dir, rel)` resolves real paths; raises `PathPolicyViolation` on outside-dir, `..` traversal, absolute escape, or original-evidence path. Central (D3). | `evidence/path_policy.py` | A4 | in-run allowed; outside/traversal/evidence-path/symlink-to-outside blocked. | M | path normalization → `Path.resolve()` / realpath (POSIX, the SIFT target) |
| B3 | Read-only handling | Record original evidence locations + read-only posture; separation principle (never write to source); produce `readonly_mounts.json`. (MVP uses posture + guarantee-by-construction; OS-level read-only mounting is a documented Linux enhancement - see design notes B.) | `evidence/readonly.py` | B1,B2 | `readonly_mounts.json` lists sources as read_only; no write ever issued to a source. | S | OS-level RO mount is a Linux enhancement, deferred in MVP; honest in docs |
| B4 | Manifest builder | `evidence_manifest.json` (case/run id, created_utc, tool version; per-file path/sha256/size/mtime/evidence_type guess) + `hashes.sha256` (sha256sum-compatible). Serializes C's `EvidenceManifest`. | `evidence/manifest.py` | B1, C6 | manifest validates; `hashes.sha256` verifiable by `sha256sum -c`; one entry/file. | M | model in `schemas/`, I/O here |
| B5 | Derived-artifacts registry | `derived_artifacts.json`: append-only map of every derived/output file → source artifact + source_sha256 + producing tool_call_id. | `evidence/derived.py` | B4 | adding derived records source+hash+producer; originals never mutated. | S | low |
| B6 | Evidence policy doc | Generate `context/evidence_policy.md` from template (read-only posture, hashing standard, separation, injection stance, ISO/SWGDE/NIST citations). | `evidence/policy.py`, `reports/templates/evidence_policy.md.j2` | A4 | file generated with case values; lists standards + write restriction. | S | low |
| B7 | `init-case` command | Wire B1–B6 into `siftmesh init-case CASE_PATH --evidence EVIDENCE_PATH [--run-name]`: create run dir, hash, write all registries/policy, append `orchestration_events.jsonl`. | `cli.py`, `evidence/vault.py` | A2,A4,B1–B6 | one command → all expected files under `case_runs/RUN-*/`; event logged; evidence unchanged. | M | big evidence → stream + progress |
| B8 | Orchestration audit wiring | Each init-case transition (start/hash-complete/manifest-written/done) appends a structured `orchestration_events.jsonl` event. | `ledgers/audit_log.py` | A5,B7 | events present, UTC, ordered, replayable. | S | low |
| B9 | Chain-of-custody ledger + re-hash verification | `ledgers/custody_ledger.py` → append-only `evidence/custody_log.jsonl` (`CustodyEvent` from C10, pulled forward like B4/EvidenceManifest); re-hash originals **before/after** each access and assert unchanged (records a `source_rehash_verified` event); capture `tool_version`/`parser_version` per tool call. ISO 27037 / NIST SP 800-86 alignment; non-goal: not court-admissible. | `ledgers/custody_ledger.py`, `schemas/custody.py` | B1,B2 | each access → a `custody_log.jsonl` event; before/after hash equal; invalid event never persisted. | M | criterion-5 differentiator |

**Design notes (B):** **Posture-recorded read-only, not OS write-blocking, in MVP.** Because dev and target are Linux (SANS SIFT / Ubuntu; PLAN/08 §0.1), OS-level read-only access to sources *is* genuinely available - e.g. loopback `mount -o ro …`, `blockdev --setro`, or read-only bind mounts - and is a documented Linux enhancement. The MVP nonetheless takes the pragmatic cut of recording posture + guarantee-by-construction that no code path writes to a source, verified by a before/after hash test; the choice (and the deferred OS-level RO mount) is stated honestly in `evidence_integrity.md`. **Hash-before-anything** ordering starts chain of custody at ingest. Manifest schema in `schemas/`, I/O in `evidence/` for reuse by tools/reports.

**Tests (B):** `test_evidence_manifest_created`; `test_original_evidence_not_modified` (hash before/after init-case == unchanged); `test_path_policy` / `test_write_paths_restricted_to_run_directory`; `test_hashes_sha256_verifiable`.

---

# EPIC C - Schemas & Ledgers

**Goal:** The Pydantic v2 type system + JSONL ledger utilities with hard validation rules (a Claim is invalid without `tool_call_id` + `source_sha256`). This is the hallucination firewall and the audit-integrity layer.

**Judging criteria:** 2 (validators make unsupported claims structurally rejectable), 5 (typed + exportable JSON Schema + ledgers), 4 (validation is architectural). **Dependencies:** Epic A; **on the critical path before Epic D.**

| Task | Title | Description | Key files | Deps | Acceptance (testable) | Eff | Risk |
|---|---|---|---|---|---|---|---|
| C1 | Provenance base + ToolResult | `ToolResult`/`ProvenanceMixin` (D1) with all provenance fields; every tool return subclasses it. | `schemas/tool_result.py` | A1 | validates; missing required provenance → `ValidationError`; JSON Schema exportable. | M | lock field names - many consumers |
| C2 | Claim schema + validators | `Claim`: claim_id, task_id, status{confirmed/inferred/contradicted/unsupported}, claim, confidence, evidence_type, source_artifact, **source_sha256**, tool_name, **tool_call_id**, timestamp_utc?, supporting_evidence_refs, contradicting_evidence_refs, requires_human_review. **Validator: invalid without `tool_call_id` AND `source_sha256`**, except status=`unsupported` (the explicit no-evidence record). | `schemas/claim.py` | A1 | claim missing refs rejected; valid passes; status enum enforced; `unsupported` asymmetry handled. | M | model the asymmetry explicitly |
| C3 | TaskContract schema | task_id, role, objective, assigned_agent_profile, allowed_tools, input_artifacts(path+sha256+mode), context_packet, output_required, success_criteria, retry_policy, **safety_policy**(required). | `schemas/task.py` | A1 | task without `safety_policy` rejected; YAML↔model round-trips. | M | keep aligned with GUIDELINES §9 example |
| C4 | ToolCall, CriticVerdict, RunState | `ToolCall`(request: tool_name, args, tool_call_id, requested_utc); `CriticVerdict`(accepted/accepted_with_downgrade/retry_required/escalation_required/human_review_required/rejected + reasons + affected_claim_ids); `RunState`(run_id, state, iteration counters, gates). | `schemas/audit.py`, `schemas/run.py` | A1 | each validates; enums enforced; RunState → resumable snapshot. | M | types here; engines elsewhere |
| C5 | AgentProfile + Workflow | `AgentProfile`(profile_id, kind, model tier, cost class); `Workflow`(workflow_id, mode, limits, approval_gates, safety, agents, retry_policy, steps) per `OVERALL_PLAN §5`. | `schemas/agent_profile.py`, `schemas/workflow.py` | A1 | sample triage YAML parses into `Workflow`; invalid mode/limits rejected. | M | schema only |
| C6 | EvidenceManifest schema | `EvidenceFile` + `EvidenceManifest` consumed by B4/B5. | `schemas/evidence.py` | A1 | manifest from B validates; derived entries validate. | S | coordinate field names with B |
| C7 | JSONL ledger utilities | Generic append-one-validated-model + stream-read-validate for claim/contradiction/unsupported/confidence/injection + audit logs (agent_calls, tool_calls, token_budget, retries, orchestration_events). Append routes through path policy (D3) and **validates before write**. | `ledgers/claim_ledger.py`, `contradiction_ledger.py`, `audit_log.py`, `injection_alerts.py`, `task_ledger.py` | A5,B2,C1–C6 | invalid model never persisted; read yields typed objects; corrupt line → clear error, not silent skip. | M | append atomicity → write+flush; one-writer documented |
| C8 | JSON Schema export | Export each model via Pydantic v2 `model_json_schema()` for docs + external-agent contract validation. | `schemas/__init__.py` helper | C1–C6 | emits valid JSON Schema for Claim/Task/ToolResult. | S | low |
| C9 | Schema/ledger tests | Validation + round-trip tests (below). | `tests/test_claim_validation.py`, `tests/test_task_contracts.py` | C1–C7 | all green. | S | low |
| C10 | `CustodyEvent` schema (chain-of-custody) | `CustodyEvent`: event_type{evidence_ingested/source_rehash_verified/tool_invoked/derived_written/custody_transfer}, run_id, artifact, source_sha256, action, actor, tool_name, tool_version, parser_version, start/end_time_utc, result. Validate-before-write. Backbone of the B9 custody ledger (criterion-5 differentiator); ISO 27037 / NIST SP 800-86. | `schemas/custody.py` | A1 | validates; missing required field → `ValidationError`; JSON Schema exportable. | S | low |

**Design notes (C):** **Validation is the hallucination firewall (criterion 2):** because a `Claim` cannot serialize without `tool_call_id`+`source_sha256`, an unsupported assertion physically cannot enter `claim_ledger.jsonl` as a confirmed claim - it can only land in `unsupported_claims.jsonl`. **Validate-before-write** in ledgers means ledgers can never hold a malformed record (criterion 5). The `unsupported` status is the one Claim allowed to lack evidence and is routed to its own ledger - encoding "log, don't delete, never report as fact" in types. `CriticVerdict`/`RunState` are *types* here; the Critic engine (Epic G) and state machine (Epic H) that produce them live in PLAN 04.

**Tests (C):** `test_task_contract_schema_valid` (missing `safety_policy` rejected); `test_claim_requires_evidence_reference`; `test_critic_rejects_missing_tool_call_id` (the Claim validator + the `validate_claim_evidence` primitive the Critic will call); JSONL round-trip (append N, read equal; invalid never persisted).

---

## Sequencing (Days 1–3 of the 11-day schedule)

```
Day 1: A1–A7  (package, CLI stubs, config, run dir, logger, tests, CI)
Day 2: B1–B8  + pull C1/C2/C6 forward so B4 binds real schemas
Day 3: C3–C9  (remaining schemas, ledgers, JSON-Schema export, tests) - FREEZE schemas
```

**Pragmatic cuts (A–C):** OS-level read-only mounting (available on the Linux target - `mount -o ro` / `blockdev --setro`) is deferred as a documented enhancement; the MVP instead records posture + guarantee-by-construction + a before/after hash test. Everything else in A–C is achievable in the window.

**Forward consumers (built in later PLANs):** `ToolResult`/audited-exec → Epic D; `Claim`/ledgers → Epics G, J; `TaskContract` → Epics E, F; `RunState` → Epic H; `Workflow`/`AgentProfile` → Epics H, I.

# PLAN 07 — Testing, Documentation & Submission (Epics M, N, O)

_The reliability + delivery workstream. Full test suite + CI (M), all written docs mapped to the 8 mandatory submission artifacts with a go/no-go checklist (N), and the optional, deferred TUI (O). Serves criteria 4 (constraints, via tests), 5 (audit, via golden determinism), 6 (usability & documentation)._

---

# EPIC M — Testing & CI

**Goal:** Full pytest suite (all CLAUDE.md §14 named tests + bypass suite + golden/snapshot report tests + a deterministic REAL end-to-end test) with GitHub Actions CI (lint/type/test) on Ubuntu (the SANS SIFT target — Linux-first; see PLAN/08_REAL_TOOL_STACK.md §0.1). **Tests written alongside modules (TDD), not bolted on.** **Criteria:** 4, 5, 6; underpins reliability of everything. **Deps:** schemas (Epic C) onward; J for golden fixtures; K for the e2e demo run; L for bypass tests.

**Real-only testing gate (see PLAN/08_REAL_TOOL_STACK.md):** unit / schema / safety tests need NO real evidence and run autonomously in CI (they exercise the in-process typed tools — `evtx`/`regipy`/`pyscca`/`mft` — over tiny committed real artifacts, zero network, zero API keys). Integration / e2e tests that require the maintainer-provided real SANS SIFT workstation or larger real triage evidence are **human-gated**: STOP and ask the maintainer; never fabricate, seed, or synthesize evidence. This mirrors GUIDELINES §17 and PLAN/08 §4.

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| M1 | Test fixtures + factories | Reusable fixtures: temp run dir, sample manifest, sample claims/tool_calls/retries ledgers, the demo case. | `tests/conftest.py`, `tests/fixtures/*` | Epic C | fixtures build a valid run dir w/o network; usable by all test modules. | M | — |
| M2 | §14 required tests | All 10 named tests from CLAUDE.md §14 (manifest created; original evidence not modified; task contract schema valid; claim requires evidence ref; critic rejects missing tool_call_id; retry on malformed JSON; auto stops at max iterations; guided plan-gate approval; forbidden tool not exposed; write paths restricted). | `tests/test_evidence_vault.py`, `test_task_contracts.py`, `test_claim_validation.py`, `test_critic.py`, `test_state_machine.py`, `test_cli_modes.py`, `test_path_policy.py` | Epics B–H | all 10 present + green; each maps to a guideline rule. | L | written late → schedule TDD per phase |
| M3 | Golden/snapshot report tests | Snapshot the body (header-excluded) of `final_report.md`, `accuracy_report.md`, `dataset_documentation.md`, replay text — rendered from ledgers produced by the **real in-process tools** over committed real artifacts (NOT mock ledgers); assert byte-stability across two renders of identical ledgers. Snapshots of reports over the full K1 real evidence are **integration-gated on K1** (maintainer-provided; see PLAN/08_REAL_TOOL_STACK.md §4). | `tests/test_reports_golden.py`, `tests/golden/*` | J2–J7, K6 | re-render of fixed real-tool ledgers == golden body byte-for-byte; intentional change requires golden update. | M | flapping on ts/locale → enforce J2 determinism contract |
| M4 | Bypass suite integration | Wire L5 bypass tests into the suite + CI as a required gate. | (L5 files) | L5 | bypass suite runs in CI; any guardrail regression fails the build. | S | — |
| M5 | End-to-end test (recorded-golden + live) | Two complementary tests: (a) over the **recorded-golden** run (real committed ledgers, no keys/network) assert byte-stable report bodies + replay; (b) a **live** `siftmesh run --auto` over the real demo case asserts **properties** — all MVP artifacts exist, ≥1 **genuine** self-correction occurred, unsupported claim absent from final-report facts (NOT a byte-exact verdict trail). **Integration-gated on K1** real evidence + an agent/LLM for the live test (PLAN/08 §6). | `tests/test_demo_end_to_end.py` | K1, K3, K6, J3 | golden test reproduces byte-for-byte with no keys; live test asserts the self-correction property | M | live variance → assert properties; byte-exact only vs the recorded golden |
| M6 | GitHub Actions CI | Lint (ruff), type (mypy/pyright), test (pytest) — all run via **uv** (`astral-sh/setup-uv` + `uv sync` + `uv run`) — on Ubuntu (the primary runner = SANS SIFT target; Linux-first per PLAN/08 §0.1). A Windows runner is optional and not required — Ubuntu mirrors the real target. Coverage report; ~80% core, ~100% for schemas/evidence/critic/path_policy. | `.github/workflows/ci.yml`, `pyproject.toml` (tool config) | M1–M5 | CI green on Ubuntu; coverage gate enforced; badge in README. | M | keep `pathlib` for path-portability hygiene; the only real CI gate is real evidence (maintainer-provided), not OS coverage |

**Design (M):** Tests alongside modules (TDD), not a final-phase bolt-on — the inherited 12-day schedule had no test days; M is threaded through every phase, and the §14 tests double as the executable spec for the guidelines. **Ubuntu is the primary (and sufficient) CI runner** (matches SANS SIFT — dev + target are both Linux; the plan is merely authored on Windows, see PLAN/08 §0.1). A Windows runner is optional, not a gate. Golden tests rest on Epic J's determinism contract — if reports aren't byte-stable, snapshots flap, so M owns the assertion that proves J's claim.

### Consolidated required-test matrix (single source of truth)

| Test | Owning Epic/Task | Criterion |
|---|---|---|
| `test_evidence_manifest_created` | B/M2 | 5 |
| `test_original_evidence_not_modified` | B/L5/M2 | 4,5 |
| `test_write_paths_restricted_to_run_directory` | B/L5/M2 | 4 |
| `test_task_contract_schema_valid` | C/M2 | 4 |
| `test_claim_requires_evidence_reference` | C/M2 | 2 |
| `test_critic_rejects_missing_tool_call_id` | G/L5/M2 | 2,4 |
| `test_forbidden_tool_not_exposed` | D/L5/M2 | 4 |
| `test_retry_created_for_malformed_json` | G/M2 | 1 |
| `test_auto_mode_stops_at_max_iterations` | H/M2 | 4 |
| `test_guided_mode_requires_approval_at_plan_gate` | H/M2 | 1,4 |
| `test_self_correction_sequence_reproducible` | G/M5 | 1 (tiebreaker) |
| `test_bypass_injection` (+ 4 siblings) | L5/M4 | 4 |
| `test_demo_end_to_end` | M5 | 1,2,5,6 |
| `test_reports_golden` | J/M3 | 5 |
| `test_resume_roundtrip` | H/M2 | 5,6 |
| `test_manual_artifacts_equal_auto_artifacts` | H/M2 | 4,6 |

---

# EPIC N — Documentation & Submission Assets

**Goal:** Author all written docs and submission assets, mapping each to the 8 mandatory artifacts so none is missed. Includes the license check and the go/no-go gate. **Criteria:** 6 (deployment, extensibility), 5 (audit), with 4 via threat-model surfacing. **Deps:** J (generated reports), K (demo), L (threat model/diagram), M (CI/runbook).

### The 8-artifact traceability matrix (backbone — every row green to submit)

| # | Mandatory artifact | Owning task | Producing file(s) | Acceptance check |
|---|---|---|---|---|
| 1 | Public repo + MIT/Apache-2.0 license | N6 | `LICENSE` (Apache 2.0) | license present; repo public; `pyproject` license matches |
| 2 | Demo video ≤5 min (live terminal + narration) | N7 + K5 | recorded video | ≤5:00; live run + narration of the demo beats incl. self-correction |
| 3 | Architecture diagram w/ security boundaries | L6 / N3 | `docs/diagrams/security_boundaries.*` | labels all 5 boundaries; embedded in README + threat model |
| 4 | Written project description | N1 | `README.md`, `docs/project_description.md` | pitch, differentiation, how-it-works, extensibility |
| 5 | Dataset documentation | J5 / N4 | `docs/dataset_documentation.md` | provenance + structure + license + ground truth; hashes match manifest |
| 6 | Accuracy / false-positive report | J4 / N5 | `docs/accuracy_report.md` | precision/FP vs K2 ground truth; rejected FP shown |
| 7 | Local-deploy instructions / working software | N2 + M6 | `docs/try_it_out.md`, `docs/judge_runbook.md` | fresh clone → install → `run_demo` succeeds on Ubuntu/SIFT; the in-process real tools need **no API keys and no network** (real evidence is maintainer-provided; see PLAN/08_REAL_TOOL_STACK.md §4) |
| 8 | Structured execution logs (JSONL + timestamps) | run output / N8 | `audit/*.jsonl`, `execution_logs_sample.md` | timestamps + tool_call traceability; replay reconstructs timeline |

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| N1 | README + project description | Pitch, differentiation (evidence/claim ledger + adversarial critic + deterministic state machine + replayable audit), quickstart, architecture summary, extensibility, license + CI badges. | `README.md`, `docs/project_description.md` | J,K,L,M | covers what/why/how/run/extend/license; links the diagram. | M | — |
| N2 | `try_it_out.md` + `judge_runbook.md` | Fresh-clone deploy on Ubuntu/SANS SIFT (Linux-native demo — judges run on Linux/SIFT); exact commands; expected outputs; how to reproduce self-correction + read the ledgers. | `docs/try_it_out.md`, `docs/judge_runbook.md` | K5, M6 | a judge reproduces the demo + finds the self-correction event unaided. | M | untested instructions → validate on SIFT VM Day 11a |
| N3 | `architecture.md` | Static architecture (layers 0–6), security boundaries (L6 diagram), state machine, data flow, extensibility points. | `docs/architecture.md` | L6 | matches implemented modules; diagram embedded; boundaries labeled. | M | drift → write near-final |
| N4 | `evidence_integrity.md` | ISO 27037 / SWGDE / NIST SP 800-86 & IR 8387 alignment (SHA-256, chain of custody, read-only, originals-vs-derived, provenance). Explicit non-goal: NOT court-ready forensic soundness. | `docs/evidence_integrity.md` | L4 | cites each standard; states the non-goal prominently. | M | overclaiming → non-goal explicit |
| N5 | `accuracy_report.md` (publish) | The J4-generated report committed as a submission doc; methodology + limitations. | `docs/accuracy_report.md` | J4 | equals generated output; methodology described. | S | — |
| N6 | License check + LICENSE | Apache-2.0 `LICENSE` (the project's own license — submission artifact 1). Tool/connector dependency licenses (LGPL `libscca`, VSL Volatility 3, `regipy[full]`, libyal/TSK in Plaso) are **not a blocker — they are replaceable runtime deps** (PLAN/08 §0.1, §5); record them in a license note for awareness, but runtime dependency on them is fine. The one code-reuse rule that stays: **do not COPY source** from restrictive projects (vs. depending on them at runtime). | `LICENSE`, `docs/licenses.md` | — | Apache-2.0 `LICENSE` present and matches `pyproject`; license note records deps; no copied source from restrictive projects. | S | none — dependency licenses are replaceable, not a gate; only the project's own Apache-2.0 must be present |
| N7 | Demo video plan/script | ≤5-min shot list mapping to the demo beats; narration; live-terminal capture plan; recorded on the SIFT VM (Linux-native). | recorded video | K5 | video ≤5 min; covers hashing→plan→dispatch→tool→claims→critic-reject→retry→report→replay. | M | recording slips → schedule in final no-code window |
| N8 | `execution_logs_sample.md` | Curated excerpt of `audit/*.jsonl` + `claim_ledger.jsonl` showing timestamps + tool_call_id traceability + a self-correction entry. | `execution_logs_sample.md` | demo run | sample shows timestamped, traceable chain incl. self-correction. | S | — |
| N9 | Submission-completeness checklist | Single checklist asserting all 8 matrix rows green before Devpost submit. | `docs/submission_checklist.md` | all | every artifact row checkable; the go/no-go gate. | S | — |

**Design (N):** The 8-artifact matrix is the go/no-go gate — N9 blocks submission until all rows are green. Generated docs (accuracy/dataset) are committed as Epic J's deterministic output, not hand-maintained second copies that drift. **Reserve the final ~2 days for SIFT-VM validation + video + Devpost submission, no coding** — repo-public + video upload + form friction can sink half a day and must not land on June 15.

---

# EPIC O — Optional Ratatui TUI (LAST, deferred)

**Goal:** A read-only operator cockpit that reads run-dir files. Clearly optional; never contains core logic; **first legal cut if time is short.** **Criteria:** 6 (polish only). **Deps:** a fully stable CLI + complete run-dir files. Gated: do not start before J–N green.

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| O1 | TUI scaffold (read-only) | Ratatui app loads a run dir, renders panels from files; no orchestration/evidence/critic logic. (A Python `textual` fallback is acceptable if Rust cost is prohibitive — only after J–N green.) | `siftmesh_tui/Cargo.toml`, `src/main.rs`, `src/app.rs` | CLI stable | `siftmesh tui RUN_PATH` opens + reads files read-only. | M | Rust toolchain time → deferred; cut first |
| O2 | Panels | State machine, current gate, agent sessions, task queue, claim ledger, critic feedback, audit log, token/budget. | `siftmesh_tui/src/panels/{state,gate,agents,tasks,claims,critic,logs,budget}.rs` | O1 | each panel reflects run files; refresh on change. | L | — |
| O3 | TUI note in docs | Mark clearly optional; CLI is source of truth. | `README.md`, `docs/architecture.md` | O1 | docs state TUI is an optional read-only cockpit. | S | — |

**Design (O):** Rust/Ratatui adds toolchain + time cost with zero artifact dependency, so O is explicitly the first cut. If kept, it must remain a pure reader so it can never destabilize the CLI spine. Graduates to roadmap **R6**.

---

## Sequencing (threaded Days 1–11) + cut discipline

```
Days 1–9: M1 fixtures + M2 §14 tests written WITH each phase (TDD); M4 bypass wired as L5 lands
Day 9:    M3 golden, M5 e2e, M6 CI green — spine locked
Day 10:   N1/N3/N4/N6/N8 docs + L6 diagram — freeze code
Day 11a:  N2 try_it_out + judge_runbook (validated on SIFT VM), N5 publish, N7 script
Day 11b:  N7 record video, N6 final license check, N9 go/no-go, Devpost submit with buffer
O (TUI):  only if J–N green and time remains; otherwise cut.
```

**Global cut order (first→last):** O (TUI) → live agents/CAO → `replay.html` → MCP tools beyond the 4 core → K4 injection event. **Never cut:** the 8 artifacts · the self-correction sequence · the bypass suite.

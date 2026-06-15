# Tests - organized by epic

Test modules live under `EPIC_<X>_TESTS/`, matching the epic that owns the code under test
(docstrings carry the exact task tag, e.g. `B1`, `C7`, `D12`). `conftest.py` (shared fixtures) and
`fixtures/` (real upstream parser samples + golden JSON; **never SANS evidence**) stay at the
`tests/` root and apply to every subfolder.

| Folder | Epic | Covers |
|--------|------|--------|
| `EPIC_A_TESTS/` | A | CLI surface, config, run-dir, logging, doctor, debug inspection commands |
| `EPIC_B_TESTS/` | B | evidence vault: hashing, path policy, manifest, derived, custody, init-case, audit log |
| `EPIC_C_TESTS/` | C | schemas (ToolResult/Claim/Task), claim firewall, JSONL ledgers |
| `EPIC_D_TESTS/` | D | typed MCP gateway, backends (real + sift_lane EZ Tools), evtx/prefetch/registry/timeline, image + memory access, protocol-sift, validation, no-volatility-import guard |
| `EPIC_E_TESTS/` | E | deterministic planner: artifact router, investigation-plan schema, context pack + datamark, case brief/assumptions, tool map, task contracts, `plan` CLI, review-only, byte-stability |
| `EPIC_F_TESTS/` | F | executor adapters: deterministic real-tool executor (real-fixture claims), spotlight + injection alerts, `dispatch`/`collect`, agent_calls audit, generic-shell + claude/opencode adapters (mocked), genuine retry triggers |
| `EPIC_G_TESTS/` | G | critic & self-correction: pure `decide()` truth table, grade-claim refactor, structural verdicts + ledgers, contradiction/confidence/injection consequence, `critique`/`retry` CLI, governance self-correction sequence (crafted; live human-gated) |
| `EPIC_H_TESTS/` | H | the run engine: state machine, modes, caps, gates, resume, manual≡auto parity, `run` CLI |
| `EPIC_I_TESTS/` | I | agent profiles, multi-agent selection + fallback chain |
| `EPIC_J_TESTS/` | J | deterministic reports: loader, final/accuracy/dataset/architecture, replay, wiring |
| `EPIC_K_TESTS/` | K | live self-correction loop (agent-result parsing; subprocess mocked) |
| `EPIC_L_TESTS/` | L | the bypass suite: effect-asserting security tests for every guardrail |
| `EPIC_M_TESTS/` | M | golden report bodies (recorded-golden run) + end-to-end (MVP artifact checklist, subprocess smoke, skip-gated live property test) |

## Shared fixtures (M1 - one factory, no duplication)

The root `conftest.py` owns the real-run builder; per-epic conftests are thin wrappers
that keep their historical fixture names:

```python
make_real_run(*, plan=True, review_only=False, dispatch=False, critique=False, with_mft=False)
# -> (RunPaths, evidence_root)  - real fixtures, real manifest/readonly, real Epic-D tools
build_evidence(path, *, with_mft=False)   # just the evidence tree
```

Wrappers: `real_case` (F), `dispatched_case` (G/L), `dispatched_run`/`planned_run` (J),
`built_run`/`evidence_dir` (H - adds the persisted RunState). The Hypothesis profile
`siftmesh` (derandomize) is registered + loaded here, so property tests are replayable.

## Golden / recorded-run regression (M3)

`tests/golden/recorded_run/RUN-GOLDEN/` is a **real recorded run** (real ledgers from the
real tools over the committed fixtures - the §2B recorded-golden floor) and
`tests/golden/bodies/` holds the deterministic report bodies. Regen ONLY via:

```bash
uv run python tests/golden/record.py --update   # then review the diff and commit both dirs
```

## Required-test matrix (CLAUDE §14 + PLAN/07)

All 10 §14 names exist verbatim: `test_evidence_manifest_created` (B),
`test_original_evidence_not_modified` (L), `test_task_contract_schema_valid` (C),
`test_claim_requires_evidence_reference` (C), `test_critic_rejects_missing_tool_call_id` (G),
`test_retry_created_for_malformed_json` (G), `test_auto_mode_stops_at_max_iterations` (H),
`test_guided_mode_requires_approval_at_plan_gate` (H), `test_forbidden_tool_not_exposed` (D),
`test_write_paths_restricted_to_run_directory` (B). Matrix extras:
`test_manual_artifacts_equal_auto_artifacts` + resume roundtrip (H), `test_demo_end_to_end` +
goldens (M).

## Running

```bash
uv run pytest                       # full suite (testpaths=["tests"] recurses)
uv run pytest tests/EPIC_M_TESTS    # just one epic's tests
SIFTMESH_LIVE_E2E=1 uv run pytest -m live   # maintainer-only: live-agent e2e (claude CLI + auth)
```

New tests go in the folder of the epic whose code they exercise. All subprocess is mocked
(except the M5 entrypoint smoke, which spawns this repo's own CLI) and no SANS evidence is
used, so the suite is CI-safe on Ubuntu.

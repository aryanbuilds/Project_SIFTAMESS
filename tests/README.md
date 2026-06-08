# Tests — organized by epic

Test modules live under `EPIC_<X>_TESTS/`, matching the epic that owns the code under test
(docstrings carry the exact task tag, e.g. `B1`, `C7`, `D12`). `conftest.py` (shared fixtures) and
`fixtures/` (real upstream parser samples + golden JSON; **never SANS evidence**) stay at the
`tests/` root and apply to every subfolder.

| Folder | Epic | Covers |
|--------|------|--------|
| `EPIC_A_TESTS/` | A | CLI surface, config, run-dir, logging, doctor |
| `EPIC_B_TESTS/` | B | evidence vault: hashing, path policy, manifest, derived, custody, init-case, audit log |
| `EPIC_C_TESTS/` | C | schemas (ToolResult/Claim/Task), claim firewall, JSONL ledgers |
| `EPIC_D_TESTS/` | D | typed MCP gateway, backends (real + sift_lane EZ Tools), evtx/prefetch/registry/timeline, image + memory access, protocol-sift, validation, no-volatility-import guard |
| `EPIC_E_TESTS/` | E | deterministic planner: artifact router, investigation-plan schema, context pack + datamark, case brief/assumptions, tool map, task contracts, `plan` CLI, review-only, byte-stability |
| `EPIC_F_TESTS/` | F | executor adapters: deterministic real-tool executor (real-fixture claims), spotlight + injection alerts, `dispatch`/`collect`, agent_calls audit, generic-shell + claude/opencode adapters (mocked), genuine retry triggers |

## Running

```bash
uv run pytest                       # full suite (testpaths=["tests"] recurses)
uv run pytest tests/EPIC_D_TESTS    # just one epic's tests
```

New tests go in the folder of the epic whose code they exercise. All subprocess is mocked and no
SANS evidence is used, so the suite is CI-safe on Ubuntu.

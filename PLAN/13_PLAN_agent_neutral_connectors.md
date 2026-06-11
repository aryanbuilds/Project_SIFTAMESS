# PLAN 13 — Agent-neutral connector layer (Epic Q): headless-first, ACP next

_Status: **round 1 SHIPPED** (config-driven headless connector + onboarding); **round 2 PLANNED**
(ACP client + protocol-level permission gate). Maintainer-approved sequencing 2026-06-11._

## Goal

Make SIFTMesh genuinely **agent-neutral**: any CLI coding agent — Claude Code, Gemini CLI, Codex,
OpenCode, OpenClaw, … — is selectable with `--agent <name>`, with an **onboarding** step that detects
what's installed/authenticated and picks the best available. Governance is unchanged: connectors are
swap-in `ExecutorAdapter`s under the same deterministic FSM (ADR PLAN/12) — **"LLM proposes, code
decides"** holds for every agent. A missing/unready agent fails closed to the deterministic real-tool
floor (never a fake fallback).

## Decision: headless-first, ACP second

Two integration surfaces exist. We ship them in order:

1. **Round 1 (shipped) — config-driven headless connector.** One generic `HeadlessAdapter` launches
   any agent from a YAML `launch_argv` recipe (`gemini -p`, `codex exec`, `opencode run`, …), hands it
   the same spotlighted prompt, and parses its `{claims:[…]}` output through the same
   `parse_agent_result`. Adding an agent is a **profile row, not a new adapter**.
2. **Round 2 (planned) — ACP client + permission gate.** SIFTMesh becomes an Agent Client Protocol
   *client*; each agent runs as an out-of-process ACP server; SIFTMesh answers `session/request_permission`
   programmatically — the protocol-level "code decides" gate.

### Why this order (research, verified 2026-06-11)

- **ACP is real and viable for round 2.** Agent Client Protocol (Zed + JetBrains, **Apache-2.0**,
  JSON-RPC 2.0 over stdio, agent = out-of-process server, capability negotiation,
  `PROTOCOL_VERSION = 1`). Official **Python SDK `agent-client-protocol`** exists and is maintained
  (PyPI ~0.10.x, Apache-2.0, **async**, Pydantic models, `Client`/`ClientSideConnection`,
  `session/new` with an `mcpServers` array, client-side `session/request_permission` + `fs/*`
  handlers, programmatic deny without a human prompt).
  Sources: agentclientprotocol.com · github.com/agentclientprotocol/agent-client-protocol ·
  github.com/agentclientprotocol/python-sdk · pypi.org/project/agent-client-protocol.
- **But headless is the robust path *today*:**
  - Some agents **silently ignore MCP servers passed via `session/new`** (documented bugs). A gated
    ACP agent whose native tools are denied AND whose MCP config is ignored has **no tools at all** →
    every task fails. Headless `claude -p --mcp-config` is the path we already run and trust.
  - The Python ACP SDK is **async-only**; our `ExecutorAdapter._execute` is synchronous (wrappable via
    `asyncio.run`, but real glue).
  - ACP agents need their **Node adapter packages** (`npx @zed-industries/claude-code-acp`,
    `…/codex-acp`, `gemini --experimental-acp`, `opencode acp`) installed.
- **Correction to the original draft:** it proposed *reusing* an Epic-P `x_siftmesh` policy overlay
  (untrusted-by-default). That overlay is **plan-only — it does not exist in code.** The *enforced*
  governance that exists and that we rely on is: the contract's `allowed_tools`, the run-scoped MCP
  server (`_run_scope()` fails closed if `SIFTMESH_RUN_ROOT`/`SIFTMESH_EVIDENCE_ROOT` are unset), the
  deterministic critic (under-anchored claim → `unsupported`, never promoted), and `safe_write_path`.
  We enforce **those**; we do **not** add an unenforced trust-tier JSON (theater).

## Round 1 — what shipped

- **Schema** (`schemas/agent_profile.py`): `kind: "headless"`; config-driven fields `launch_argv`,
  `model_flag`, `extra_argv`, `native_tool_argv`, `auth_env`, `mcp_strategy`
  (`claude_flag`|`config_file`|`none`); `output_format: "agent_json"` (tolerant extract → claims JSON).
- **Adapter** (`adapters/headless.py`): generic `HeadlessAdapter` (available = CLI on PATH + an
  `auth_env` set; `_execute` = spotlighted prompt → fixed-argv `subprocess.run(shell=False)` →
  tolerant `extract_agent_text` → injection-scan → `parse_agent_result`) + thin `@register`
  subclasses `GeminiHeadlessAdapter` / `CodexHeadlessAdapter` / `OpenClawHeadlessAdapter`. Claude and
  OpenCode keep their existing adapters (no risky refactor). Reuses `build_task_prompt`,
  `parse_agent_result`, `scan_injection`, `safe_write_path`, the run-scoped MCP writer.
- **Profiles** (`agent_profiles.yaml`): `gemini_headless`, `codex_headless`, `openclaw_headless`.
- **Selection** (`cli.py`): `--agent gemini|codex|opencode|openclaw|claude|deterministic` — any live
  agent leads the preference chain; the registry fallback (`get_adapter`) walks requested → others →
  floor (no engine change).
- **Onboarding** (`doctor.py` + `cli.py`): `probe_agents()` → typed `AgentCapabilityMap`
  (`schemas/agent_capabilities.py`); `siftmesh doctor --agents` prints present/auth/tool-reachable +
  the chosen default; `siftmesh agents list` / `siftmesh agents inspect <id>`;
  `write_agent_capability_map()` → `context/agent_capabilities.json` (path-policed, snapshot-stable).
- **Tests** (`tests/EPIC_Q_TESTS/`, subprocess mocked): argv-from-profile, tolerant output parse,
  anchored→claim / unanchored→`unsupported` / unparseable→`retry`, availability, fallback to floor,
  `--agent` reorder, probe map (present/absent/auth), byte-stable map, `doctor --agents`, `agents`
  CLI. No live agent, no SANS evidence (CLAUDE §2B).

### Round-1 audit corrections (2026-06-11, workflow-verified)

A 22-agent MCP/web-grounded audit of the first round found and fixed several real issues (the live
CLI facts were confirmed against current docs; flags stay `verify-live` per CLAUDE §2B):

**Evidence safety (the agents ran weaker than the Claude adapter):**
- **Fail closed on un-sandboxed recipes.** A headless profile is dispatchable ONLY if it carries
  native-tool deny/sandbox flags (`native_tool_argv`) or reaches tools via `claude_flag` — else
  `available()` is False → floor. Shipped flags: codex `--sandbox read-only --ask-for-approval never
  --ephemeral` (+ mandatory `--skip-git-repo-check`); gemini `--approval-mode default` (auto-denies
  shell/write/web_fetch; never `--yolo`).
- **Pinned, run-scoped cwd** for every agent subprocess (claude/opencode/headless) via a fresh
  `run/scratch/<task>` dir — never the operator's CWD, from which these CLIs auto-load TRUSTED
  `GEMINI.md`/`AGENTS.md`/`CLAUDE.md` (a prompt-injection channel) and where workspace writes would
  escape the run-dir policy.
- **Minimized child env** (headless): only the agent's own `auth_env`/`env_passthrough` + an
  allowlisted base — so a gemini child can't read `ANTHROPIC_API_KEY`/cloud creds.
- **`claude_flag` now injects the full Claude sandbox block** (shared `claude_sandbox_flags`), not
  just `--mcp-config` — typed-tool wiring and native-tool denial can never be separated.
- **`--agent X` falls back only to the deterministic floor**, never to a *different* live agent
  (an operator who chose sandboxed Claude is never silently downgraded). Unknown `--agent` is a hard
  error, not a silent passthrough.
- **Claude adapter hardening:** added `--tools ""` (future-proof built-in kill-switch covering new
  tools the deny-list misses); `invoke_claude_text` (advisory path) gained `--strict-mcp-config` +
  `--tools ""` (it was leaking ambient claude.ai/user MCP servers into the tool-less call).

**Correctness:**
- **Codex `exec --json` is a JSONL event stream** — the old whole-stdout `json.loads` always failed,
  so every codex run would have been `retry_required`. `extract_agent_text` is now JSONL-aware (codex
  `item.completed` agent-message, gemini stream-json, opencode `type:text`) and recovers nested/
  escaped `{claims}` envelopes. Codex `--model` is now actually sent (was silently dropped).
- **Auth fidelity:** dropped `OPENAI_API_KEY` from codex (it's a false positive — codex reads
  `CODEX_API_KEY`); added cached-credential detection (`auth_files`: `~/.codex/auth.json`,
  `~/.gemini/oauth_creds.json`). Gemini model unpinned (CLI auto-routes; drift-proof).
- **`doctor --agents` honesty:** reports a `sandboxed` column; the default mirrors real dispatch
  (under the `deterministic` default it's the floor) and the ready live agent is surfaced separately
  as the `--agent` opt-in.

**Removed:** `openclaw` — research showed it is a personal-assistant gateway daemon (messaging
bridge with by-design shell + external delivery), not a workspace-scoped coding agent, and
`openclaw run` is not a real command; its delivery/shell surface conflicts with evidence safety.

### Honest tool-reachability (round 1)

Only Claude's `--mcp-config` (`mcp_strategy: claude_flag`) is **verified** to reach the run-scoped
typed tools today. Gemini/Codex/OpenClaw ship `mcp_strategy: none` and are tagged `verify-live`: they
**run** but reach no typed tools until per-run MCP wiring lands (round 2 / ACP, where `mcpServers` is
passed cleanly per session). Until then a non-Claude agent emits no anchored claims → critic rejects →
the run falls to the floor (fail-closed, never faked). `doctor --agents` reports `tools: verify-live`
so this is **never silently assumed**, and such an agent is never the auto-selected default (the
operator can still pick it explicitly with `--agent`).

## Round 2 — ACP client + permission gate (planned)

- **Q1** `adapters/acp_client.py`: subclass the SDK `Client`/`ClientSideConnection`; drive
  initialize → negotiate → `session/new` → `session/prompt` from the sync `_execute` via `asyncio.run`;
  `spawn_agent_process` fixed-argv.
- **Q2 (crown jewel)** permission gate: client-side `session/request_permission` + `fs/*` handlers —
  grant **only** a tool in the contract's `allowed_tools` whose paths resolve under the run dir over
  read-only evidence (reuse `safe_write_path`); else **deny + log** `agent_permission_denied` /
  `injection_alerts`. Protocol-level "code decides", no human in the loop.
- **Q3** `AcpAdapter` (implements `ExecutorAdapter`): spotlighted prompt → gated ACP session →
  `parse_agent_result` → `results/…` + `agent_calls.jsonl` (`backend="acp:<agent>"`).
- **Q4** run-scoped MCP bridge: pass our `mcp-serve` server (with `SIFTMESH_RUN_ROOT` /
  `SIFTMESH_EVIDENCE_ROOT`) in `session/new.mcpServers`; **best-effort** (some agents ignore it) with a
  fail-closed fallback to the headless path.
- **Q5–Q9** ACP profile rows (`kind: acp`), registry fallback chain (requested ACP → other ACP →
  headless → floor), `doctor --agents` extended to ACP, CLI surfaces.
- **§10 fact-hygiene (confirm at impl, do not assert unverified):** pin `agent-client-protocol` +
  record its license in NOTICE/SBOM (Epic N6); the exact ACP launch flag per agent; each agent's
  native-tool-disable flag + MCP-config shape; current `--model` strings + auth env names; the ACP
  `PROTOCOL_VERSION` in force.

## Drift-prone facts (verify on the maintainer box before a live run; CLAUDE §2B)

Model ids, launch flags, and auth env names are best-current (2026-06) and tagged `verify-live` in
`agent_profiles.yaml`. Headless launch recipes (best understanding): `gemini -p "<p>" --output-format
json`; `codex exec "<p>" --json`; `opencode run "<p>" --format json`; `claude -p "<p>" --output-format
json --mcp-config <file>`. Per-agent native-tool-deny flags are **not yet set** (unconfirmed) — add
them once verified; until then non-Claude agents are not a recommended autonomous default.

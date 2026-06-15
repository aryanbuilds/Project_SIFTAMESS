# PLAN 03 - Typed MCP Tool Gateway (Epic D)

_Phase 4 of the build. The forensic-tool boundary: a FastMCP (stdio) server exposing exactly eight typed, evidence-safe, audited tools - each with Pydantic args/returns, mandatory provenance, allowlist enforcement, and a swappable real (in-process) / SIFT-lane backend, with no raw shell and no forbidden tools. This is where judging criteria 4 (constraints) and 5 (audit trail) are won or lost._

> **Authoritative source:** [`PLAN/08_REAL_TOOL_STACK.md`](08_REAL_TOOL_STACK.md) is the confirmed real-only tool stack (research-verified via deepwiki + Tavily + primary sources). All 8 MVP tools have a **real backend buildable locally now**; this file must not contradict PLAN/08. The earlier "placeholder / mock / synthetic" backend strategy is **rejected and superseded** by PLAN/08.

---

## Where this fits

```
Layer 1 - Typed MCP forensic gateway (this Epic)
   server.py (FastMCP stdio) ── registry.py (allowlist) ── audit_exec.py (provenance)
        └─ tools/*.py  ──►  backends/{real, sift_lane}.py
```

**Depends on:** Epic A (run dir, config, logger), Epic B (hashing, path policy, manifest, derived registry), Epic C (`ToolResult`/provenance, `Claim`, JSONL ledgers). Sequence **after C's provenance/ToolResult/Claim land.**

---

## Foundational rules (real-only, in-process)

**All 8 MVP tools have a REAL backend buildable locally now** (see [PLAN/08_REAL_TOOL_STACK.md](08_REAL_TOOL_STACK.md) §3). There are **no placeholder backends, no mock executors, and no synthetic/seeded "fake-real" outputs** - judges and the maintainer see real tools running on real artifacts.

The buildable-now local real path is **100% in-process typed Python library calls** (`hashlib`/stdlib + `evtx` + `pyscca` + `regipy` + `mft`): **zero subprocess, zero shell surface**. There is literally no command string to inject into - this **strengthens criterion 4 (constraints)**, it does not complicate it.

Fixed-argv `subprocess.run([...], shell=False)` is reserved **only** for the optional backends - Plaso (native on Linux) and the optional SIFT-lane CLIs (EvtxECmd / PECmd / MFTECmd / Volatility 3) - where a subprocess boundary is simply the natural way to drive an external binary (license is not a blocker - these backends are replaceable; see [PLAN/08_REAL_TOOL_STACK.md](08_REAL_TOOL_STACK.md) §0.1, §5). For those wrappers the no-raw-shell rule still holds: no *generic* shell tool is ever exposed, only a fixed allowlist of binaries with fixed argv lists, and **no evidence-derived string is ever interpolated into a command**.

Every tool has an identical typed interface; backing is swappable behind a `Backend` protocol. Selection is `real` (local, in-process - the demo path) vs `sift_lane` (on the SIFT host); there is **no auto-placeholder fallback**. The swap real→sift_lane is a config change, not a rewrite.

---

# EPIC D - Typed MCP Tool Gateway (MVP)

**Goal:** Eight typed evidence-safe audited forensic tools over FastMCP stdio, no raw shell, no forbidden tools.

**Judging criteria:** 4 (allowlist registry + fixed-argv wrappers + no raw shell = testable bypass resistance), 5 (every call → `tool_calls.jsonl` with provenance), 2 (`validate_claim_evidence`), 3 (eight artifact families).

| Task | Title | Description | Key files | Deps | Acceptance (testable) | Eff | Risk |
|---|---|---|---|---|---|---|---|
| D1 | FastMCP server + allowlist registry | FastMCP stdio server; tools register through an **allowlist-only registry**; forbidden names cannot register; no generic-shell tool exists. | `mcp_gateway/server.py`, `mcp_gateway/registry.py` | A3,C1 | server starts; lists exactly the 8 tools; registering a forbidden name raises. | M | MCP SDK churn → pin version, verify via context7 at impl |
| D2 | Audited-execution wrapper | Single decorator/context manager: allocate `TOOL-NNN`, stamp start/end UTC, run backend, write structured+raw output via `safe_write_path`, register derived artifact (B5), append one `tool_calls.jsonl` line. Every tool wraps in this. | `mcp_gateway/audit_exec.py` | A5,B2,B5,C1,C7 | any tool call → exactly one audit line with full provenance + structured_result_path under run dir. | M | keystone of criterion 5 |
| D3 | Backend abstraction (real in-process + gated sift-lane) | `Backend` protocol with `RealBackend` (in-process typed Python lib calls - no subprocess) and `SiftLaneBackend` (gated; fixed-argv `subprocess.run(shell=False)` against allowlisted binaries, no evidence string in argv). Selection via config: `real` (local, default - the demo path) vs `sift_lane` (SIFT host). **No auto-placeholder.** | `mcp_gateway/backends/__init__.py`, `real.py`, `sift_lane.py` | A3,C1 | real backend runs in-process (no subprocess on the local path); sift-lane invokes only allowlisted binaries with fixed argv; switching backend is config-only. | L | all 8 real-buildable now (PLAN/08 §3); sift-lane is optional |
| D4 | Evidence tools (always-real) | `compute_hash_manifest` (wraps B1/B4), `create_readonly_evidence_vault` (wraps B3/B7). Pure-Python, native on Linux (SANS SIFT / Ubuntu). | `mcp_gateway/tools/evidence_tools.py` | B1,B3,B4,D2 | both real on the Linux target (SANS SIFT / Ubuntu); emit provenance; vault tool never writes to source. | M | low - always-real |
| D5 | EVTX tools (real, in-process) | `parse_evtx_security`, `parse_evtx_powershell`. Real backend = **`evtx` (pyevtx-rs)** `PyEvtxParser(...).records_json()` in-process - `evtx==0.11.1` (MIT OR Apache-2.0; installs natively on Linux via manylinux wheel). PowerShell variant filters 4103/4104 / PS-Operational. Output normalized to JSON rows (event_id, ts_utc, source_file, fields). EvtxECmd = optional SiftLane only. | `mcp_gateway/tools/evtx_tools.py` | D2,D3 | real wrapper parses an EVTX fixture in-process on the Linux target (SANS SIFT / Ubuntu); provenance complete. | L | alpha lib → hard-pin `evtx==0.11.1` (PLAN/08 §3) |
| D6 | Prefetch tool (real, in-process) | `analyze_prefetch`. Real backend = **`libscca-python` (pyscca)** `pyscca.file().open(...)` in-process - on Linux installs from wheel or builds from sdist (gcc). Use the library binding; license is not a blocker (replaceable). PECmd = optional SiftLane only. | `mcp_gateway/tools/prefetch_tools.py` | D2,D3 | real wrapper parses a `.pf` fixture in-process; provenance complete. | M | pin to a recent release; license not a concern (PLAN/08 §0.1, §5) |
| D7 | Registry tool (real, in-process) | `extract_registry_run_keys`. Real backend = **regipy** `RegistryHive` + Run/RunOnce extraction - pure-Python, native on Linux (SANS SIFT / Ubuntu), in-process (offline REGF). Pin `regipy==6.2.1`; `regipy[full]` is fine to add if shell-item parsing is wanted (license not a blocker). Extracts Run/RunOnce keys → JSON rows. | `mcp_gateway/tools/registry_tools.py` | D2,D3 | regipy parses a hive fixture on the Linux target; normalized output + provenance. | M | **always-real, pure-Python - prioritize** |
| D8 | Timeline tool | `build_timeline`. Real backend = **own deterministic merge** over the real D5/D6/D7 rows **+ `$MFT` via `mft` (pymft-rs)** `PyMftParser.entries_json()` in-process - pin `mft==0.7.0` (Apache-2.0 own + MIT `mft`). Merges artifact rows into time-ordered JSON timeline. **Plaso/log2timeline (Apache-2.0) = OPTIONAL enrichment** (native on Linux via `uv pip install plaso` / `apt install python3-plaso` / preinstalled on SANS SIFT; subprocess only). MFTECmd = optional SiftLane only. | `mcp_gateway/tools/timeline_tools.py` | D2,D3,D5,D6,D7 | real in-process merge yields an ordered timeline over real D5/D6/D7 + `$MFT` rows; Plaso enrichment runs natively on the Linux target. | L | `mft.entries()` yields inline `RuntimeError` instances → type-check, don't raise (PLAN/08 §3) |
| D9 | Validation tool (differentiator) | `validate_claim_evidence`: always-real pure-Python. Given a Claim, verify `source_artifact` in manifest, `source_sha256` matches, `tool_call_id` exists in `tool_calls.jsonl`. The primitive the Critic consumes. | `mcp_gateway/tools/validation_tools.py` | B4,C2,C7,D2 | claim with bad hash / missing tool_call_id → fails with reason; valid passes. | M | low - high value for criterion 2 |
| D10 | Gateway tests | Allowlist, no-raw-shell, provenance, injection-at-boundary (optional subprocess backends only), in-process-real-backend tests. | `tests/test_mcp_gateway.py` (+ extend `tests/test_path_policy.py`) | D1–D9 | all green on the Ubuntu CI runner (= SANS SIFT target); Windows CI optional/not required. | M | low |

---

## Real backend matrix (all 8 real, buildable now - see [PLAN/08_REAL_TOOL_STACK.md](08_REAL_TOOL_STACK.md) §3)

| Tool | Real backend (in-process) | Pin | License (awareness only - not a blocker) | Native on Linux now? |
|---|---|---|---|---|
| `compute_hash_manifest` | stdlib `hashlib` (own code, wraps B1/B4) | - | Apache-2.0 (own) | **Yes** (always-real) |
| `create_readonly_evidence_vault` | stdlib shutil/pathlib + sha256 (own code, wraps B3/B7) | - | Apache-2.0 (own) | **Yes** (always-real) |
| `parse_evtx_security` | `evtx` (pyevtx-rs) `PyEvtxParser.records_json()` | `evtx==0.11.1` | MIT OR Apache-2.0 | **Yes** (manylinux wheel) |
| `parse_evtx_powershell` | `evtx` (same lib; filter 4103/4104 / PS-Operational) | `evtx==0.11.1` | MIT OR Apache-2.0 | **Yes** (same backend) |
| `analyze_prefetch` | `libscca-python` (pyscca) `pyscca.file().open(...)` | `libscca-python` (recent) | LGPL (lib) - replaceable | **Yes** (wheel, or sdist+gcc) |
| `extract_registry_run_keys` | `regipy` `RegistryHive` + Run/RunOnce | `regipy==6.2.1` (`[full]` fine if shell-items wanted) | MIT | **Yes** (offline REGF, OS-independent) |
| `build_timeline` | own merge over real rows + `$MFT` via `mft` (pymft-rs) | `mft==0.7.0` | Apache-2.0 (own) + MIT (`mft`) | **Yes** (in-process; Plaso enrichment native on Linux) |
| `validate_claim_evidence` | own pure-Python verifier (manifest + sha256 + tool_call_id) | - | Apache-2.0 (own) | **Yes** (always-real; the Critic differentiator) |

**Optional / gated on real evidence (validate on the maintainer's box):** **Plaso/log2timeline** super-timeline *enrichment* (native on Linux - `uv pip install plaso` / `apt install python3-plaso` / preinstalled on SANS SIFT; subprocess only); the optional **SIFT-lane CLIs** (EvtxECmd / PECmd / MFTECmd / Volatility 3); and **real demo evidence** (maintainer provides the real SANS SIFT artifacts - do not fabricate). The only real gate is real evidence, not tool buildability. See PLAN/08 §0.1, §4.

**Result:** the demo shows **eight genuinely-real tools** running on real artifacts - directly answering "is this real?" for judges - with the audit trail never labeling anything a placeholder. The local real path is fully **in-process** (zero subprocess/shell), which strengthens criterion 4; only Plaso enrichment and real-evidence integration are gated.

**MVP coverage vs. known gaps (honest scope):** in-process MVP = **EVTX (Security + PowerShell) / Prefetch / Registry Run-RunOnce / `$MFT`**; documented gaps = **Amcache, SRUDB, ShimCache/AppCompatCache, full Plaso super-timeline, memory (Volatility 3)** - reachable on the SANS host via the SIFT-lane (PLAN/08 "MVP coverage vs gaps"; PLAN/09 §3–§4). State the gaps in the dataset + accuracy docs; do not overclaim breadth.

---

## Mandatory provenance fields (every tool output)

```json
{
  "tool_call_id": "TOOL-007",
  "source_artifact": "evidence/windows/Security.evtx",
  "source_sha256": "…",
  "start_time_utc": "2026-06-09T14:03:01Z",
  "end_time_utc":   "2026-06-09T14:03:04Z",
  "status": "ok",                 // ok | error
  "structured_result_path": "results/TOOL-007.structured.json",
  "raw_output_path": "results/TOOL-007.raw.txt",   // if any
  "error_code": null,
  "backend": "real",              // real | sift_lane  ← never forged
  "tool_version": "regipy==6.2.1"
}
```

---

## Key design decisions & trade-offs (D)

- **All eight tools are genuinely real** (in-process typed Python lib calls - see [PLAN/08_REAL_TOOL_STACK.md](08_REAL_TOOL_STACK.md) §3): the demo shows real forensic computation on real artifacts, with no placeholder/mock/synthetic backend anywhere. Because the local real path is fully in-process (zero subprocess/shell), it **strengthens criterion 4** while preserving audit honesty (criteria 2+5). This is a differentiator, not a weakness.
- **No-raw-shell + injection defense at the boundary** via fixed binary allowlist, fixed argv, `shell=False`, zero evidence-string interpolation - one rule satisfies criterion 4 and the tool-boundary injection requirement.
- **License is not a runtime blocker; code-reuse rule still holds:** runtime dependencies on tools under any license are fine (replaceable backends - PLAN/08 §0.1, §5). The remaining rule is a *code-reuse* one: do **not copy source** from restrictive projects (e.g., Hayabusa/Chainsaw); only Sigma rules (DRL, reusable data) are consumed later. The **project itself stays Apache-2.0** (hackathon submission requirement: public repo under MIT/Apache-2.0).
- **SIFT lane is a third backend, not a fork:** `backends/sift_lane.py` per tool orchestrates the real SIFT/Protocol-SIFT tools on the SANS host behind the identical typed interface (roadmap R2).
- **Pragmatic 11-day cut:** all eight tools are real and buildable now - prioritize D1–D4, D7, D9 (always-real / pure-Python), then D5/D6/D8 (real in-process via `evtx`/`pyscca`/`mft`). Gate only the **Plaso super-timeline enrichment** and **real-evidence integration** (validate on the maintainer's box - do not fabricate). If behind on Day 4, trim to **4 core tools** (hash, vault, registry-real, validate) - still a complete, auditable, evidence-safe gateway - but D5/D6/D8 remain real (not mocked) when included.

---

## Tests to add (D)

- `test_forbidden_tool_not_exposed` - tool list excludes all forbidden names (`execute_shell_command`, `arbitrary_python`, `rm`, `dd_write`, `mount_rw`, `curl_arbitrary`, `scp_arbitrary`); registry rejects registering a forbidden name.
- `test_tool_call_logged_with_provenance` - every call appends one `tool_calls.jsonl` line with all provenance fields populated.
- `test_real_backend_is_in_process` - the local real backends (`evtx`/`pyscca`/`regipy`/`mft` + stdlib) run without spawning any subprocess (no shell surface on the demo path).
- `test_no_evidence_string_in_argv` / injection-at-boundary - for the **gated subprocess backends only** (sift-lane CLIs / Plaso/Docker), a crafted evidence path/field cannot inject into the command (fixed argv asserted). Not applicable to the in-process real path (no command string exists).
- `test_validate_claim_evidence_rejects_bad_hash` - claim with mismatched `source_sha256` or missing `tool_call_id` fails validation.
- `test_tool_writes_only_under_run_dir` - every tool's structured/raw output lands under the run dir (path policy enforced).

---

## Forward consumers

- The Executor adapters (Epic F) call these tools when running a task and rely on `tool_calls.jsonl` provenance.
- The Critic (Epic G) calls `validate_claim_evidence` (D9) as the structural backbone of claim validation.
- The Reports (Epic J) read `tool_calls.jsonl` to build the tool-execution appendix and the replay timeline.

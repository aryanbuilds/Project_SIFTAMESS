# PLAN 08 — Confirmed REAL Tool Stack (real-only, Linux-first)

_Authored 2026-06-04. **This file is authoritative for the real-only delivery rule** (CLAUDE.md §2B, AGENT.md rules 6–7, GUIDELINES.md §7a). It supersedes every "placeholder / mock / synthetic" strategy in PLAN/00–07. Tool facts were confirmed via deepwiki + Tavily + WebFetch of primary sources and adversarially verified. Re-confirm version pins + the exact MCP `FastMCP` import surface against the pinned versions at implementation time (context7/deepwiki)._

## 0. The rule this file enforces

SIFTMesh ships **real, working forensic tools** — no mock tools, no placeholder backends, no synthetic/seeded "fake-real" outputs. Judges and the maintainer see real tools running on real artifacts. The "deterministic placeholder backend / mock executor / synthetic demo evidence" strategy from the original plan is **rejected**.

## 0.1 Platform & license posture (read first)

- **Linux-first.** The **development AND target platform is Linux (SANS SIFT / Ubuntu)** — *not* Windows. The plan is authored on Windows, but no code is built or run here; all development, tool installation, and execution happen on Linux. Windows is **not** a constraint. Earlier "buildable-on-Windows / dual-OS / WSL2 / pywin32 / MSVC-wheel" framing is **superseded** — on Linux every backend below installs natively (pip wheels or sdist+gcc; several are preinstalled on SANS SIFT). Keep `pathlib` discipline as good hygiene, but Linux is primary; CI primary runner = Ubuntu.
- **License is not a blocker.** Tool/connector licenses (LGPL `libscca`, VSL Volatility 3, `regipy[full]`, libyal/TSK in Plaso's tree, etc.) are **not a gating concern — these components are replaceable.** Use whatever real backend works best; swap if a license ever matters. The **project itself stays Apache-2.0** (a hackathon submission requirement: public repo under MIT/Apache-2.0) — that is the only license constraint that remains.

## 1. The biggest correction: the local real path is IN-PROCESS, not subprocess

The original PLAN/03 framing — *"real wrappers invoke a fixed allowlist of binaries with fixed argv via `subprocess.run([...], shell=False)`"* — is **wrong for 7 of the 8 MVP tools**. The real MVP is **100% in-process typed Python library calls** (hashlib/stdlib + `evtx` + `regipy` + `pyscca` + `mft`): **zero subprocess, zero shell surface**. There is literally no command string to inject into — this **strengthens criterion 4 (constraints)**, it does not complicate it.

Fixed-argv `subprocess.run(shell=False)` is reserved **only** for the optional/gated backends — Plaso and the SIFT-lane CLIs (EvtxECmd / PECmd / MFTECmd / Volatility 3) — where a subprocess boundary is simply the natural way to drive an external binary.

## 2. MCP gateway — CONFIRMED

| Item | Confirmed value |
|---|---|
| Package | **`mcp`** (official `modelcontextprotocol/python-sdk`), MIT. NOT the standalone `fastmcp` package. |
| Pin | `mcp>=1.27,<2` (latest 1.27.2, 2026-05-29); `requires-python >=3.10` |
| Server | `from mcp.server.fastmcp import FastMCP; mcp = FastMCP("siftmesh"); … ; mcp.run(transport="stdio")` |
| Tool | `@mcp.tool()` over Pydantic-args / dict-or-Pydantic-return, wrapped in the D2 audited-execution context manager (TOOL-NNN, UTC stamps, `safe_write_path`, derived-artifact registry, one `tool_calls.jsonl` line, `backend="real"|"sift_lane"`). |
| Transport | stdio (local, sandboxable; the agent→tool boundary; run as fixed-argv subprocess `["python","-m","siftmesh_mcp_server"]`, shell=False) |
| Note | `mcp` core is pure Python; installs cleanly on Linux. |

The PLAN/03 design (FastMCP stdio server + allowlist-only registry + typed tools) is **confirmed** — only the "all backends are subprocess" framing changes (see §1).

## 3. Real-tool matrix — all 8 real and native on Linux (SANS SIFT / Ubuntu)

| SIFTMesh tool | Real backend (in-process) | Pin | Notes |
|---|---|---|---|
| `compute_hash_manifest` | Python **stdlib `hashlib`** (own code, wraps B1/B4) | — | Always-real, pure Python |
| `create_readonly_evidence_vault` | Python **stdlib** (shutil/pathlib + sha256, own code, wraps B3/B7) | — | Never writes to source; hash before analysis |
| `parse_evtx_security` | **`evtx`** (pyevtx-rs) `PyEvtxParser(...).records_json()` | `evtx==0.11.1` | Real EVTX parsing; manylinux wheels. Alpha → hard-pin |
| `parse_evtx_powershell` | **`evtx`** (same lib; filter 4103/4104 / PS-Operational) | `evtx==0.11.1` | Same backend, different channel/ID normalization |
| `analyze_prefetch` | **`libscca-python`** (pyscca) `pyscca.file().open(...)` | `libscca-python` (recent) | Real Prefetch parsing; on Linux installs from wheel or builds from sdist (gcc). Use the library binding; license not a concern |
| `extract_registry_run_keys` | **`regipy`** `RegistryHive` + Run/RunOnce extraction | `regipy==6.2.1` | Pure-Python, offline REGF; `regipy[full]` is fine to add if shell-item parsing is wanted. Plan said "regipy 4.x" → corrected to 6.2.1 |
| `build_timeline` | Deterministic **own-code merge** over real `evtx`/`pyscca`/`regipy` rows + `$MFT` via **`mft`** (pymft-rs) `PyMftParser.entries_json()`; **Plaso** optional enrichment (native on Linux) | `mft==0.7.0` | `mft.entries()` yields `RuntimeError` instances inline → type-check, don't raise |
| `validate_claim_evidence` | **Own pure-Python verifier** (manifest membership + sha256 match + tool_call_id in `tool_calls.jsonl`) | — | Always-real; the differentiator the Critic (Epic G) consumes |

**The demo shows EIGHT genuinely-real tools** — directly answering "is this real?" for judges, with the audit trail never labeling anything a placeholder.

## 4. Optional enrichment & the real-evidence gate

| Item | Status on Linux | Notes |
|---|---|---|
| **Plaso / log2timeline** super-timeline (optional, on top of the in-process merge) | **Native on Linux** — `pip install plaso`, `apt install python3-plaso`, or preinstalled on SANS SIFT. Not build-gated. | Drive via `log2timeline.py` / `psteal.py` / `psort.py` (subprocess, shell=False) or Docker. Apache-2.0 |
| **SIFT-lane CLIs** EvtxECmd / PECmd / MFTECmd / Volatility 3 | Optional alternates to the in-process libs (.NET runs on Linux; Volatility 3 is pure-Python) | Optional `SiftLaneBackend` behind the **same typed interface**; fixed-argv `subprocess.run(shell=False)`. Not the demo path |
| **Real demo evidence (K1)** + integration/e2e (K3, K6, M3, M5) | **Gated on the maintainer providing real files** | The tools build/run on the Linux dev box; producing/validating a real timeline needs real artifacts (EVTX / prefetch / registry hive / `$MFT`). **STOP and ask the maintainer for the real SANS SIFT workstation + real files — do not fabricate.** |

**The only real gate is real evidence** (not tool buildability) — every backend above installs on Linux now.

## 5. License posture (not a blocker)

Tool/connector licenses are **not a gating concern — components are replaceable.** Use the best real backend; swap later if any license ever matters. Notes for awareness only (no action required): `libscca-python` is LGPL, Volatility 3 is VSL, Plaso's dep tree includes libyal/TSK. The **project itself remains Apache-2.0** (hackathon submission requirement) — keep `LICENSE` Apache-2.0 and avoid *copying source* from restrictive projects, but depending on them at runtime is fine.

## 6. Self-correction (hero / tiebreaker) — real, deterministic, no scripted verbs

The mock scenario verbs (`emit_claim_missing_field`, `emit_malformed_json`, `emit_corrected_claim`, `emit_contradicting_claim`, `emit_valid`, `tool_failure`) are **deleted**. The hero is now a **deterministic engine over real tool output**:

1. The first-pass task contract is **genuinely under-specified** (its `success_criteria` does not yet require binding `source_sha256` + `tool_call_id`).
2. The real in-process tool runs over the real (committed) evidence and emits a **real claim** that genuinely lacks the required evidence binding.
3. The deterministic Critic structural check (Layer 1) genuinely returns `retry_required`.
4. DECIDE (pure fn) → retry with a **tightened** contract (`claim MUST include tool_call_id + source_sha256`).
5. The **second real attempt** over the same real tools now passes → promoted to `claim_ledger.jsonl` (confirmed).

Determinism survives because it comes from **real tools over fixed committed evidence with no LLM and no randomness** — reproducible ≥10/10. Integration-gated on K1 real evidence; the in-process tools are testable on the Linux dev box against any small committed real artifact.

## 7. a2a-sdk (Epic P, optional/stretch) — CONFIRMED

`a2a-sdk` (PyPI; published by `a2aproject`, Apache-2.0, pure-Python wheel, `requires-python >=3.10`, pin `1.1.0`). Agent Card at `/.well-known/agent-card.json`. **Do NOT** pin the look-alike third-party `python-a2a` (different maintainer). Backs the optional A2A boundary only — governed by the `x_siftmesh` policy overlay (remote agents untrusted by default).

---

_Provenance: confirmed by workflow `wf_d174de6b-b23` (17 agents: 8 research → 8 adversarial-verify → 1 synthesis; deepwiki + Tavily + primary-source WebFetch). Platform: Linux-first (SANS SIFT / Ubuntu) for dev + target; Windows is not a constraint. Tool/connector licenses are not a blocker (replaceable); project stays Apache-2.0. Pins (reproducibility, not platform): `evtx==0.11.1`, `mft==0.7.0`, `regipy==6.2.1`, `mcp>=1.27,<2` (libscca: a recent release)._

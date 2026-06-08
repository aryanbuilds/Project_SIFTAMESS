# SIFTMesh — Project state through Epic D

**Status:** Epics **A, B, C, D complete** (Epic D node closed). Next: **Epic E (Planner & Deep
Context Agent)** — unblocked, not started.
**Branch:** `mvp_phase_1` · **Epic D closed at commit** `db84669` · **Tests:** 203 passing
(ruff + ruff-format + mypy clean) · **`siftmesh doctor`:** ok (10-tool allowlist, no forbidden).

This document summarizes everything built so far, the APIs/features available, the real-evidence
validation performed, and the key decisions/findings from the work sessions that produced it.

---

## 1. What SIFTMesh is

A **CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR** on SANS SIFT
/ Protocol SIFT. The governing principle is **"LLM proposes, code decides"**: autonomy lives in the
agent; determinism lives in the governance (typed tools, claim ledger, deterministic critic, caps,
evidence-safety, replayable audit). It is **not** a generic multi-agent chatbot — it's a
forensic-safe investigation controller.

**Non-negotiable boundaries:** CLI = source of truth · MCP = typed forensic tool boundary · Evidence
vault = integrity boundary · Critic = claim-validation boundary · A2A (later) = agent-to-agent
interop. External orchestrators never decide forensic truth, report content, or evidence policy.

**Hard rules in force on every change:** REAL-ONLY (no mocks/placeholders; missing backend fails
closed, never fakes — pure unit tests may use fixtures/golden JSON); all state under
`case_runs/RUN-*`; never modify/commit original evidence; no raw-shell/destructive tools; treat case
data as hostile; Linux-first; **commits carry no AI co-author trailer**; `uv` for all env/run; **bd
(beads)** is the single source of task truth; **strictly sequential epics** (only a human closes an
epic node).

---

## 2. Architecture (as built)

```
siftmesh_core/
  cli.py            Typer CLI (the source-of-truth surface)
  config.py         SiftmeshSettings (env > toml > defaults); caps; backend_mode; tool paths
  doctor.py         host/dep/safety verification — fails closed on missing core dep
  run_dir.py        RUN-* directory contract (CLAUDE.md §5)
  logging.py        structlog setup
  protocol_sift.py  inspect+govern the ~/.claude Protocol SIFT layer (D11)
  evidence/         hash_utils, manifest, vault(init-case), readonly, derived, custody, path_policy,
                    image_access (Sleuthkit), memory_access (zip→7z→image)
  ledgers/          jsonl_ledger (validate-before-write), tool_call_ledger, custody_ledger, claim_ledger
  schemas/          Pydantic v2 typed contracts (StrictModel; the claim firewall; capability map; …)
  mcp_gateway/      registry (allowlist) · server (FastMCP stdio) · audit_exec (provenance keystone)
                    · backends/{real, sift_lane} · tools/*.py (the 10 typed tools)
```

**Layering:** CLI and the FastMCP server both call the **same typed service functions** (CLI-first).
Each tool runs through `audit_exec.run_tool`, which is the provenance keystone. Each parser tool
delegates to a swappable **Backend** (`real` in-process libs, or `sift_lane` host CLIs) — a config flip.

---

## 3. Epic status (the sequential spine)

`A → B → C → D → E → F → G → H → K → J → L → M → N → I → P → O`

| Epic | Title | Status |
|------|-------|--------|
| A | CLI skeleton, run dir, config, doctor, logging | ✅ done |
| B | Evidence vault: streaming SHA-256, manifest, custody, path policy, read-only posture | ✅ done |
| C | Schemas & ledgers: ToolResult, Claim firewall, task/agent/workflow, JSONL ledgers | ✅ done |
| **D** | **Typed MCP tool gateway (10 tools, backends, audit, EZ-Tools, memory)** | ✅ **done (closed)** |
| E | Planner & Deep Context Agent (brief → context pack → plan) | ⬜ next (unblocked) |
| F–O | Dispatch, Critic, `run` automation, agents, reports, security, CI, docs, A2A, TUI | ⬜ pending |
| D-H | Evidence-handling hardening (backlog, off-spine) — `Project_SIFTAMESS-b2m` | ⬜ backlog |

bd snapshot: 213 issues, 108 closed.

---

## 4. The 10 typed forensic tools (Epic D — the agent/CLI-facing surface)

All registered on a FastMCP stdio server; allowlist-enforced; each returns a `ToolResult` subclass
and is audited (one `audit/tool_calls.jsonl` line + custody + derived-artifact records).

| Tool | Purpose | Backend(s) |
|------|---------|-----------|
| `compute_hash_manifest` | SHA-256 every file under evidence root | own (stdlib) |
| `create_readonly_evidence_vault` | record read-only posture | own (stdlib) |
| `parse_evtx_security` | Security.evtx records | real `evtx` / sift_lane `EvtxECmd` |
| `parse_evtx_powershell` | PowerShell-Operational 4103/4104 | real `evtx` / sift_lane `EvtxECmd` |
| `analyze_prefetch` | `.pf` execution evidence | real `pyscca` (sift_lane: fails closed — PECmd absent) |
| `extract_registry_run_keys` | Run/RunOnce autostart | real `regipy` / sift_lane `RECmd` |
| `build_timeline` | merge evtx+prefetch+`$MFT` → ordered timeline | real (own merge; `mft`) |
| `validate_claim_evidence` | verify a claim's evidence anchor (Critic primitive) | own (pure-Python) |
| `extract_artifacts_from_image` | carve Windows artifacts from an `.E01`/raw image | sift_lane (Sleuthkit `mmls`/`ifind`/`icat`/`fls`) |
| `analyze_memory` | Volatility 3 triage (pslist/pstree/netscan/cmdline/malfind) | sift_lane (vol subprocess) |

The first 8 are the CLAUDE.md §7 set; the last 2 are a **governed allowlist expansion (8→10)** added
for real disk-image + memory evidence.

**Forbidden, never registerable:** `execute_shell_command`, `arbitrary_python`, `rm`, `dd_write`,
`mount_rw`, `curl_arbitrary`, `scp_arbitrary`.

---

## 5. Backends

- **`real` (in-process, default, demo path):** `evtx`/`regipy`/`pyscca`/`mft` + stdlib. **Zero
  subprocess** (enforced by `test_real_backend_is_in_process`) — strengthens the no-raw-shell story.
- **`sift_lane` (host CLIs, D12):** drives **EZ Tools** via fixed-argv `dotnet <Tool>.dll`
  (`EvtxECmd`, `MFTECmd`, `RECmd`), normalized to the *exact same row shapes* as `real`. Config flip
  `real ↔ sift_lane` via `SIFTMESH_BACKEND_MODE` / `config.backend_mode`; provenance records
  `backend="sift_lane"`. RECmd uses `--nl true` for dirty hives. **PECmd absent → prefetch fails
  closed.** Missing tool / non-zero exit → fails closed (`BackendUnavailableError` / error status).
- **Evidence-access (image + memory):** `evidence/image_access.py` (Sleuthkit, fixed-argv, per-file
  fault-tolerant — a corrupt artifact is recorded, never aborts) and `evidence/memory_access.py`
  (zip → `7z` → memory image, magic-based format detect). `analyze_memory` uses a writable
  `--symbol-dirs` cache because vol's install dir is read-only.

---

## 6. CLI surface (`siftmesh …`)

Real today: `init-case` (hash+seal evidence → run dir), `doctor [--protocol-sift]`, `mcp-serve`
(FastMCP stdio gateway), `extract-artifacts`, `analyze-memory`, `protocol-sift inspect [--run-dir]`,
`protocol-sift skills list`. Stubs (wired in later epics): `plan`, `dispatch`, `collect`, `critique`,
`report`, `replay`, `run`, `resume`, `status`, `retry`, `approve`, `reject`, `tasks/claims/audit …`.

**Gap (next epic):** there is **no brief/prompt intake → autonomous investigation** yet (`run` is a
stub). Ingesting a case brief (ppt/docx/md/txt) → `context_pack` + `investigation_plan` is **Epic E**;
dispatch/critic/orchestration are F/G/H.

---

## 7. Run-directory contract (`case_runs/RUN-*`)

Created by `run_dir.new_run_dir()` (7 subdirs). Populated by what's built; the rest is scaffolded for
later epics:

| Dir | Populated by | Status |
|-----|--------------|--------|
| `evidence/` (manifest, hashes.sha256, custody_log, derived_artifacts, readonly_mounts, extracted/) | B + D | ✅ |
| `results/` (`TOOL-NNN.structured.json` + `.raw.json`) | D | ✅ |
| `audit/` (tool_calls.jsonl, orchestration_events.jsonl) | B + D | ✅ |
| `context/` (evidence_policy.md, protocol_sift_capabilities.json) | B + D11 | ✅ partial |
| `reports/` | (driver findings now; Epic J owns `final_report.md`) | partial |
| `tasks/` | Epic F | ⬜ |
| `claims/` | Epic G | ⬜ |

---

## 8. Schemas & ledgers (Epic C + D additions)

- **`ToolResult`** — the provenance base every tool output carries (`tool_call_id`, `source_artifact`,
  `source_sha256`, UTC start/end, `status`, `backend`, `tool_version`, `structured_result_path`,
  `raw_output_path`, `error_code`).
- **`Claim`** — the **hallucination firewall**: confirmed/inferred/contradicted claims require
  `source_artifact`+`source_sha256`+`tool_name`+`tool_call_id` (except `unsupported`).
  `validate_claim_evidence` is a non-raising grader the Critic (Epic G) will consume.
- **`TaskContract`, `AgentProfile`, `Workflow`, `RunState`, `CustodyEvent`, `EvidenceManifest`,
  `ProtocolSiftCapabilityMap`** (D11).
- **Ledgers:** generic `jsonl_ledger` (validate-before-write; corrupt line → `LedgerCorruptionError`,
  never silent skip); `tool_call_ledger`; `custody_ledger`; `claim_ledger`.

---

## 9. Safety invariants enforced (criteria 4 & 5)

- **Allowlist:** exactly the 10 tools register; forbidden names can never register (`registry.py`).
- **No raw shell:** in-process real path has no command string; sift_lane/image/memory use fixed-argv
  `shell=False` with **no evidence string interpolated**; evidence paths validated by
  `resolved_source` (inside the evidence root, no traversal) before any subprocess.
- **Provenance:** every tool call → one `tool_calls.jsonl` line + custody + derived records, on
  success **and** error (criterion 5).
- **Path policy:** every write routes through `safe_write_path` (run dir only; rejects traversal /
  symlink-escape / evidence-tree writes).
- **Fail closed:** missing backend/tool → `BackendUnavailableError` (recorded, never faked).
- **Volatility 3 (VSL) never imported** — subprocess-only, enforced by `test_no_volatility_import.py`.
- **No SANS evidence in repo or CI;** heavy real runs are human-gated.

---

## 10. Real-evidence validation (the ROCBA SANS case — human-authorized, local only)

The maintainer provided the real ROCBA evidence (23 GB `rocba-cdrive.e01`, 5.3 GB `Rocba-Memory.zip`,
a PPTX brief). The full chain was run **through `siftmesh_core`'s own gateway** (208 audited tool
calls), in a run dir **outside the repo** (never committed/CI):

- **218 artifacts** carved from the E01 (PowerShell/System evtx, SOFTWARE/SYSTEM hives, 211 prefetch,
  per-user `NTUSER.DAT` for users `fredr`/`srl-h`, the 469 MB `$MFT`).
- **Real autostart persistence** (OneDrive/Teams/GoogleDrive/Edge; SecurityHealth).
- **479,383-event timeline** (evtx + prefetch + `$MFT`).
- **Memory triage:** Windows 10 build 19041; **2,186 processes, 16 malfind hits, 211 external
  connections** (incl. RDP 3389 to external IPs).
- **Honest fail-closed findings:** `Security.evtx` is **corrupt in the image** (NTFS LZNT1 unit 284 —
  libtsk, ntfs-3g, and libfsntfs all fail identically) → recorded as a failure, run continues; vol
  needed a writable `--symbol-dirs` (the only real fix). The audit ledger even records the failed
  memory attempt and the successful retry — full traceability.
- **D12 parity proof:** EvtxECmd `System.evtx` 2512 rows == in-process 2512; RECmd finds
  `SecurityHealth`; config flip audited as `backend="sift_lane"`.

---

## 11. Key decisions & findings from the work sessions

- **Epic D deepening (governed 8→10):** the original 8 tools only parsed *loose* artifacts; real
  evidence is an image → added an **evidence-access layer** (Sleuthkit) + **memory triage**
  (Volatility3 subprocess), folded into Epic D with maintainer approval.
- **E01 access = host CLIs via `sift_lane`** (chosen over in-process dfvfs/pytsk3): TSK reads `.E01`
  directly, zero new venv deps, license-clean. ROCBA is a **single-volume NTFS** image (no partition
  table → offset 0).
- **NTFS-compressed evtx corruption** is an evidence property, not a tool bug (3 independent NTFS
  libraries agree) → per-file fault tolerance.
- **Protocol SIFT skill layer is not installed** on this box (`~/.claude` is plain Claude Code) —
  `protocol-sift inspect` reports it honestly while detecting the underlying tools; fixed stale tool
  paths (`vol` at `/opt/volatility3/bin/vol`).
- **EZ Tools** are MIT; invoked as external `dotnet` subprocess; canonical NOTICE/SBOM is Epic N6.
- **P2 hardening** (per-access re-hash, stream-parse, OS RO-mount, resumable ingest) moved to backlog
  epic `b2m` so Epic D could close cleanly.

---

## 12. Testing & how to run

```bash
uv sync --extra sift                              # install forensic backends (evtx/regipy/pyscca/mft)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest   # all green (203)
uv run siftmesh doctor                            # host + backend verification
uv run siftmesh doctor --protocol-sift            # also detect the ~/.claude layer
uv run siftmesh mcp-serve                          # FastMCP stdio gateway (10 tools)
```
- **203 tests**, Ubuntu-CI-safe: all subprocess is mocked; golden JSON fixtures; tiny **real**
  upstream parser fixtures in `tests/fixtures/forensic/`; **no SANS evidence in CI**.
- Real EZ-Tools / image / memory validation is **human-gated** on the SIFT box.

## 13. What is NOT done yet (post-Epic-D)
- **Epic E** — Planner & Deep Context Agent: brief/prompt intake → `context/context_pack.md` +
  `investigation_plan.yaml` (the autonomous front door). **Unblocked, not started.**
- **F/G/H** — executor dispatch, deterministic Critic + self-correction loop, `run --auto-human-loop`.
- **I/J/L/M/N/P/O** — live agents, reports/replay, threat model, CI, docs/submission, A2A, TUI.
- **D-H backlog** (`b2m`): per-access re-hash, stream-parse, OS read-only mount, resumable ingest.

## 14. Reference (env + memories)
- **Env:** SANS SIFT (Ubuntu 6.8); Sleuthkit 4.11.1 (libewf), `vol` `/opt/volatility3/bin/vol`,
  Plaso, EZ Tools `/opt/zimmermantools` + `dotnet 9.0.117`, 7-Zip 23.01. `yara`/`weasyprint` absent.
- **bd memories** capture the non-obvious specifics (`bd memories <kw>`): `siftmesh-epic-d-apis`,
  `siftmesh-epic-d-fixtures`, `siftmesh-epic-d-evidence-access`, `siftmesh-epic-d-memory-vol`,
  `siftmesh-epic-d-d11-d12`, `siftmesh-protocol-sift-integration`, `siftmesh-real-only-tool-stack-…`,
  `git-no-coauthor`, `siftmesh-uv-tooling`, and the Epic B/C summaries.

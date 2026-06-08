# PLAN/10 — Evidence-Access Layer (Epic D deepening)

Status: implemented (DA1–DA6); real-evidence validation (DA7) human-gated. Epic D node
`Project_SIFTAMESS-5ds` stays **OPEN** (only the maintainer closes an epic node).

## Why

The original Epic D delivered 8 typed tools that each parse **one loose Windows artifact**
(`.evtx` / `.pf` / `NTUSER.DAT` / `$MFT`) resolved relative to `evidence_root`. Real evidence
(the ROCBA SANS case) is a **23 GB `.E01` disk image** + a **5.3 GB memory capture**, which no
existing tool could touch. This layer bridges image → loose artifacts → analysis, and adds memory
triage, so the gateway runs end-to-end on real evidence — without weakening any safety invariant.

Maintainer decisions (2026-06-08): host-CLI extraction via the `sift_lane` lane; focused memory
triage via Volatility 3; folded into Epic D with a **governed allowlist expansion 8 → 10**; copy
the data and run the full chain.

## Architecture

```
ORIGINALS (local copy)        RUN DIR
  rocba-cdrive.e01  ── init-case hash ─▶ evidence/{manifest,custody,...}
  Rocba-Memory.zip                       evidence/extracted/   ◀── derived artifacts (hashed)
                                         results/TOOL-NNN.structured.json (+ .raw.json)
                                         audit/tool_calls.jsonl  (1 provenance line / tool call)

  extract_artifacts_from_image  (sift_lane: mmls → ifind → icat / fls on the .E01) ─▶ extracted/*
  existing in-process parsers   (parse_evtx_*, analyze_prefetch, extract_registry_run_keys,
                                 build_timeline) run with evidence_root = run/evidence/extracted
  analyze_memory                (sift_lane: 7z decompress → vol -r json triage)
```

The extracted loose files live under the run dir, so the existing parsers run **unchanged** — no
modification to `resolved_source` or `path_policy` was needed. The two new tools are the
**`sift_lane` lane** (provenance `backend="sift_lane"`); they call internal helpers, not the
4-method real `Backend` protocol.

### Components added
- `siftmesh_core/evidence/image_access.py` — Sleuthkit primitives (`list_partitions`/`resolve_offset`/
  `find_inode`/`list_dir`/`extract_inode`) and `extract_artifacts()` over a curated `ARTIFACT_MAP`
  (Security/PowerShell-Operational/System evtx, SOFTWARE/SYSTEM hives, per-user `NTUSER.DAT`,
  `Prefetch/*.pf`, `$MFT`). Fixed-argv, `shell=False`. A single-volume image (no partition table,
  as in ROCBA) resolves to offset 0.
- `siftmesh_core/evidence/memory_access.py` — `decompress()` (stdlib unzip + fixed-argv `7z x`),
  magic-based `detect_format()`, intermediate `.7z` cleanup, zip-slip guard.
- `siftmesh_core/mcp_gateway/tools/image_tools.py` — `extract_artifacts_from_image` →
  `ImageExtractionResult`; registers each extracted file as a `DerivedArtifact` (image → file chain
  with `extraction_source_path`/`extraction_inode`/`extraction_method`).
- `siftmesh_core/mcp_gateway/tools/memory_tools.py` — `analyze_memory` → `MemoryAnalysisResult`
  (pslist/pstree/netscan/cmdline/malfind, JSON-normalised); raw `vol` JSON preserved as
  `raw_output_path`.
- `audit_exec.run_tool` — optional raw-output capture (`results/TOOL-NNN.<suffix>` +
  `raw_output_path`); both structured and raw outputs registered as derived artifacts.
- `DerivedArtifact` — optional extraction-provenance fields (backward-compatible, defaulting None).
- `registry`/`server`/`doctor`/`config` + CLAUDE.md §7 reflect the **10-tool** surface; `doctor`
  adds WARN-level checks for `mmls`/`fls`/`icat`/`ifind`, `7z`, and `vol`.

## Invariants (unchanged)
- **REAL-ONLY / fail-closed:** real Sleuthkit + Volatility output only; a missing host CLI raises
  `BackendUnavailableError` (recorded as `status=error`, never faked).
- **No raw shell (criterion 4):** every subprocess is a fixed argv with `shell=False`; the only
  variable elements are the validated image path, a numeric offset, and a TSK metadata address.
- **Provenance (criterion 5):** every call appends one `tool_calls.jsonl` line; extraction chains
  image → derived file with hashes + inode; memory preserves raw `vol` JSON.
- **Path policy:** all writes via `safe_write_path` (run dir only); originals never modified.
- **No evidence in repo/CI:** real runs are local + human-gated; unit tests mock all subprocess.
- **Volatility 3 never imported** (VSL): subprocess-only, enforced by `tests/test_no_volatility_import.py`.

## License posture (runtime tools; canonical NOTICE/SBOM = Epic N6)
| Tool | Use | License | Note |
|------|-----|---------|------|
| The Sleuth Kit (`mmls`/`ifind`/`icat`/`fls`) | extraction | IBM CPL / Apache-2.0 / GPL (mixed) | external CLI only; not linked/imported |
| libewf (via TSK) | EWF read | LGPL-3+ | external; not a project dependency |
| 7-Zip / p7zip (`7z`) | memory decompress | LGPL | external CLI only |
| Volatility 3 (`vol`) | memory triage | **VSL v1.0** | **external subprocess only; never imported** |
| EZ Tools (`EvtxECmd`/`MFTECmd`/`RECmd`) | SIFT-lane (D12) | MIT (EricZimmerman) | external `dotnet <dll>` subprocess only |
| .NET runtime (`dotnet`) | EZ Tools runtime | MIT | external; host runtime |
| evtx / regipy / pyscca / mft | in-process parsers | MIT/GPL/LGPL/Apache | existing `sift` extra |

Project license stays **Apache-2.0**; no restrictive source is copied. None of the above are added
to `pyproject.toml` (they are host runtime tools, discovered via PATH / `config.vol_path` /
`config.ez_tools_dir`).

## D11/D12 done (2026-06-08)
- **D11** — `protocol-sift inspect [--run-dir]` writes a typed `ProtocolSiftCapabilityMap` to
  `context/protocol_sift_capabilities.json`; multi-candidate tool detection fixed PLAN/09's stale
  paths (vol `/opt/volatility3/bin/vol`; `yara` honestly absent). The Protocol SIFT *skill layer*
  is not installed on this host and is reported absent while the underlying tools are present.
- **D12** — `SiftLaneBackend` drives EZ Tools (`dotnet <dll>`, fixed-argv) and normalizes to the
  exact `RealBackend` row shapes; **config flip** `real ↔ sift_lane` via `SIFTMESH_BACKEND_MODE`.
  RECmd needs `--nl true` for dirty hives; **PECmd is absent → prefetch fails closed**. Validated on
  the real ROCBA artifacts (EvtxECmd 2512 == in-process 2512; RECmd finds `SecurityHealth`).
- **P2 hardening** (per-access re-hash, stream-parse, OS RO-mount, resumable ingest) moved to the
  backlog epic `Project_SIFTAMESS-b2m` (not on the must-have spine) so Epic D could close.

## Deferred (new bd issues under Epic D `5ds`, not this pass)
- Plaso super-timeline (`log2timeline`/`psort`) as an optional heavyweight enrichment lane.
- Pure in-process extraction alternative (`dfvfs`/`pytsk3`) if a no-subprocess path is later wanted.
- D12 EZ-Tools parser wiring (`EvtxECmd`/`PECmd`/`MFTECmd`) in the `sift_lane` parser backend — the
  in-process parsers already cover the extracted artifacts, so this stays optional.
- Broader registry forensics (Shimcache/Amcache/UserAssist/Services), MFT `$UsnJrnl`, fuller evtx
  fields — additive, governed if exposed as new tools.

## Real-evidence run (DA7, human-authorized)
Driver: `/home/sansforensics/projects/rocba_case/driver.py` (external, not committed). It runs
`init-case` → `extract_artifacts_from_image` → evtx/registry/prefetch parsers → `build_timeline` →
memory `decompress` + `analyze_memory`, and writes `reports/findings.{json,md}` into a run dir
**outside the repo** (`/home/sansforensics/projects/rocba_case/case_runs/RUN-*`). The SANS evidence
and the run dir are never committed and never enter CI.

### What the real run validated (RUN-20260608-064510)
- The ROCBA E01 is a **single-volume NTFS** image (no partition table → offset 0). `init-case`
  hashed the originals; the E01 sha is the extraction tool's `source_artifact`/`source_sha256`.
- **218 artifacts** extracted: PowerShell-Operational.evtx, System.evtx, SOFTWARE + SYSTEM hives,
  211 prefetch files, per-user `NTUSER.DAT` (users `fredr`, `srl-h`), and the 469 MB `$MFT`.
- **Security.evtx is corrupt in the image** — NTFS-compressed and unreadable at LZNT1 compression
  unit 284 by **all three** NTFS implementations (libtsk `icat`, libntfs-3g `ntfscat`, libfsntfs
  `pyfsntfs`), so it is recorded as an extraction **failure** (honest, fail-closed) and the run
  continues. This is an evidence property, not a tool defect.
- Parsers ran on the extracted files (e.g. PowerShell 4103/4104 events; real autostart Run keys);
  `build_timeline` merged a **479,383-event** timeline over evtx + prefetch + `$MFT`.
- **Memory:** `analyze_memory` requires a **writable `--symbol-dirs`** — vol's install symbol dir
  is read-only, so downloaded PDB symbols can't cache there (`config.vol_symbol_dirs`, default a
  user cache). The image is Windows 10 build 19041 (x64), captured 2020-11-16.

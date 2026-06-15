# Dataset Documentation

This documents the dataset SIFTMesh investigates and how to reproduce a run against it. The
committed execution logs for this dataset are a single live Claude-agent run
(`docs/logs/rocba-live-RUN-20260615-064002/`) that investigated the disk and memory evidence on the
SANS SIFT workstation. SIFTMesh never self-tests against real forensic
evidence (CLAUDE.md §2B); the maintainer runs the pipeline on the box and the committed bundle is
the resulting real ledgers, audit trail, and report.

---

## The case dataset (ROCBA)

Provided evidence, held read-only on the workstation at `~/projects/data/`. The SHA-256 values below
are the sealed manifest from run `RUN-20260615-064002` (full digests live in
`evidence/evidence_manifest.json` + `evidence/hashes.sha256`) and serve as the chain-of-custody
anchor:

| Artifact | Size (bytes) | SHA-256 (truncated) | Role |
| --- | --- | --- | --- |
| `rocba-cdrive.e01` | 23,678,691,658 | `f2eb856d6fb48e39...` | NTFS disk image (EnCase E01) - primary host evidence |
| `Rocba-Memory.zip` | 5,682,814,481 | `32cec94018051f6c...` | memory capture; auto-decompressed to the raw image below |
| `Rocba-Memory.raw` (derived) | - | `eb33bdf63730858a...` | decompressed raw memory image (Volatility 3 input) |
| `ROCBA-BACKGROUND.pptx` | 40,148,560 | `44a12c54d1324339...` | incident background - the **TRUSTED brief/objective** (`--brief`, never fed to a tool as hostile evidence) |
| `standard_case_1/rocba-cdrive.e01.download` | 2,605,550,889 | `c8710c72a094eff1...` | partial download present in the evidence dir; hashed for custody |

Host: **SRL-FORGE** (Windows 10 x64). Primary user: `fredr` (Fred Rocba); other users `srl-h`,
`rsydow` (admin). Activity window in the artifacts spans **2020-10-21 to 2020-11-16 UTC**; SIFTMesh
emits all timestamps in UTC.

## How SIFTMesh handles it (integrity)

- **Hashed + sealed at ingest** - each file gets a SHA-256 into `evidence_manifest.json` +
  `hashes.sha256` before any analysis; the chain of custody starts there (see
  [`evidence_integrity.md`](https://github.com/aryanbuilds/Project_SIFTMESH/blob/mvp_phase_1/docs/evidence_integrity.md)).
- **Read-only** - originals are opened read-only and never modified; derived artifacts (extracted
  files, decompressed memory) are written only under the run dir.
- **Real, fail-closed tools** - the `.E01` is carved with **Sleuth Kit**
  (`extract_artifacts_from_image`) and the memory image triaged with **Volatility 3**
  (`analyze_memory`), both fixed-argv subprocess backends with no evidence string interpolated into a
  command. A missing backend fails closed.

## What the run found

`RUN-20260615-064002` ran in `--auto` mode and reached the `done` terminal state in about 1 h 57 m
wall clock (sealed 2026-06-15 06:40:02Z, completed 2026-06-15 08:37:01Z). The executor was a live
Claude agent via `claude_headless`; the two heavy tools (disk extract, memory triage) ran on the
deterministic floor by policy. An advisory `opencode` Tier-2 judge ran but never promotes.

Headline numbers from the committed ledgers:

- **28 agent calls** (26 live `claude_headless` + 2 `deterministic_executor`), **0 fallbacks**.
- **25 task contracts**; **245 tool calls** (244 success + 1 honestly-logged parse error on a single
  prefetch file), across **13 distinct tools** drawn from the **19-tool allowlist**.
- **428 artifacts** extracted from the disk image; **674 derived artifacts** carved in total; 24
  derived-gap follow-up tasks were auto-generated mid-run as the plan re-sequenced on findings.
- **223 claims promoted** (182 confirmed + 41 inferred; 0 unsupported; 0 contradicted-status); every
  one anchored to a `tool_call_id` + `source_sha256`, with 0 dangling references.

The IP-theft narrative the agent assembled (all anchored): staging of SRL project files to a
removable `F:` volume and to a Google Drive `G:` mirror under
`G:\My Drive\STARK-RESEARCH-LABS FOLDER\`; SRL email exfil via `SRL-EMAIL-EXPORT.pst` / `backup.pst`;
anti-forensics (SDelete downloaded 2020-11-14, `vssadmin`/`wevtutil` executions, FTK Imager run
2020-11-16); BitLocker recovery-key `.TXT` files copied to `D:`, `E:`, and `G:\My Drive\Key\`; 8
distinct USBSTOR devices; cloud sync via Google Drive File Stream, Dropbox, OneDrive, and iCloud;
517 Amcache program-presence entries; and memory triage over 2,186 processes / 430 network
endpoints. ATT&CK coverage: T1005, T1547.001, and (low-confidence) T1055.

### Limitations of this run

- **`$MFT` and USN change-journal findings are not in the promoted findings.** The live agent failed
  to anchor TASK-016/017/019 on attempt 1, the deterministic critic forced a retry with tightened
  criteria, attempt 2 still failed, and the tasks were escalated and quarantined. `parse_mft_filesystem`
  (22 calls) and `parse_usnjrnl` (15 calls) ran, but produced no promoted claims this pass; the
  governance did not emit unsupported claims for them.
- **Plaso super-timeline was not run this pass** (the fast command omitted
  `SIFTMESH_ENABLE_SUPER_TIMELINE`); it is available behind that flag.
- **Security.evtx was not parsed** (genuine TSK LZNT1 corruption on this image).
- **Prompt-injection alerts are noisy**: 11,628 alerts were logged (never executed), of which 11,625
  are `base64_blob` over-triggers on base64-like hash fragments in tool output - a fail-safe that
  over-flags rather than under-flags.
- **Per-agent LLM token accounting is not recorded** (`agent_calls` carry no token field;
  `token_budget.jsonl` logs profile-routing decisions only).

## Reproduce a run on this data

On the SANS box, the exact command behind the committed bundle:

```bash
SIFTMESH_CAPS__MAX_PARALLEL_TASKS=6 uv run siftmesh run ./case_fast \
  --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --objective "What key projects did Fred Rocba have access to? What was stolen, where to, how, and when?" \
  --auto --agent claude --judge opencode --parallel \
  --max-agent-tasks 400 --max-iterations 2
```

The authoritative outputs land under the run dir:

- `reports/final_report.md` - evidence-anchored findings + MITRE ATT&CK + the chain of custody.
- `reports/accuracy_report.md` - precision/recall vs `expected_findings.md` when ground truth is
  supplied, else an honest self-assessment.
- `claims/claim_ledger.jsonl` - the raw findings, each citing `tool_call_id` + `source_sha256`.
- `audit/*.jsonl` + `uv run siftmesh replay RUN --html` - the full, timestamped, replayable trail.

The committed copy of this run lives at `docs/logs/rocba-live-RUN-20260615-064002/` (including a
self-contained `replay.html`).

## Note on the committed demo fixture

`examples/demo_case/` ships a tiny **public** `Security.evtx` (the `Security_short_selected.evtx`
sample from [omerbenamram/evtx](https://github.com/omerbenamram/evtx), 7 records) as a
reproducibility harness - it lets anyone exercise the real pipeline end to end without licensed
evidence. It is **not** the case data, and its output is **not** a finding on the ROCBA dataset.

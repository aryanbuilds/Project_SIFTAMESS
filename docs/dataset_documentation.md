# Dataset Documentation

This documents the **dataset SIFTMesh investigates** and how to reproduce a run against it. Running the pipeline against this data on the SANS SIFT workstation produces the real findings, accuracy report, and audit trail. Those outputs are **not** committed to the repo (CLAUDE.md §2B: SIFTMesh never self-tests against real forensic evidence, and real-evidence outputs stay on the box).

---

## The case dataset (ROCBA)

Provided evidence sits read-only on the workstation at `~/projects/data/`. The SHA-256 values below come from the **real sealed manifest** of the runs (`RUN-20260612-163324` disk, the full 19-tool sweep; `RUN-20260612-082630` memory). Each value is the chain-of-custody anchor computed at ingest:

| Artifact | Size (bytes) | SHA-256 | Role |
| --- | --- | --- | --- |
| `rocba-cdrive.e01` | 23,678,691,658 | `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` | NTFS disk image (EnCase E01), primary host evidence |
| `Rocba-Memory.zip` | 5,682,814,481 | `32cec94018051f6ce20ec75f1b7b53ad2f6eb5e8bbaec7b402e30409af552b09` | memory capture (nested `…/Rocba-Memory.7z` to raw image) |
| `Rocba-Memory.raw` (derived) | 19,050,528,768 | `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` | decompressed raw memory image (Volatility 3 input) |
| `ROCBA-BACKGROUND.pptx` | 40,148,560 | n/a (objective, not evidence) | incident background, the **TRUSTED objective** (`--brief`, never fed to a tool) |

## How SIFTMesh handles it (integrity)

- **Hashed and sealed at ingest.** Each file gets a SHA-256 into `evidence_manifest.json` plus `hashes.sha256` before any analysis, and the chain of custody starts there (see [`evidence_integrity.md`](evidence_integrity.md)).
- **Read-only.** SIFTMesh opens originals read-only and never modifies them; it writes derived artifacts (extracted files, decompressed memory) only under the run dir.
- **Real, fail-closed tools.** Sleuth Kit carves the `.E01` (`extract_artifacts_from_image`) and Volatility 3 triages the memory image (`analyze_memory`). Both run as fixed-argv subprocess backends with no evidence string interpolated into a command. A missing backend fails closed.

## Reproduce a run on this data

Run this on the SANS box. The job is heavy: the disk image yields 200+ derived tasks and memory triage re-scans the image per plugin.

```bash
uv run siftmesh run ~/cases/rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --agent claude --auto --max-agent-tasks 400 --max-iterations 5
```

The authoritative outputs land under the new run dir:

- `reports/final_report.md` carries evidence-anchored findings, MITRE ATT&CK mapping, and the chain of custody.
- `reports/accuracy_report.md` gives precision/recall vs `expected_findings.md` when ground truth is supplied, otherwise an honest self-assessment.
- `claims/claim_ledger.jsonl` holds the raw findings, each citing `tool_call_id` plus `source_sha256`.
- `audit/*.jsonl` plus `uv run siftmesh replay RUN --html` give the full, timestamped, replayable trail.

The real findings, accuracy self-assessment, and a traceable execution-log excerpt from this dataset are in [`findings_rocba.md`](findings_rocba.md), [`accuracy_report.md`](accuracy_report.md), and [`execution_logs_sample.md`](execution_logs_sample.md). The committed full ledgers for both sealed runs live at [`docs/logs/rocba-disk-RUN-20260612-163324/`](logs/rocba-disk-RUN-20260612-163324/) and [`docs/logs/rocba-memory-RUN-20260612-082630/`](logs/rocba-memory-RUN-20260612-082630/).

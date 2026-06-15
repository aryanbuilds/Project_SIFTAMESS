# Dataset Documentation

This documents the dataset SIFTMesh investigates and how to reproduce a run against it. Findings,
the accuracy report, and the audit trail are produced by running the pipeline against this data on
the SANS SIFT workstation; they are not committed to the repo (CLAUDE.md §2B: SIFTMesh never
self-tests against real forensic evidence, and real-evidence outputs stay on the box).

---

## The case dataset (ROCBA)

Provided evidence, held read-only on the workstation at `~/projects/data/`. The SHA-256 values below
are the sealed manifest from the runs (`RUN-20260612-082004` disk, `RUN-20260612-082630` memory)
and serve as the chain-of-custody anchor:

| Artifact | Size (bytes) | SHA-256 | Role |
| --- | --- | --- | --- |
| `rocba-cdrive.e01` | 23,678,691,658 | `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` | NTFS disk image (EnCase E01) - primary host evidence |
| `Rocba-Memory.zip` | 5,682,814,481 | `32cec94018051f6ce20ec75f1b7b53ad2f6eb5e8bbaec7b402e30409af552b09` | memory capture (nested `…/Rocba-Memory.7z` → raw image) |
| `Rocba-Memory.raw` (derived) | 19,050,528,768 | `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` | decompressed raw memory image (Volatility 3 input) |
| `ROCBA-BACKGROUND.pptx` | 40,148,560 | - (objective, not evidence) | incident background - the **TRUSTED objective** (`--brief`, never fed to a tool) |

## How SIFTMesh handles it (integrity)

- **Hashed + sealed at ingest** - each file gets a SHA-256 into `evidence_manifest.json` +
  `hashes.sha256` before any analysis; the chain of custody starts there (see
  [`evidence_integrity.md`](evidence_integrity.md)).
- **Read-only** - originals are opened read-only and never modified; derived artifacts (extracted
  files, decompressed memory) are written only under the run dir.
- **Real, fail-closed tools** - the `.E01` is carved with **Sleuth Kit** (`extract_artifacts_from_image`)
  and the memory image triaged with **Volatility 3** (`analyze_memory`), both fixed-argv subprocess
  backends with no evidence string interpolated into a command. A missing backend fails closed.

## Reproduce a run on this data

On the SANS box (the disk image yields 200+ derived tasks and memory triage re-scans the image per
plugin):

```bash
uv run siftmesh run ~/cases/rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --agent claude --auto --max-agent-tasks 400 --max-iterations 5
```

The authoritative outputs land under the new run dir:

- `reports/final_report.md` - evidence-anchored findings + MITRE ATT&CK + the chain of custody.
- `reports/accuracy_report.md` - precision/recall vs `expected_findings.md` when ground truth is
  supplied, else an honest self-assessment.
- `claims/claim_ledger.jsonl` - the raw findings, each citing `tool_call_id` + `source_sha256`.
- `audit/*.jsonl` + `uv run siftmesh replay RUN --html` - the full, timestamped, replayable trail.

## Note on the committed demo fixture

`examples/demo_case/` ships a tiny **public** `Security.evtx` (the `Security_short_selected.evtx`
sample from [omerbenamram/evtx](https://github.com/omerbenamram/evtx), 7 records) as a
reproducibility harness - it lets anyone exercise the real pipeline end to end without licensed
evidence. It is **not** the case data, and its output is **not** a finding on the ROCBA dataset.

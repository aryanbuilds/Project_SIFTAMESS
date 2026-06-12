# Dataset Documentation

This documents the **dataset SIFTMesh investigates** and how to reproduce a run against it. The real
findings, accuracy report, and audit trail are produced by running the pipeline against this data on
the SANS SIFT workstation — they are **not** committed to the repo (CLAUDE.md §2B: SIFTMesh never
self-tests against real forensic evidence, and real-evidence outputs stay on the box).

---

## The case dataset (ROCBA)

Provided evidence, held read-only on the workstation at `~/projects/data/`:

| Artifact | Size | Role |
| --- | --- | --- |
| `rocba-cdrive.e01` | ~23.7 GB | NTFS disk image (EnCase E01) — primary host evidence |
| `Rocba-Memory.zip` | ~5.7 GB | memory capture (nested `…/Rocba-Memory.7z` → raw image) |
| `ROCBA-BACKGROUND.pptx` | ~40 MB | incident background — the **TRUSTED objective** (passed via `--brief`, never treated as evidence) |

## How SIFTMesh handles it (integrity)

- **Hashed + sealed at ingest** — each file gets a SHA-256 into `evidence_manifest.json` +
  `hashes.sha256` before any analysis; the chain of custody starts there (see
  [`evidence_integrity.md`](evidence_integrity.md)).
- **Read-only** — originals are opened read-only and never modified; derived artifacts (extracted
  files, decompressed memory) are written only under the run dir.
- **Real, fail-closed tools** — the `.E01` is carved with **Sleuth Kit** (`extract_artifacts_from_image`)
  and the memory image triaged with **Volatility 3** (`analyze_memory`), both fixed-argv subprocess
  backends with no evidence string interpolated into a command. A missing backend fails closed.

## Reproduce a run on this data

On the SANS box (heavy: the disk image yields 200+ derived tasks and memory triage re-scans the image
per plugin):

```bash
uv run siftmesh run ~/cases/rocba --evidence ~/projects/data \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --agent claude --auto --max-agent-tasks 400 --max-iterations 5
```

The authoritative outputs land under the new run dir:

- `reports/final_report.md` — evidence-anchored findings + MITRE ATT&CK + the chain of custody.
- `reports/accuracy_report.md` — precision/recall vs `expected_findings.md` when ground truth is
  supplied, else an honest self-assessment.
- `claims/claim_ledger.jsonl` — the raw findings, each citing `tool_call_id` + `source_sha256`.
- `audit/*.jsonl` + `uv run siftmesh replay RUN --html` — the full, timestamped, replayable trail.

## Note on the committed demo fixture

`examples/demo_case/` ships a tiny **public** `Security.evtx` (the `Security_short_selected.evtx`
sample from [omerbenamram/evtx](https://github.com/omerbenamram/evtx), 7 records) purely as a
**no-keys reproducibility harness** — it lets anyone exercise the real pipeline end to end without
licensed evidence. It is **not** the case data, and its output is **not** a finding on the ROCBA
dataset.

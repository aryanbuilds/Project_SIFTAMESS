<!-- generated_utc: 2026-06-15T08:37:01.561271Z -->
<!-- host: siftworkstation -->
<!-- python: 3.12.3 -->
<!-- run_id: RUN-20260615-064002 -->
<!-- run_dir: case_fast/case_runs/RUN-20260615-064002 -->
<!-- load_mode: strict -->
<!-- SIFTMESH-REPORT-BODY-BELOW -->
# Run Architecture Notes - RUN-20260615-064002

## Run mode & state

- Mode: auto
- State: report
- Self-correction iterations: 2/3
- Gates: plan=pending, retry=pending

## Guardrails active (this run)

- Path policy: all writes confined to the run directory (originals never modified).
- Typed-tool allowlist: only the 19 audited tools; no raw shell / destructive tools.
- Evidence read-only: hashed at ingest; re-hashed on each tool access (custody).
- Spotlighting: 11628 injection alert(s); 3 consequence(s) applied.
- Adapter fall-back to deterministic floor: 0 time(s).

## Security boundaries crossed

- Derived-artifact extraction/decompression: 674 artifact(s) carved.
- Disk-image extraction (Sleuthkit): 1 claim(s).
- Memory analysis (Volatility 3, subprocess-only): 17 claim(s).

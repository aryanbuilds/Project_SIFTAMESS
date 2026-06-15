<!-- generated_utc: 2026-06-13T16:49:58.265472Z -->
<!-- host: siftworkstation -->
<!-- python: 3.12.3 -->
<!-- run_id: RUN-20260612-163324 -->
<!-- run_dir: rocba_full/case_runs/RUN-20260612-163324 -->
<!-- load_mode: strict -->
<!-- SIFTMESH-REPORT-BODY-BELOW -->
# Run Architecture Notes - RUN-20260612-163324

## Run mode & state

- Mode: auto
- State: done (terminal)
- Self-correction iterations: 2/6
- Gates: plan=pending, report=pending, retry=pending

## Guardrails active (this run)

- Path policy: all writes confined to the run directory (originals never modified).
- Typed-tool allowlist: only the 19 audited tools; no raw shell / destructive tools.
- Evidence read-only: hashed at ingest; re-hashed on each tool access (custody).
- Spotlighting: 3949 injection alert(s); 20 consequence(s) applied.
- Adapter fall-back to deterministic floor: 0 time(s).

## Security boundaries crossed

- Derived-artifact extraction/decompression: 852 artifact(s) carved.
- Disk-image extraction (Sleuthkit): 1 claim(s).

<!-- generated_utc: 2026-06-10T07:11:23.138235Z -->
<!-- host: siftworkstation -->
<!-- python: 3.12.3 -->
<!-- run_id: RUN-GOLDEN -->
<!-- run_dir: <RUN> -->
<!-- load_mode: strict -->
<!-- load_error: no run_state.json (run driven by discrete commands; engine snapshot absent) -->
<!-- SIFTMESH-REPORT-BODY-BELOW -->
# Run Architecture Notes — RUN-GOLDEN

## Run mode & state

No engine snapshot (run driven by discrete CLI commands); see events below.

## Guardrails active (this run)

- Path policy: all writes confined to the run directory (originals never modified).
- Typed-tool allowlist: only the 16 audited tools; no raw shell / destructive tools.
- Evidence read-only: hashed at ingest; re-hashed on each tool access (custody).
- Spotlighting: 0 injection alert(s); 0 consequence(s) applied.
- Adapter fall-back to deterministic floor: 0 time(s).

## Security boundaries crossed

- Derived-artifact extraction/decompression: 4 artifact(s) carved.

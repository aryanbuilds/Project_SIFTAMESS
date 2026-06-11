# Dataset Documentation

> **Provenance.** This is a committed copy of SIFTMesh's **deterministic, code-generated** dataset
> documentation (no LLM at report time). It is produced by `siftmesh report` from the sealed evidence
> manifest of a run; the copy below is the golden regression run (`tests/golden/recorded_run/RUN-GOLDEN`,
> the §2B real-tool floor over committed public fixtures). Run any case to regenerate your own at
> `case_runs/RUN-*/reports/dataset_documentation.md`. Every row is anchored to a SHA-256 computed at
> ingest (chain of custody) — see `docs/evidence_integrity.md`.

---

# Dataset Documentation — RUN-GOLDEN

Provenance and integrity of every ingested artifact, generated from the sealed manifest.

## Case

- Case: golden-case
- Run: RUN-20260610-071122
- Sealed (UTC): 2026-06-10 07:11:22 UTC
- Artifacts: 3

## Artifacts (integrity-verified)

| Path | sha256 | Size (bytes) | Type |
| --- | --- | --- | --- |
| CMD.EXE-89305D47.pf | 6127d820b031cac7…edcd0 | 6026 | prefetch |
| NTUSER.DAT | 6a38fcea92411396…cd439 | 786432 | registry |
| Security.evtx | 50c87926d2dfed97…13456 | 69632 | evtx |

These are public upstream test fixtures (omerbenamram/evtx, EricZimmerman/Prefetch,
mkorman90/regipy) — real artifacts parsed by real backends, committed so the demo is reproducible
with no keys and no licensed evidence. The `examples/demo_case` uses the same `Security.evtx`.

## Derived artifacts (carved / parsed)

Originals are never modified; each derived file chains back to its source + producer.

| Derived path | Source artifact | source_sha256 | Produced by |
| --- | --- | --- | --- |
| results/TOOL-001.structured.json | CMD.EXE-89305D47.pf | 6127d820b031cac7… | TOOL-001 (analyze_prefetch) |
| results/TOOL-002.structured.json | NTUSER.DAT | 6a38fcea92411396… | TOOL-002 (extract_registry_run_keys) |
| results/TOOL-003.structured.json | Security.evtx | 50c87926d2dfed97… | TOOL-003 (parse_evtx_security) |
| results/TOOL-004.structured.json | timeline | 4ad00a02214d95f6… | TOOL-004 (build_timeline) |

## Real-evidence datasets (maintainer-gated)

The full hackathon datasets — the ROCBA disk image (`rocba-cdrive.e01`, 22.6 GB) and memory capture
(`Rocba-Memory.zip`, 5.4 GB) — are processed on the SANS SIFT workstation by the maintainer (CLAUDE
§2B: SIFTMesh never self-tests against real forensic evidence). Their handling is documented in
`RUNBOOK.md`; the tools used (Sleuthkit, Volatility 3) are real subprocess backends, fail-closed.

## License & provenance

- Evidence provenance and licensing are the responsibility of the case submitter.
- Integrity anchor: SHA-256 computed at ingest and on each tool access (chain of custody).
- The committed fixtures are public test data from their upstream repositories.

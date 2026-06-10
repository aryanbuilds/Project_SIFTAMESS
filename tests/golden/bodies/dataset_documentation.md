# Dataset Documentation — RUN-GOLDEN

Provenance and integrity of every ingested artifact, generated from the sealed manifest.

## Case

- Case: golden-case
- Run: RUN-20260610-071122
- Sealed (UTC): 2026-06-10 07:11:22.974185+00:00
- Artifacts: 3

## Artifacts (integrity-verified)

| Path | sha256 | Size (bytes) | Type | Modified (UTC) |
| --- | --- | --- | --- | --- |
| CMD.EXE-89305D47.pf | 6127d820b031cac7f5fb1e6d45e244aa48cbb7fa62910ad0317eacb71a0edcd0 | 6026 | prefetch | 2026-06-10 07:11:22.942941+00:00 |
| NTUSER.DAT | 6a38fcea924113963e4931725cc4c2f4f10e1240234cb1867d101a1cd92cd439 | 786432 | registry | 2026-06-10 07:11:22.965974+00:00 |
| Security.evtx | 50c87926d2dfed9776906ffbcc77e61577940910a71fb1c1871860a4e2213456 | 69632 | evtx | 2026-06-10 07:11:22.941981+00:00 |

## Derived artifacts (carved / decompressed)

Originals are never modified; each derived file chains back to its source + producer.
| Derived path | Source artifact | source_sha256 | Produced by | Method |
| --- | --- | --- | --- | --- |
| results/TOOL-001.structured.json | CMD.EXE-89305D47.pf | 6127d820b031cac7… | TOOL-001 | — |
| results/TOOL-002.structured.json | NTUSER.DAT | 6a38fcea92411396… | TOOL-002 | — |
| results/TOOL-003.structured.json | Security.evtx | 50c87926d2dfed97… | TOOL-003 | — |
| results/TOOL-004.structured.json | timeline | 4ad00a02214d95f6… | TOOL-004 | — |

## License & provenance

- Evidence provenance and licensing are the responsibility of the case submitter.
- Integrity anchor: SHA-256 computed at ingest and on each tool access (chain of custody).

# Forensic test fixtures (real upstream samples)

These are **real** sample artifacts taken from the upstream parser projects' own
public test suites — real input that produces real tool output. They are NOT
fabricated/synthetic, and they are NOT the SANS hackathon evidence (that evidence
is human-gated: never committed, never run in CI, parsed only on explicit
maintainer command on the SIFT workstation — see CLAUDE.md §2B).

| file | source repo | upstream path | used by |
|------|-------------|---------------|---------|
| `security_short.evtx` | omerbenamram/evtx (MIT/Apache-2.0) | `samples/Security_short_selected.evtx` | D5 EVTX (Security) |
| `prefetch_vista_cmd.pf` | EricZimmerman/Prefetch (MIT) | `Prefetch.Test/TestFiles/Vista/CMD.EXE-89305D47.pf` | D6 prefetch |
| `prefetch_win2012_cmd.pf` | EricZimmerman/Prefetch (MIT) | `Prefetch.Test/TestFiles/Win2012/CMD.EXE-4A81B364.pf` | D6 prefetch |
| `mft_entry_single` | omerbenamram/mft (Apache-2.0) | `samples/entry_single_file` | D8 timeline ($MFT) |
| `ntuser.dat.xz` | mkorman90/regipy (MIT) | `regipy_tests/data/NTUSER.DAT.xz` | D7 registry (kept xz; decompressed at test time) |
| `jumplist_auto.automaticDestinations-ms` | EricZimmerman/JumpList (MIT) | `JumpList.Test/TestFiles/Win7/1b4dd67f29cb1962.automaticDestinations-ms` | B2 LNK/jumplists (OLE auto-dest) |
| `jumplist_custom.customDestinations-ms` | Matmaus/LnkParse3 (MIT) | `tests/raw/5afe4de1b92fc382.customDestinations-ms` (base64 in repo; **decoded to raw on-disk binary** here) | B2 LNK/jumplists (custom-dest) |
| `lnk_sample.lnk` | derived from `jumplist_auto` above | OLE stream `1` extracted (a real LNK from that public jumplist) | B2 LNK/jumplists (single `.lnk`) |
| `usrclass.dat.xz` | mkorman90/regipy (MIT) | `regipy_tests/data/UsrClass.dat.xz` | B3 shellbags (UsrClass BagMRU; decompressed at test time) |
| `ntuser_bagmru.dat.xz` | mkorman90/regipy (MIT) | `regipy_tests/data/NTUSER_BAGMRU.DAT.xz` | B3 shellbags (NTUSER BagMRU; decompressed at test time) |

Note: no PowerShell-Operational sample exists in any upstream parser test suite, so
`parse_evtx_powershell`'s 4103/4104 filter is validated by (a) the generic
event-id-filter test against `security_short.evtx` and (b) asserting the PowerShell
filter returns no rows on a Security log (correct exclusion). Real PowerShell
script-block extraction is human-gated on SANS evidence.

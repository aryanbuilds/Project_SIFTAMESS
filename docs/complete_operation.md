# ROCBA: Complete Operation Log

This is a record of the SIFTMesh investigation against the ROCBA dataset on the SANS SIFT workstation. It logs every command, its result, the findings, and the mapping to the five questions the incident brief asks. Nothing here is fabricated. Where the data does not answer a question, this document says so.

> **Scope.** This run used SIFTMesh's **19-tool** governed allowlist: the original 10 (hash, vault,
> EVTX-security, EVTX-PowerShell, prefetch, registry-Run-keys, timeline, claim-validation,
> disk-image extraction, memory triage) plus the 9 deep-evidence tools added in Phases A-C:
> `parse_mft_filesystem`, `parse_recentdocs_mru`, `parse_usb_registry`, `parse_browser_history`,
> `parse_lnk_jumplists`, `parse_shellbags`, `parse_amcache_shimcache`, `parse_usnjrnl`, and
> `build_super_timeline` (Plaso). With these, the run answers **all five** brief questions. See
> "Objective coverage" below. The remaining gaps (SRUM, Outlook email, server-side SharePoint logs) are
> documented in §5.

---

## 1. Case facts (from the brief + probed host)

| | |
|---|---|
| Subject | Fred Rocba, `frocba@stark-research-labs.com` (Stark Research Labs / SRL) |
| Scenario | Suspected insider IP theft; "Fred on vacation, pictures synced to his home system" |
| Host (from evidence) | **SRL-FORGE**, Windows 10 x64 |
| Timezone | EST5EDT (Eastern). **SIFTMesh outputs UTC**; convert for the report (UTC−5/−4) |
| SRL systems in scope | Office 365, SharePoint, OneDrive (personal + business), Exchange Online / local Outlook |
| Evidence | `rocba-cdrive.e01` (disk) · `Rocba-Memory.zip` (memory) · `ROCBA-BACKGROUND.pptx` (brief = objective) |

The sealed hashes for chain of custody are in [`dataset_documentation.md`](dataset_documentation.md).

## 2. The operation (commands + real results)

We ran everything from `~/projects/Project_SIFTAMESS`. Heavy steps run with long timeouts or in the background.

### 2.1 Host setup + verify (no evidence touched)
```bash
uv sync --all-extras          # incl. regipy[full] (libfwsi/libfwps), LnkParse3, olefile
uv run siftmesh doctor        # → "gateway tool allowlist: 19 tools, no forbidden"; Plaso + TSK + vol OK
```

### 2.2 Disk image: one-command full-auto (seal → extract → re-ingest → parse → super-timeline)
```bash
ln -f ~/projects/data/rocba-cdrive.e01 ~/projects/ev_disk/
SIFTMESH_ENABLE_SUPER_TIMELINE=true SIFTMESH_HEAVY_TOOL_TIMEOUT_SECONDS=7200 \
  uv run siftmesh run ./rocba_full --evidence ~/projects/ev_disk \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx --auto --max-agent-tasks 400 --max-iterations 6
RUN=rocba_full/case_runs/RUN-20260612-163324
```
Real results:
- `init-case` hashed the 23.7 GB e01 to sha256 `f2eb856d…`; it ingested the brief as the trusted objective.
- The engine **extracted** the high-value artifacts with TSK, including `$MFT`, per-user `NTUSER.DAT` /
  `UsrClass.dat`, browser `History`, the Recent/JumpList tree, `Amcache.hve`, and the `$UsnJrnl:$J`
  ADS. It then **auto re-ingested** them and dispatched the typed parsers through the derived-gap loop.
- **634 claims promoted, 0 unsupported, 0 contradictions.** Tool successes: `parse_mft_filesystem` 1,
  `parse_browser_history` 3, `parse_lnk_jumplists` 201, `parse_shellbags` 4, `parse_amcache_shimcache` 2,
  `parse_recentdocs_mru` 2, `parse_usb_registry` 3, `parse_usnjrnl` 1, `build_super_timeline` 1,
  `extract_registry_run_keys` 4, `analyze_prefetch` 200, `parse_evtx_powershell` 1.
- We logged one honest failure: `Security.evtx` extraction fails with a genuine TSK LZNT1 NTFS-decompression error
  (recorded in `failed[]`). For prompt-injection, the run flagged and logged the evidence strings that looked like
  instructions and never executed them.

> **Two issues this run surfaced (both fixed, commit `9c24e23`):** (1) Plaso's full-disk scan crashes
> on this image's **unreadable VSS backup header**, a partial-acquisition trait. We added `--vss_stores
> none` plus a fallback to the extracted-artifacts dir, and built the 5,727,623-event timeline that way.
> (2) The `--auto` derived re-ingest only minted **primary**-family tasks, so the
> `recentdocs`/`usb`/`shellbags` extras on NTUSER and `shimcache` on SYSTEM did not auto-fire. We fixed
> `generate_followup_tasks` / `ingest_derived` to apply `extra_tools_for` to carved hives. The run then
> dispatched those tasks (`TASK-018…025`).

### 2.3 Memory: seal, decompress, triage (Volatility 3), reclaim space
```bash
ln -f ~/projects/data/Rocba-Memory.zip ~/projects/ev_mem/
uv run siftmesh init-case ./case_mem --evidence ~/projects/ev_mem
RUNM=case_mem/case_runs/RUN-20260612-082630
uv run siftmesh evidence decompress "$RUNM" --archive Rocba-Memory.zip --evidence ~/projects/ev_mem
uv run siftmesh evidence memory "$RUNM" --evidence "$RUNM" --memory evidence/extracted/Rocba-Memory.raw \
  --plugins pslist --plugins pstree --plugins netscan --plugins cmdline --plugins malfind
uv run siftmesh prune "$RUNM"
```
Real results: `Rocba-Memory.raw` (19,050,528,768 B, sha256 `eb33bdf6…`); Win10 x64; **all 6 plugins ran,
0 failed**; **2,186 processes, 430 net endpoints, 16 `malfind` regions**; `prune` freed 17.7 GB.

## 3. Findings (evidence-anchored; full set in the run ledgers)

The headline question-by-question answers and the per-artifact detail are in
[`findings_rocba.md`](findings_rocba.md). In brief: Fred stole **ADAMANTIUM** research from OneDrive
`Research`, exfiltrated it to his **personal Google Drive** (he downloaded and ran the Backup-and-Sync
installer; `Google Drive\…` LNK targets) and to **USB** (5 USBSTOR devices including Lexar/innostor). He
cleaned up with **SDelete** and **47,966 USN deletions**, including the Google-sync DBs. The `$MFT`
lists 479,359 files; the Plaso super-timeline holds 5,727,623 events. Memory shows live OneDrive, iCloud,
and Teams cloud egress.

## 4. Objective coverage: does this run answer the brief's 5 questions?

**Verdict: yes, leads for all five** (analyst-grade, not a legal conclusion).

| Brief question | Status | What the run shows (tool) |
|---|---|---|
| **What key projects did Fred have access to?** | ✅ Answered (lead) | **ADAMANTIUM**: OneDrive `Research\…Adamantium.pptx` + `ADAMANTIUM-Background.docx` (`parse_lnk_jumplists`); shellbags of `OneDrive…\Research`, `Documents\SRL` (`parse_shellbags`); `SRL VPN Setup.pdf` (`parse_recentdocs_mru`). |
| **What was stolen?** | ✅ Answered (lead) | SRL research + business docs copied to personal `Google Drive\…` (BetterWidgets, NETFLIX, Firedam) (`parse_lnk_jumplists`); `$MFT` 479,359-file inventory (`parse_mft_filesystem`); 47,966 deletions incl. sync DBs (`parse_usnjrnl`). |
| **Where was it transferred to?** | ✅ Answered (lead) | Personal **Google Drive** (Backup-and-Sync download, `parse_browser_history`) + **OneDrive**; **5 USB devices** + MountPoints2 (`parse_usb_registry`). |
| **How was it stolen?** | ✅ Answered (lead) | Cloud-sync clients **executed**: GoogleDriveFS / googledrivesync / installbackupandsync / Teams (`parse_amcache_shimcache`) + Run-key persistence; USB attachment; **SDelete** anti-forensics (`parse_lnk_jumplists` + USN deletions). |
| **When did the activity occur?** | ✅ Answered (lead) | USN per-record FILETIMEs (149,424 creates / 47,966 deletes / 24,577 renames); `$MFT` timestamps; **Plaso super-timeline 5,727,623 events**; prefetch through 2020-11-16 02:50 UTC; memory ~2020-11-16. |

## 5. Remaining honest gaps (documented, fail-closed, not invented)

- **`Security.evtx`**: genuine LZNT1 corruption in this image; we recorded it as a failure and never faked it.
- **Full-disk super-timeline**: this image's VSS backup header is unreadable (partial acquisition), so
  we built the Plaso timeline over the *extracted artifacts*. That output is real but narrower than a full-volume run.
- **Outlook/Exchange email** (OST/PST) and **server-side SharePoint/M365 audit logs**: out of the
  on-disk allowlist. OST is often encrypted, and tenant logs are not on the image. Phase D (OST/ODL) is the
  documented, deferred roadmap.
- **SRUM** (per-app bytes-sent): no viable parser on this host, so we did not build it.
- This is **investigative triage to guide a human examiner, not a court-ready conclusion.**

## 6. Integrity & provenance

We opened the evidence read-only and sealed each item with SHA-256 at ingest. Every promoted claim cites
its `tool_call_id` and `source_sha256`, and unsupported claims stay firewalled out of the findings
(Appendix B of the run's `reports/final_report.md`). The full ledgers and `replay.html` live in the run
dirs (`rocba_full/…`, `case_mem/…`), uncommitted per CLAUDE.md §2B. The committed full ledgers for this
write-up are at `docs/logs/rocba-disk-RUN-20260612-163324/` and
`docs/logs/rocba-memory-RUN-20260612-082630/`.

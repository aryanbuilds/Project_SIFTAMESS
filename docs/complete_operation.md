# ROCBA - Complete Operation Log

This log records every command, its result, the findings, and the mapping to the five brief questions.
Where the data does not answer a question, this document says so.

> **Scope.** This run used SIFTMesh's **19-tool** governed allowlist - the original 10 (hash · vault ·
> EVTX-security · EVTX-PowerShell · prefetch · registry-Run-keys · timeline · claim-validation ·
> disk-image extraction · memory triage) **plus the 9 deep-evidence tools** added in Phases A–C:
> `parse_mft_filesystem`, `parse_recentdocs_mru`, `parse_usb_registry`, `parse_browser_history`,
> `parse_lnk_jumplists`, `parse_shellbags`, `parse_amcache_shimcache`, `parse_usnjrnl`, and
> `build_super_timeline` (Plaso). With these, the run answers **all five** brief questions - see
> "Objective coverage" below. Remaining gaps (SRUM, Outlook email, server-side SharePoint logs) are
> documented in §5.

---

## 1. Case facts (from the brief + probed host)

| | |
|---|---|
| Subject | Fred Rocba - `frocba@stark-research-labs.com` (Stark Research Labs / SRL) |
| Scenario | Suspected insider IP theft; "Fred on vacation, pictures synced to his home system" |
| Host (from evidence) | **SRL-FORGE** - Windows 10 x64 |
| Timezone | EST5EDT (Eastern) - **SIFTMesh outputs UTC**; convert for the report (UTC−5/−4) |
| SRL systems in scope | Office 365, SharePoint, OneDrive (personal + business), Exchange Online / local Outlook |
| Evidence | `rocba-cdrive.e01` (disk) · `Rocba-Memory.zip` (memory) · `ROCBA-BACKGROUND.pptx` (brief = objective) |

Sealed hashes (chain of custody) are in [`dataset_documentation.md`](dataset_documentation.md).

## 2. The operation (commands + real results)

Run from `~/projects/Project_SIFTAMESS`. Heavy steps run with long timeouts / in the background.

### 2.1 Host setup + verify (no evidence touched)
```bash
uv sync --all-extras          # incl. regipy[full] (libfwsi/libfwps), LnkParse3, olefile
uv run siftmesh doctor        # → "gateway tool allowlist: 19 tools, no forbidden"; Plaso + TSK + vol OK
```

### 2.2 Disk image - one-command full-auto (seal → extract → re-ingest → parse → super-timeline)
```bash
ln -f ~/projects/data/rocba-cdrive.e01 ~/projects/ev_disk/
SIFTMESH_ENABLE_SUPER_TIMELINE=true SIFTMESH_HEAVY_TOOL_TIMEOUT_SECONDS=7200 \
  uv run siftmesh run ./rocba_full --evidence ~/projects/ev_disk \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx --auto --max-agent-tasks 400 --max-iterations 6
RUN=rocba_full/case_runs/RUN-20260612-163324
```
Real results:
- `init-case` hashed the 23.7 GB e01 → sha256 `f2eb856d…`; brief ingested as the objective.
- The engine **extracted** the high-value artifacts (TSK) - incl. `$MFT`, per-user `NTUSER.DAT` /
  `UsrClass.dat`, browser `History`, the Recent/JumpList tree, `Amcache.hve`, and the `$UsnJrnl:$J`
  ADS - then **re-ingested** them and dispatched the typed parsers (the derived-gap loop).
- **634 claims promoted, 0 unsupported, 0 contradictions.** Tool successes: `parse_mft_filesystem` 1,
  `parse_browser_history` 3, `parse_lnk_jumplists` 201, `parse_shellbags` 4, `parse_amcache_shimcache` 2,
  `parse_recentdocs_mru` 2, `parse_usb_registry` 3, `parse_usnjrnl` 1, `build_super_timeline` 1,
  `extract_registry_run_keys` 4, `analyze_prefetch` 200, `parse_evtx_powershell` 1.
- Honest failure: `Security.evtx` extraction fails with a genuine TSK LZNT1 NTFS-decompression error
  (recorded in `failed[]`). Prompt-injection: evidence strings that looked like instructions were
  flagged + logged, never executed.

> **Two issues this run surfaced (both fixed, commit `9c24e23`):** (1) Plaso's full-disk scan crashes
> on this image's **unreadable VSS backup header** (a partial-acquisition trait) → added `--vss_stores
> none` + a fallback to the extracted-artifacts dir (the 5,727,623-event timeline was built that way).
> (2) The `--auto` derived re-ingest only minted **primary**-family tasks, so the
> `recentdocs`/`usb`/`shellbags` extras on NTUSER and `shimcache` on SYSTEM didn't auto-fire → fixed
> `generate_followup_tasks` / `ingest_derived` to apply `extra_tools_for` to carved hives. Those tasks
> were then dispatched into this run (`TASK-018…025`).

### 2.3 Memory - seal, decompress, triage (Volatility 3), reclaim space
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

The headline question-by-question answers + per-artifact detail are in
[`findings_rocba.md`](findings_rocba.md). In brief: stolen **ADAMANTIUM** research (OneDrive
`Research`), exfil to **personal Google Drive** (Backup-and-Sync installer downloaded + run; `Google
Drive\…` LNK targets) and **USB** (5 USBSTOR devices incl. Lexar/innostor), with **SDelete** +
**47,966 USN deletions** (incl. the Google-sync DBs) as cleanup; `$MFT` 479,359 files; a 5,727,623-event
Plaso super-timeline. Memory shows live OneDrive/iCloud/Teams cloud egress.

## 4. Objective coverage - does this run answer the brief's 5 questions?

**Verdict: yes - leads for all five**.

| Brief question | Status | What the run shows (tool) |
|---|---|---|
| **What key projects did Fred have access to?** | ✅ Answered (lead) | **ADAMANTIUM** - OneDrive `Research\…Adamantium.pptx` + `ADAMANTIUM-Background.docx` (`parse_lnk_jumplists`); shellbags of `OneDrive…\Research`, `Documents\SRL` (`parse_shellbags`); `SRL VPN Setup.pdf` (`parse_recentdocs_mru`). |
| **What was stolen?** | ✅ Answered (lead) | SRL research + business docs copied to personal `Google Drive\…` (BetterWidgets, NETFLIX, Firedam) (`parse_lnk_jumplists`); `$MFT` 479,359-file inventory (`parse_mft_filesystem`); 47,966 deletions incl. sync DBs (`parse_usnjrnl`). |
| **Where was it transferred to?** | ✅ Answered (lead) | Personal **Google Drive** (Backup-and-Sync download, `parse_browser_history`) + **OneDrive**; **5 USB devices** + MountPoints2 (`parse_usb_registry`). |
| **How was it stolen?** | ✅ Answered (lead) | Cloud-sync clients **executed** - GoogleDriveFS / googledrivesync / installbackupandsync / Teams (`parse_amcache_shimcache`) + Run-key persistence; USB attachment; **SDelete** anti-forensics (`parse_lnk_jumplists` + USN deletions). |
| **When did the activity occur?** | ✅ Answered (lead) | USN per-record FILETIMEs (149,424 creates / 47,966 deletes / 24,577 renames); `$MFT` timestamps; **Plaso super-timeline 5,727,623 events**; prefetch through 2020-11-16 02:50 UTC; memory ~2020-11-16. |

## 5. Remaining honest gaps (documented, fail-closed - not invented)

- **`Security.evtx`** - genuine LZNT1 corruption in this image; recorded as a failure, never faked.
- **Full-disk super-timeline** - this image's VSS backup header is unreadable (partial acquisition), so
  the Plaso timeline was built over the *extracted artifacts* (real, but narrower than a full-volume run).
- **Outlook/Exchange email** (OST/PST) and **server-side SharePoint/M365 audit logs** - out of the
  on-disk allowlist (OST is often encrypted; tenant logs aren't on the image). Phase D (OST/ODL) is the
  documented, deferred roadmap.
- **SRUM** (per-app bytes-sent) - no viable parser on this host; not built.
- This is **investigative triage to guide a human examiner, not a court-ready conclusion.**

## 6. Integrity & provenance

Evidence opened read-only; SHA-256 sealed at ingest; every promoted claim cites `tool_call_id` +
`source_sha256`; unsupported claims are firewalled out of the findings (Appendix B of the run's
`reports/final_report.md`). Full ledgers + `replay.html` live in the run dirs (`rocba_full/…`,
`case_mem/…`), uncommitted per CLAUDE.md §2B.

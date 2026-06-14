# ROCBA — Findings (full 19-tool sweep)

Output from running SIFTMesh against the provided ROCBA dataset on the SANS SIFT workstation.
Every finding below is anchored to a real tool call + the SHA-256 of its source artifact (chain of
custody). This is an **automated triage to guide an analyst — not a court-ready conclusion.**

| | |
|---|---|
| Disk run | `RUN-20260612-163324` — `rocba-cdrive.e01` · sha256 `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` (23,678,691,658 B) |
| Memory run | `RUN-20260612-082630` — `Rocba-Memory.zip` → `Rocba-Memory.raw` · sha256 `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` (19,050,528,768 B) |
| Tools (19 allowlisted) | Sleuth Kit extraction · `parse_mft_filesystem` · `parse_recentdocs_mru` · `parse_usb_registry` · `parse_browser_history` · `parse_lnk_jumplists` · `parse_shellbags` · `parse_amcache_shimcache` · `parse_usnjrnl` · `build_super_timeline` (Plaso) · `extract_registry_run_keys` · `analyze_prefetch` · `parse_evtx_powershell` · Volatility 3 (memory) |
| Critic | Tier-1 deterministic: **634 claims promoted, 0 unsupported, 0 contradictions** (disk run) |

## Objective (from the incident brief)

`ROCBA-BACKGROUND.pptx`, ingested as the trusted objective: *Fred Rocba and Stark Research Labs (SRL)
— suspected insider IP theft; Fred on vacation, "pictures synced to his home system."* Host:
**SRL-FORGE** (Windows 10 x64). Brief timezone EST5EDT; **SIFTMesh outputs UTC**.

---

## Answers to the five brief questions (real, evidence-anchored)

> Each answer is a **lead** built from real tool output (cited inline); the synthesis across leads is
> analyst-grade, **not** a closed legal finding.

**Q1 — What key projects did Fred have access to?**
The **ADAMANTIUM** research project. LNK/JumpList targets (`parse_lnk_jumplists`) point at
`C:\Users\fredr\OneDrive - Stark Research Labs\Research\France DGSE Intel Analysis Adamantium .pptx`
and `…\OneDrive - Stark Research Labs\Documents\ADAMANTIUM-Background.docx`. Shellbags
(`parse_shellbags`) show Fred browsing `OneDrive - Stark Research Labs\Research`, `Documents\SRL`, and
`Documents\Zoom\…Fred Rocba's Zoom Meeting…`. RecentDocs (`parse_recentdocs_mru`) include
`SRL VPN Setup.pdf`.

**Q2 — What was stolen?**
SRL research from the OneDrive `Research`/`Documents` tree (the ADAMANTIUM project above), plus
business/financial documents copied into a **personal** Google Drive — LNK targets under
`C:\Users\fredr\Google Drive\…` include `BetterWidgets Business Plan\BusinessPlan.docx`,
`NETFLIX SEC Filings\NETFLIX_10-K_20130201.xls`, and `Firedam.xls`. The `$MFT` inventory
(`parse_mft_filesystem`) recorded **479,359 filesystem entries (371,723 files)**; the USN journal
(`parse_usnjrnl`) recorded **47,966 deletions** including the Google-sync databases (`sync_config.db`,
`uploader.db`) — consistent with staging then cleanup.

**Q3 — Where was it transferred?**
Two channels. (a) **Personal cloud** — a Chrome download of `installbackupandsync.exe`
(`parse_browser_history`) plus the `C:\Users\fredr\Google Drive\…` LNK targets = data pushed to a
personal Google account, alongside personal OneDrive. (b) **Removable media** — `parse_usb_registry`
recovered **5 USBSTOR devices** (`Lexar USB Flash Drive`, `USB DISK 2.0`, `IS917 innostor`,
`Generic Mass Storage`, `Multiple Card Reader`) + 20 NTUSER MountPoints2 entries; RecentDocs references
`USB Drive (D:)`.

**Q4 — How?**
**Cloud-sync clients + USB.** ShimCache/Amcache (`parse_amcache_shimcache`) show `GoogleDriveFS.exe`,
`googledrivesync.exe`, `installbackupandsync (1).exe`, `GoogleDriveFSSetup.exe`, `GoogleUpdate.exe`,
and `Teams_windows_x64.exe` executed; registry Run keys (`extract_registry_run_keys`) persist
`GoogleDriveFS`/`GoogleDriveSync`/`OneDrive`. **Anti-forensics:** a LNK target
`C:\Users\fredr\Downloads\SDelete.zip` (Sysinternals secure-delete) corroborates the 47,966 USN
deletions + the deleted Google-sync DBs.

**Q5 — When?**
The USN journal carries per-record FILETIME timestamps across 149,424 creates / 47,966 deletes /
24,577 renames; `$MFT` SI/FN timestamps date the files; the **Plaso super-timeline**
(`build_super_timeline`) consolidated **5,727,623 timeline events**. Latest prefetch execution ≈
2020-11-16 02:50 UTC; memory captured ≈ 2020-11-16.

---

## Disk image — per-artifact detail (each claim anchored to its tool + source SHA-256)

- **Filesystem inventory (`parse_mft_filesystem`, `$MFT`):** 479,359 entries — 371,723 files,
  107,636 directories.
- **Browser history (`parse_browser_history`, 3 databases):** Chrome (`fredr`) 119 visits + 2 downloads
  — `installbackupandsync.exe` / `installbackupandsync (1).exe` (Google Backup & Sync installer).
- **LNK / JumpLists (`parse_lnk_jumplists`, 201 artifacts):** opened-file targets across OneDrive
  Research (ADAMANTIUM `.pptx`/`.docx`), personal `Google Drive\…` (BetterWidgets, NETFLIX, Firedam),
  and `Downloads\` (research PDFs + `SDelete.zip`).
- **Shellbags (`parse_shellbags`, 4 hives — UsrClass + NTUSER):** 138+ distinct browsed folders incl.
  `OneDrive - Stark Research Labs\Research`, `Documents\SRL`, `Documents\Zoom\…`, `Downloads`, `Pictures`
  (folders persist even after deletion).
- **Removable media (`parse_usb_registry`):** 5 USBSTOR devices (above) + MountPoints2 GUID volumes.
- **RecentDocs (`parse_recentdocs_mru`):** `SRL VPN Setup.pdf`, `USB Drive (D:)`, a BitLocker recovery
  key, `fred.rocba@outlook.com Firefox Recovery Key`, plus personal items.
- **Program execution (`parse_amcache_shimcache`):** 517 Amcache + 391 ShimCache entries; Google Drive /
  Backup-and-Sync / Teams binaries confirmed run.
- **USN change journal (`parse_usnjrnl`, `$Extend\$UsnJrnl:$J`):** 383,915 records — 149,424 created,
  47,966 deleted, 24,577 renamed (deleted set includes the Google-sync DBs = exfil cleanup).
- **Super-timeline (`build_super_timeline`, Plaso):** 5,727,623 events (see caveat on source below).
- **Persistence (`extract_registry_run_keys`, SOFTWARE/user hives):** `GoogleDriveFS`, `GoogleDriveSync`,
  `OneDrive`/`OneDriveSetup`, `com.squirrel.Teams.Teams`, `SecurityHealth`, `WAB Migrate` (RunOnce), and
  a GUID-named `C18E42C7…._service_run` — worth manual review.
- **Execution history (`analyze_prefetch`, 200 prefetch files):** AcroRd32, Slack, SmartScreen,
  MicrosoftEdgeUpdate, Adobe ARM, etc., each with run count + source `.pf`.
- **PowerShell (`parse_evtx_powershell`, host `SRL-FORGE`):** 2× EventID 4104 (script-block) — a
  **benign Microsoft troubleshooting-pack script**, not attacker activity.

## Memory — runtime state (Volatility 3, separate run `RUN-20260612-082630`, 6 plugins, 0 failed)

Anchored to `Rocba-Memory.raw` (sha256 `eb33bdf6…`). 2,186 processes; 430 network endpoints. External
egress to iCloud/Apple (`17.248.x`, `17.57.144.165`), OneDrive/Teams cloud, and `svchost` →
`81.30.144.115:56687` / `213.202.233.104:13939` (flagged for review, not concluded malicious). 16
`malfind` RWX hits were in system processes (MsMpEng/SearchApp/dllhost/Teams) — flagged, not malicious.

## Caveats

- **`Security.evtx`** failed extraction — a genuine TSK LZNT1 decompression error on this image
  (recorded in `failed[]`).
- **Super-timeline source.** The full-disk Plaso run aborts on this image's **unreadable VSS backup
  NTFS header** (offset ≈ 81 GB, past the 23 GB physical `.E01` → a *partial/sparse acquisition*). The
  5,727,623-event timeline was therefore built over the **extracted high-value artifacts** (real Plaso,
  real carved evidence) via a deliberate, recorded fallback — narrower than a full filesystem timeline.
- **Prompt-injection defense:** evidence strings that looked like instructions were flagged + logged,
  never executed.
- This is an **automated triage** — analyst-grade leads with full provenance, **not** a court
  conclusion.

## Provenance & integrity

- Evidence opened read-only; SHA-256 sealed at ingest (chain of custody) — see
  [`evidence_integrity.md`](evidence_integrity.md) and [`dataset_documentation.md`](dataset_documentation.md).
- Every claim cites `tool_call_id` + `source_sha256`; unsupported claims are excluded from the
  findings (Appendix B of the run's `reports/final_report.md`).
- Reproduce: see [`complete_operation.md`](complete_operation.md). The full ledgers + replay live in the
  run dirs (`rocba_full/…`, `case_mem/…`), uncommitted per CLAUDE.md §2B.

# ROCBA - Findings (live Claude-agent run)

Output from running SIFTMesh against the provided ROCBA dataset on the SANS SIFT workstation. A live Claude agent (sandboxed `claude_headless`) drove the typed forensic tools; the heavy tools (disk
extraction, memory triage) ran on the deterministic floor by policy, and disk and memory were processed
in one run. Every finding below is anchored to a real tool call and the SHA-256 of its source artifact
(chain of custody). This is automated triage to guide an analyst, not a court-ready conclusion.

| | |
|---|---|
| Run | `RUN-20260615-064002` (auto, live `--agent claude`, `--judge opencode`) - disk + memory in one pass |
| Disk | `rocba-cdrive.e01` · sha256 `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` (23,678,691,658 B) |
| Memory | `Rocba-Memory.zip` -> `Rocba-Memory.raw` · sha256 `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` |
| Tools used (of 19 allowlisted) | Sleuth Kit extraction · `analyze_memory` (Volatility 3) · `analyze_prefetch` · `parse_lnk_jumplists` · `parse_usb_registry` · `parse_recentdocs_mru` · `parse_shellbags` · `parse_amcache_shimcache` · `parse_browser_history` · `extract_registry_run_keys` · `parse_evtx_powershell` (`parse_mft_filesystem` / `parse_usnjrnl` ran but were quarantined - see below) |
| Critic | Tier-1 deterministic: **223 claims promoted (182 confirmed + 41 inferred), 0 unsupported**; 5 contradictions caught, 14 over-broad claims downgraded, 7 tasks quarantined |
| Committed ledgers | [`logs/rocba-live-RUN-20260615-064002/`](https://github.com/aryanbuilds/Project_SIFTMESH/tree/mvp_phase_1/docs/logs/rocba-live-RUN-20260615-064002) |

## Objective (from the incident brief)

`ROCBA-BACKGROUND.pptx`, ingested as the trusted objective: *Fred Rocba and Stark Research Labs (SRL) -
suspected insider IP theft; Fred on vacation, "pictures synced to his home system."* Host:
**SRL-FORGE** (Windows 10 x64); primary user **fredr** (Fred Rocba); other users `srl-h` and admin
`rsydow`. Activity in the artifacts spans **2020-10-21 to 2020-11-16 UTC**. SIFTMesh outputs UTC.

---

## Answers to the brief questions (real, evidence-anchored)

> Each answer is a **lead** built from real tool output (cited inline); the synthesis across leads is
> analyst-grade, **not** a closed legal finding.

**Q1 - What key projects did Fred have access to?**
A broad set of SRL intellectual property. `parse_lnk_jumplists`, `parse_recentdocs_mru`, and
`parse_shellbags` resolve opened-file targets across **Megaforce, Blue Thunder, Airwolf / Wolf Air,
KITT, Adamantium, Gunstar (FTL Comms), New Alloy Research, Vibrainium**, plus files such as
`Research to Weaponize the Ion Thruster.docx`, `The Future of KITT.pptx`,
`RareEarthDeposits_Confidential`, `France DGSE Intel Analysis Adamantium .pptx`, and
`Quantum Particles Affected by Other Dimensions.pdf`. Many resolve under
`C:\Users\fredr\Stark Research Labs\…`, `…\OneDrive - Stark Research Labs\…`, and SRL SharePoint.

**Q2 - What was stolen?**
SRL research, financials, and email. LNK/JumpList targets include `Wolf AIr Financials.xlsx`, the SRL
project trees above, and two large Outlook archives: **`SRL-EMAIL-EXPORT.pst` (20,587,520 bytes)** and
**`backup.pst` (20,587,520 bytes)**. **BitLocker recovery-key `.TXT` files** were copied off the system
(Notepad JumpList + LNK targets to `D:`, `E:`, and `G:\My Drive\Key\`).

**Q3 - Where was it transferred?**
Two staging channels, both anchored in `parse_lnk_jumplists`:
- **Removable volume F:** purpose-named staging folders -
  `F:\Files of interest\SRL-Projects - Megaforce\Megaforce\Megaforce Specs & Research.docx`,
  `F:\Key Data\SRL-Projects - Blue Thunder\…`, `F:\Files from SRL system`,
  `F:\Files of interest\Recovered Documents\Wolves_Lair_Tech_Specs.pptx`.
- **Google Drive G:** a full mirror under `G:\My Drive\STARK-RESEARCH-LABS FOLDER\` (Airwolf, Wolf Air
  financials, Research, Vibrainium, KITT, and `Exported-PST\SRL-EMAIL-EXPORT.pst`).
- Plus personal cloud: OneDrive, Dropbox, and **iCloud** (`ICLOUDIE.EXE` executed 59 times -
  "pictures synced to Fred's home system").

**Q4 - How?**
**Cloud-sync clients + USB + anti-forensics.**
- Cloud: `GOOGLEDRIVEFS.EXE` (Google Drive File Stream) ran many times; Chrome downloaded the Google
  "Backup and Sync" installer **twice** (`installbackupandsync.exe`, 1,317,080 bytes, 2020-10-31 and
  2020-11-10 - `parse_browser_history`); OneDrive and Dropbox clients present.
- Removable media: `parse_usb_registry` recovered **8 distinct USBSTOR devices** (Lexar USB Flash Drive,
  IS917 innostor, two USB DISK 2.0, three Generic Mass Storage, Multiple Card Reader) in the SYSTEM hive,
  plus **20 MountPoints2** entries under Fred's NTUSER.
- Anti-forensics: **`SDelete.zip`** (Sysinternals secure-delete, 226,573 bytes) downloaded to
  `C:\Users\fredr\Downloads\` on 2020-11-14T13:37:51Z; `vssadmin.exe` ran 3x and `VSSVC.EXE` 8x;
  `wevtutil.exe` ran 4x within ~2 seconds on 2020-11-14 (event-log tampering); **`FTK IMAGER.EXE`** was
  executed once at 2020-11-16T02:43:57Z (the latest dated execution observed - the imaging event).

**Q5 - When?**
Program-execution and access timestamps cluster the staging activity around **2020-11-13 / 2020-11-14**;
`SDelete.zip` downloaded 2020-11-14T13:37:51Z; the two PowerShell script-block events on 2020-11-02 and
2020-11-10; Amcache program-presence spans 2020-10-21T03:44:22Z to 2020-11-14T13:50:48Z; the latest
dated execution is `FTK IMAGER.EXE` at 2020-11-16T02:43:57Z, consistent with the disk/memory capture.

---

## Per-artifact detail (each claim anchored to its tool + source SHA-256)

- **Execution history (`analyze_prefetch`, 49 prefetch files):** `ICLOUDIE.EXE` x59, `Op-MSEDGE.EXE` x387,
  `GOOGLEDRIVEFS.EXE` (multiple hashes, 22/17/12/10 runs), `GOOGLEUPDATE.EXE` x59, `OUTLOOK.EXE` x8,
  `POWERPNT.EXE` x6 (loads `WOLVES_LAIR_TECH_SPECS.PPTX` and other SRL decks), `VSSADMIN.EXE` x3,
  `VSSVC.EXE` x8, `WEVTUTIL.EXE` x4, `CMD.EXE` x4, `REGEDIT.EXE` x1, `REGSVR32.EXE` x6, `FTK_IMAGER.EXE`
  x1, `ZOOM.EXE` x4, `AU_.EXE` (Dropbox installer). `NOTEPAD.EXE` prefetch references **removable
  volumes** including `MY DRIVE\KEY`. One artifact (`WMIPRVSE.EXE-E8B8DD29.pf`) failed to parse
  (`TOOL-050`, `parse_error`) and is labelled "verify."
- **LNK / JumpLists (`parse_lnk_jumplists`, 137 artifacts):** the F: and G: staging story above, the PST
  exports, the BitLocker recovery keys, the SRL project files, plus a Remote Desktop (`mstsc.exe`)
  JumpList to `base-rd-08.shieldbase.lan` and personal photo/iCloud targets.
- **Browser history (`parse_browser_history`, Chrome `fredr`):** the two Backup-and-Sync installer
  downloads, repeated Google Drive access (2020-10-31 to 2020-11-11), webmail **fred.rocba@gmail.com**,
  and Chrome account sync sign-in.
- **Removable media (`parse_usb_registry`):** 8 USBSTOR devices (SYSTEM hive) + 20 MountPoints2 entries
  (fredr NTUSER); `srl-h` had zero device entries.
- **RecentDocs (`parse_recentdocs_mru`):** 233 entries for `fredr` (SRL project docs, co-workers'
  research files, the PST exports); 18 for `srl-h` (a BitLocker recovery-key `.TXT`, `USB Drive (D:)`).
- **Shellbags (`parse_shellbags`):** `srl-h` BagMRU records browsing of `D:\` ("New World", "Build"),
  the Prefetch directory, `Pictures\Screenshots`, and `Users\rsydow\Documents\SRL Admin\Workstation-Prep`.
- **Program presence (`parse_amcache_shimcache`):** 517 Amcache entries, each with a SHA-1 and a
  first-run UTC timestamp, spanning 2020-10-21 to 2020-11-14 (0 ShimCache entries on this hive).
- **Persistence (`extract_registry_run_keys`):** SOFTWARE -> `SecurityHealth`; `fredr` -> 5 per-user
  autostart entries (OneDrive, GoogleDriveFS, ...); `srl-h` -> 3 (OneDriveSetup, OneDrive, WAB Migrate);
  SYSTEM -> 0.
- **PowerShell (`parse_evtx_powershell`, host `SRL-FORGE`):** exactly 2 EventID 4104 script-block events
  (2020-11-02T13:08:46Z and 2020-11-10T12:11:04Z), both the Microsoft-shipped `CL_Utility.ps1`
  diagnostics utility - **benign**, and the agent correctly characterized it rather than over-claiming.

## Memory - runtime state (Volatility 3, deterministic floor)

Anchored to `Rocba-Memory.raw` (sha256 `eb33bdf6…`): **2,186 processes; 430 network endpoints.** The
agent flagged `malfind` RWX regions in **system** processes (MsMpEng, SearchApp, dllhost, Teams,
smartscreen, LockApp, RuntimeBroker). These are **review-only leads, not asserted as malware** - and the
critic actively pushed back: duplicated SearchApp (PID 8312/19436) claims tripped the contradiction rule
(5 contradictions) and were confidence-downgraded (0.50 -> 0.25).

## Self-correction

The governance acted against the live agent's output:

- The agent **could not anchor the high-volume parses.** `$MFT` and USN-journal tasks
  (TASK-016/017/019) returned no parseable anchored claims on attempt 1; the critic forced a retry with
  tightened criteria; attempt 2 still failed; the tasks were escalated and **quarantined**. So
  `parse_mft_filesystem` (22 calls) and `parse_usnjrnl` (15 calls) executed but produced no promoted
  findings; the system did not emit unsupported claims.
- The memory injected-code over-claims were **downgraded and contradicted** (above).
- 3 prompt-injection consequences routed `TASK-001` to human review.

This run therefore has no MFT/USN findings; the deterministic floor surfaces those mechanically.

## Caveats

- **`Security.evtx`** is not parsed - a genuine TSK LZNT1 decompression error on this image.
- **Super-timeline not run this pass** (the fast command omits `SIFTMESH_ENABLE_SUPER_TIMELINE`; Plaso is
  available behind that flag).
- **Injection scanner is noisy:** of 11,628 logged alerts, 11,625 are base64-like hash fragments
  over-flagged by the `base64_blob` signature - fail-safe (over- not under-flag), never executed.
- This is an **automated triage** - analyst-grade leads with full provenance, **not** a court conclusion.

## Provenance & integrity

- Evidence opened read-only; SHA-256 sealed at ingest (chain of custody) - see
  [`evidence_integrity.md`](https://github.com/aryanbuilds/Project_SIFTMESH/blob/mvp_phase_1/docs/evidence_integrity.md) and [`dataset_documentation.md`](https://github.com/aryanbuilds/Project_SIFTMESH/blob/mvp_phase_1/docs/dataset_documentation.md).
- Every claim cites `tool_call_id` + `source_sha256`; unsupported claims are excluded from the findings
  (Appendix B of the run's `reports/final_report.md`).
- The full ledgers + `replay.html` are committed under
  [`logs/rocba-live-RUN-20260615-064002/`](https://github.com/aryanbuilds/Project_SIFTMESH/tree/mvp_phase_1/docs/logs/rocba-live-RUN-20260615-064002). Reproduce: see
  [`complete_operation.md`](https://github.com/aryanbuilds/Project_SIFTMESH/blob/mvp_phase_1/docs/complete_operation.md).

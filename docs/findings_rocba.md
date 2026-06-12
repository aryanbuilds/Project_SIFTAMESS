# ROCBA — Findings (real run)

Real output from running SIFTMesh against the provided ROCBA dataset on the SANS SIFT workstation.
Every finding below is anchored to a real tool call + the SHA-256 of its source artifact (chain of
custody). This is an **automated triage to guide an analyst — not a court-ready conclusion.**

| | |
|---|---|
| Disk run | `RUN-20260612-082004` — `rocba-cdrive.e01` · sha256 `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67` (23,678,691,658 B) |
| Memory run | `RUN-20260612-082630` — `Rocba-Memory.zip` → `Rocba-Memory.raw` · sha256 `eb33bdf63730858a805463d171245b233335dd6d89ed458bc681f7d282e10563` (19,050,528,768 B) |
| Tools | Sleuth Kit (extraction) · `parse_evtx_powershell` · `extract_registry_run_keys` · `analyze_prefetch` · Volatility 3 (`windows.info/pslist/pstree/netscan/cmdline/malfind`) |
| Critic | Tier-1 deterministic: **416 claims promoted, 0 unsupported, 0 contradictions** (disk run) |

## Objective (from the incident brief)

`ROCBA-BACKGROUND.pptx`, ingested as the trusted objective: *Fred Rocba and Stark Research Labs (SRL)
— victim of a break-in and IP theft; Fred is on vacation, pictures synced to his home system.*

## Disk image — host artifacts (Sleuth Kit + typed parsers)

- **Persistence (registry Run/RunOnce, `extract_registry_run_keys`, SOFTWARE/user hives):**
  cloud-sync autostarts `GoogleDriveFS`, `GoogleDriveSync`, `OneDrive`, `OneDriveSetup`,
  `com.squirrel.Teams.Teams`; system `SecurityHealth`; `WAB Migrate` (RunOnce); and an unusual
  GUID-named key `C18E42C7363A0E298C5594A2ABE53A0760B71220._service_run` — worth manual review.
- **Execution history (`analyze_prefetch`, 211 prefetch files):** AcroRd32 (9 runs), AdobeARM (12),
  Slack (3), SmartScreen (55), MicrosoftEdgeUpdate (42), etc. — each with run count + source `.pf`.
- **PowerShell (`parse_evtx_powershell`):** 2× EventID **4104** (script-block logging) recorded.
- **Honest gap:** `Security.evtx` failed extraction — a genuine TSK LZNT1 decompression error on this
  image (recorded in `failed[]`, **not** fabricated). 67 evidence strings that looked like
  instructions were flagged as prompt-injection and logged, never executed.

## Memory — runtime state (Volatility 3, all 6 plugins, 0 failed)

Anchored to `TOOL-001` over `Rocba-Memory.raw` (sha256 `eb33bdf6…`). 2,186 processes; 430 network
endpoints.

- **Data-egress channels (relevant to the IP-theft / "synced to home" objective):** established/closing
  connections from `iCloudPhotos.exe`, `iCloudDrive.exe`, `iCloudServices`, `APSDaemon.exe` → Apple
  (`17.248.138.x`, `17.57.144.165`), plus `OneDrive.exe` and `Teams.exe` cloud endpoints — consistent
  with cloud-sync exfiltration paths.
- **Unusual externals for review:** `svchost.exe` → `81.30.144.115:56687` and `213.202.233.104:13939`
  (non-standard high ports) — flag for analyst follow-up.
- **`malfind` (16 RWX regions):** predominantly in **system processes** (`MsMpEng.exe`=Defender,
  `SearchApp.exe`, `dllhost.exe`, `RuntimeBroker`, `smartscreen.exe`, `Teams.exe`) — typical malfind
  noise, **flagged for manual review, not asserted as malicious.**

## Answer to the objective (triage)

The triage surfaces the host's **cloud-sync data-egress channels** (iCloud, OneDrive, Google Drive)
that an analyst would examine first for the alleged IP theft / "pictures synced to home" scenario,
alongside autostart persistence (including one unusual GUID service key) and an execution timeline.
No single artifact *proves* exfiltration; these are the evidence-anchored leads SIFTMesh produced
autonomously for a human examiner to confirm. **This is investigative triage, not a legal conclusion.**

## Provenance & integrity

- Evidence opened read-only; SHA-256 sealed at ingest (chain of custody) — see
  [`evidence_integrity.md`](evidence_integrity.md) and [`dataset_documentation.md`](dataset_documentation.md).
- Every claim cites `tool_call_id` + `source_sha256`; unsupported claims are firewalled out of the
  findings (Appendix B of the run's `reports/final_report.md`).
- Reproduce: see [`dataset_documentation.md`](dataset_documentation.md). The full ledgers + replay
  live in the run dirs (`case_disk/…`, `case_mem/…`), uncommitted per CLAUDE.md §2B.

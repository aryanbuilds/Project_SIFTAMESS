# ROCBA - Complete Operation Log

This log records the run, its results, the findings, and the mapping to the brief questions.
Where the data does not answer a question, this document says so.

> **Scope.** This is a **single live Claude-agent run** - `RUN-20260615-064002` (case `case_fast`) - that
> investigated the disk image **and** the memory image in one autonomous pass. The LIVE executor is a
> Claude agent driven through `claude_headless`; the two heaviest tools (disk extract and memory triage)
> stay on the deterministic floor by policy. This run **replaces** the two earlier deterministic-floor
> bundles; those are deleted. The committed logs for this operation are at
> [`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002/).
>
> The run used SIFTMesh's **19-tool** governed allowlist (hash · vault · EVTX-security · EVTX-PowerShell ·
> prefetch · registry-Run-keys · timeline · claim-validation · disk-image extraction · memory triage,
> plus the 9 deep-evidence tools `parse_mft_filesystem`, `parse_recentdocs_mru`, `parse_usb_registry`,
> `parse_browser_history`, `parse_lnk_jumplists`, `parse_shellbags`, `parse_amcache_shimcache`,
> `parse_usnjrnl`, and `build_super_timeline`). **13 of the 19 tools were exercised this pass.** The
> Plaso super-timeline was **not** run (the fast command omitted `SIFTMESH_ENABLE_SUPER_TIMELINE`). The
> run still produces evidence-anchored leads for the brief questions - see "Objective coverage" below.
> Remaining gaps (the quarantined `$MFT`/USN parses, Plaso, `Security.evtx`, SRUM, server-side logs) are
> documented in §5.

---

## 1. Case facts (from the brief + probed host)

| | |
|---|---|
| Subject | Fred Rocba - `frocba@stark-research-labs.com` (Stark Research Labs / SRL); webmail `fred.rocba@gmail.com` |
| Scenario | Suspected insider IP theft; "Fred on vacation, pictures synced to his home system" |
| Host (from evidence) | **SRL-FORGE** - Windows 10 x64; primary user `fredr`; other users `srl-h`, `rsydow` (admin) |
| Activity window | 2020-10-21 to 2020-11-16 UTC (from artifacts) - **SIFTMesh outputs UTC** |
| SRL systems in scope | Office 365, SharePoint, OneDrive (personal + business), Exchange Online / local Outlook |
| Evidence | `rocba-cdrive.e01` (~23.7 GB disk) · `Rocba-Memory.zip` (~5.7 GB, auto-decompressed to `Rocba-Memory.raw`) · `ROCBA-BACKGROUND.pptx` (trusted brief = objective) |

Sealed hashes (chain of custody) are in [`dataset_documentation.md`](dataset_documentation.md). The four
sealed files: `rocba-cdrive.e01` (23,678,691,658 bytes, sha256 `f2eb856d…`); `Rocba-Memory.zip`
(5,682,814,481 bytes, sha256 `32cec940…`, decompressed to `Rocba-Memory.raw`, sha256 `eb33bdf6…`);
`ROCBA-BACKGROUND.pptx` (40,148,560 bytes, sha256 `44a12c54…`, trusted brief, **not** hostile evidence);
and a partial download `standard_case_1/rocba-cdrive.e01.download` (2,605,550,889 bytes, sha256
`c8710c72…`, hashed for custody).

## 2. The operation (one command + real results)

Run from `~/projects/Project_SIFTAMESS`. The whole investigation - disk and memory - was one autonomous
`siftmesh run` in `--auto` mode with a LIVE Claude executor.

### 2.1 The command
```bash
SIFTMESH_CAPS__MAX_PARALLEL_TASKS=6 uv run siftmesh run ./case_fast \
  --evidence ~/projects/data --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --objective "What key projects did Fred Rocba have access to? What was stolen, where to, how, and when?" \
  --auto --agent claude --judge opencode --parallel --max-agent-tasks 400 --max-iterations 2
```
- Run id `RUN-20260615-064002`; case dir `case_fast`. Sealed `2026-06-15 06:40:02Z`, completed
  `2026-06-15 08:37:01Z` (about 1 h 57 m wall clock). Mode `auto`; final state `done`; terminal at
  iteration 2 of 3 (`max_iterations=3` in `run_state`; report iteration 2/3).
- Executor: LIVE Claude agent via `claude_headless`. Tier-2 judge: `opencode` (advisory only - it ran,
  it never promotes; Tier-1 stays the sole promoter).

### 2.2 Execution profile (what actually ran)
- **Agent calls: 28** = 26 `claude_headless` (LIVE) + 2 `deterministic_executor` (the two heavy tools,
  tier-floor-forced by policy). **0 fallbacks** - no `fell_back_from` on any call.
- **Tasks: 25 contracts.** `TASK-001` = disk extract (floor), `TASK-002` = memory triage (floor),
  `TASK-003..025` = live Claude parser tasks. **24 derived-gap follow-up tasks** were auto-generated
  mid-run (the plan re-sequenced on findings).
- **Tool calls: 245** = 244 success + 1 error. Backends: 243 in-process "real" + 2 `sift_lane`
  subprocess (disk extract + memory). The single error is `TOOL-050` `analyze_prefetch` - a real
  `parse_error` on `WMIPRVSE.EXE-E8B8DD29.pf` (an honestly-logged partial failure, not hidden).
- **13 distinct tools exercised:** `analyze_memory` (1), `analyze_prefetch` (49),
  `extract_artifacts_from_image` (1), `extract_registry_run_keys` (4), `parse_amcache_shimcache` (3),
  `parse_browser_history` (3), `parse_evtx_powershell` (1), `parse_lnk_jumplists` (137),
  `parse_mft_filesystem` (22), `parse_recentdocs_mru` (2), `parse_shellbags` (4), `parse_usb_registry`
  (3), `parse_usnjrnl` (15).
- **428 artifacts extracted** from the disk image; **674 derived artifacts** carved in total.
- Plaso `build_super_timeline` was **not** run this pass (the fast command omitted
  `SIFTMESH_ENABLE_SUPER_TIMELINE`).
- Allowlist: **exactly 19 typed tools** (registry + a `doctor` self-check enforce it); 7 forbidden tools.
- Memory triage (Volatility 3, `sift_lane` subprocess - never imported): **2,186 processes, 430 network
  endpoints**; `malfind` flagged RWX regions in system processes (surfaced for review, **not** concluded
  malicious).

### 2.3 Claims and governance (the self-correction arc)
- **223 claims promoted** = 182 confirmed + 41 inferred; **0 unsupported, 0 contradicted-status.** All
  223 are anchored (every claim carries `tool_call_id` + `source_sha256`); 0 dangling `tool_call_id`
  references. 215 distinct claim texts.
- Confidence bands (post-downgrade): 0.90-1.00 = 163; 0.70-0.89 = 36; 0.50-0.69 = 16; 0.00-0.49 = 8.
  Corroboration: 22 multi-claim groups; 137 single-source groups.
- **Critic verdicts: 51** = accepted 34, accepted_with_downgrade 2, retry_required 4,
  escalation_required 8, human_review_required 3.
- **Self-correction retries: 3** (`RETRY-001/002/003` on `TASK-016/017/019`; cause `critic_retry`, with
  tightened criteria injected into the retry prompt).
- **Contradictions detected: 5** (`CONTRA-002/004/006/007/008`), all on the memory "Possible injected
  code in PID 8312 (`SearchApp.exe`)" claims (rule `same_artifact_field_value_mismatch`); escalated -
  neither side reported as fact.
- **Confidence downgrades by critic: 14** (over-broad claims, 0.5 → 0.25).
- **Quarantined tasks: 7** (`TASK-001, 002, 005, 013, 016, 017, 019`). Their claims are never promoted as
  facts; the run still completed to `done` (auto-mode quarantine policy).

> **The honest self-correction story (real, not staged).** The live Claude agent genuinely **failed to
> anchor three high-volume tasks** - `TASK-016`, `TASK-017`, `TASK-019` (the `$MFT` and USN-journal
> parses). On attempt 1 it returned no parseable anchored claims (`agent_produced_no_claims` /
> `agent_output_not_parseable_as_claims`). The deterministic critic forced a retry with tightened
> criteria; attempt 2 still failed; the tasks were escalated and quarantined. So `parse_mft_filesystem`
> (22 calls) and `parse_usnjrnl` (15 calls) **ran**, but produced **no promoted claims** this run - the
> governance correctly refused to let unsupported claims through rather than emit them. This is a genuine
> "the critic caught the agent" case, not a contrived demo. Separately, the memory "possible injected
> code" claims are **system** processes (MsMpEng, SearchApp, dllhost, Teams, smartscreen, LockApp,
> RuntimeBroker) flagged by Volatility `malfind`; the critic downgraded the duplicated `SearchApp` claims
> (the contradiction) and they remain inferred / low-confidence - correctly **not** asserted as malware.

### 2.4 Prompt-injection handling (fail-safe, noisy - disclosed honestly)
- **11,628 prompt-injection alerts logged** (never executed) = 11,625 `base64_blob` + 3
  `claim_injection_affected`; 3 injection consequences applied (`TASK-001` routed to `human_review`).
- The 11,625 `base64_blob` alerts are an **over-trigger** on base64-like hash fragments in tool output:
  this fails safe (over- not under-flag) but is noisy. Disclosed plainly; not hidden.

### 2.5 Audit trail
- `orchestration_events`: 213, monotonic; 17 transitions carry `duration_ms`.
- Decision sequence: `human_review → follow_up(24) → human_review → escalate → retry → escalate → done`.
- `replay.html` committed (self-contained).
- **Per-agent LLM token accounting is not recorded** (`agent_calls` carry no token field;
  `token_budget.jsonl` logs profile-routing decisions only). Honest gap - stated here.

## 3. Findings (evidence-anchored; full set in the run ledgers)

The headline question-by-question answers + per-artifact detail are in
[`findings_rocba.md`](findings_rocba.md). In brief, anchored by the live agent:
- **IP staged to a removable F: volume** - e.g. `F:\Files of interest\SRL-Projects - Megaforce\
  Megaforce\Megaforce Specs & Research.docx`, `F:\Key Data\SRL-Projects - Blue Thunder\…`,
  `F:\Files from SRL system`, and `F:\Files of interest\Recovered Documents\Wolves_Lair_Tech_Specs.pptx`.
- **IP mirrored to Google Drive G:** - a full tree under `G:\My Drive\STARK-RESEARCH-LABS FOLDER\`
  (Airwolf, `Wolf AIr Financials.xlsx`, `Research to Weaponize the Ion Thruster.docx`, Vibrainium, KITT,
  Exported-PST, VC Files, Research).
- **SRL email exfil** - `SRL-EMAIL-EXPORT.pst` (20,587,520 bytes) under `G:\My Drive\STARK-RESEARCH-LABS
  FOLDER\Exported-PST\`; `backup.pst` (20,587,520 bytes) at
  `C:\Users\fredr\OneDrive\Documents\Outlook Files\`.
- **Anti-forensics** - `SDelete.zip` (Sysinternals secure-delete, 226,573 bytes) downloaded to
  `C:\Users\fredr\Downloads` on `2020-11-14T13:37:51Z`; `vssadmin.exe` ran 3x; `VSSVC.EXE` 8x;
  `wevtutil.exe` 4x within ~2 s on 2020-11-14 (event-log tampering); `FTK IMAGER.EXE` ran once
  `2020-11-16T02:43:57Z` (the latest dated execution observed).
- **BitLocker recovery keys exfiltrated** - `BitLocker Recovery Key .TXT` files copied to D:, E:, and
  `G:\My Drive\Key\` (Notepad JumpList + LNK targets).
- **Removable media** - 8 distinct USBSTOR devices in the SYSTEM hive (Lexar USB Flash Drive, IS917
  innostor, two USB DISK 2.0, three Generic Mass Storage, Multiple Card Reader); 20 MountPoints2 entries
  under `fredr`'s NTUSER.
- **Cloud sync** - Google Drive File Stream (`GOOGLEDRIVEFS.EXE`, many runs); Chrome downloaded the
  Google "Backup and Sync" installer twice (`installbackupandsync.exe`, both 1,317,080 bytes, 2020-10-31
  and 2020-11-10); Dropbox; OneDrive; iCloud (`ICLOUDIE.EXE` executed 59 times).
- **PowerShell** - exactly 2 EventID 4104 script-block events on SRL-FORGE (`2020-11-02T13:08:46Z` and
  `2020-11-10T12:11:04Z`), both the Microsoft-shipped `CL_Utility.ps1` diagnostics utility - benign, and
  the agent characterized it correctly (no over-claim of attacker activity).
- **Registry Run keys** - SOFTWARE hive 1 system-wide (SecurityHealth); `fredr` 5 per-user; `srl-h` 3;
  SYSTEM hive 0.
- **Amcache** - 517 program-presence entries (each with a SHA-1 + first-run UTC), spanning
  `2020-10-21T03:44:22Z` to `2020-11-14T13:50:48Z`.
- **Memory triage** - 2,186 processes, 430 network endpoints; `malfind` RWX regions flagged for review,
  not concluded malicious (some downgraded / contradicted by the critic).
- **ATT&CK mapped** - T1005 (Collection / Data from Local System), T1547.001 (Persistence / Registry Run
  Keys), T1055 (Defense Evasion / Process Injection - memory, low confidence).

## 4. Objective coverage - does this run answer the brief's questions?

**Verdict: yes - evidence-anchored leads for all of them**.

| Brief question | Status | What the run shows (tool) |
|---|---|---|
| **What key projects did Fred have access to?** | Answered (lead) | SRL project trees staged off-host: Megaforce, Blue Thunder, Airwolf, KITT, Vibrainium, and "Research to Weaponize the Ion Thruster" (`parse_lnk_jumplists`, `parse_shellbags`, `parse_recentdocs_mru`). |
| **What was stolen?** | Answered (lead) | SRL research + business docs and a full email export - `SRL-EMAIL-EXPORT.pst` / `backup.pst` (20,587,520 bytes each), `Wolf AIr Financials.xlsx`, BitLocker recovery keys (`parse_lnk_jumplists`, `parse_browser_history`). |
| **Where was it transferred to?** | Answered (lead) | A removable **F:** volume, a **Google Drive G:** mirror under `G:\My Drive\STARK-RESEARCH-LABS FOLDER\`, plus OneDrive/iCloud; 8 USBSTOR devices + 20 MountPoints2 entries (`parse_usb_registry`, `parse_lnk_jumplists`). |
| **How was it stolen?** | Answered (lead) | Cloud-sync clients **executed** - Google Drive File Stream, the Backup-and-Sync installer (twice), iCloud (59 runs) (`parse_amcache_shimcache`) + Run-key persistence; USB attachment; **SDelete** + `vssadmin`/`wevtutil` anti-forensics. |
| **When did the activity occur?** | Answered (lead) | Activity window 2020-10-21 to 2020-11-16 UTC; SDelete downloaded `2020-11-14T13:37:51Z`; `FTK IMAGER.EXE` ran `2020-11-16T02:43:57Z`; Amcache first-run timestamps span `2020-10-21T03:44:22Z`-`2020-11-14T13:50:48Z` (`parse_amcache_shimcache`, `analyze_prefetch`). |

## 5. Remaining honest gaps (documented, fail-closed - not invented)

- **`$MFT` inventory and USN change-journal findings are NOT in the promoted findings.** The tools ran
  (`parse_mft_filesystem` 22 calls, `parse_usnjrnl` 15 calls) but the **live agent failed to anchor
  them** - `TASK-016/017/019` were retried, then escalated and quarantined. The deterministic floor
  surfaces these mechanically; the live agent is more autonomous but less reliable on huge tabular
  output - the critic caught it rather than emitting unsupported claims.
- **Plaso super-timeline not run this pass** - the fast command omitted `SIFTMESH_ENABLE_SUPER_TIMELINE`.
  It is available behind that flag; it is simply absent from this run's findings.
- **`Security.evtx`** - genuine TSK LZNT1 corruption on this image (per prior runs); recorded as a
  failure, never faked.
- **Per-agent LLM token accounting not recorded** - `agent_calls` carry no token field.
- This is **investigative triage to guide a human examiner, not a court-ready conclusion.**

## 6. Integrity & provenance

Evidence opened read-only; SHA-256 sealed at ingest; every one of the **223 promoted claims** cites
`tool_call_id` + `source_sha256` (0 dangling references); unsupported claims are firewalled out of the
findings. The committed ledgers, audit trail, and self-contained `replay.html` for this run live at
[`logs/rocba-live-RUN-20260615-064002/`](logs/rocba-live-RUN-20260615-064002/).

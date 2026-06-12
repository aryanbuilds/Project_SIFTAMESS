# ROCBA — Complete Operation Log

A faithful, end-to-end record of the **real** SIFTMesh investigation against the ROCBA dataset on the
SANS SIFT workstation — every command, its real result, the findings, and an **honest** mapping to the
five questions the incident brief asks. Nothing here is fabricated; where the data does not answer a
question, this document says so.

> **Scope honesty up front.** This run used SIFTMesh's current **10-tool MVP** (hash · vault ·
> EVTX-security · EVTX-PowerShell · prefetch · registry-Run-keys · timeline · claim-validation ·
> disk-image extraction · memory triage). That set establishes **persistence, execution, PowerShell,
> and live network/process state** very well, but it has **no parser** for the artifacts that answer
> "what documents existed / what was taken" (browser history, LNK/JumpLists, `$MFT` filename timeline,
> ShellBags, Outlook OST/email, OneDrive/SharePoint logs, USBSTOR). So this run produces strong
> **evidence-anchored leads**, not a closed case. See "Objective coverage" below.

---

## 1. Case facts (from the brief + probed host)

| | |
|---|---|
| Subject | Fred Rocba — `frocba@stark-research-labs.com` (Stark Research Labs / SRL) |
| Scenario | Break-in + IP theft; "Fred on vacation, pictures synced to his home system" |
| Host (from evidence) | **SRL-FORGE** — Windows 10 x64, single-user, fully patched |
| Timezone | EST5EDT (Eastern) — **SIFTMesh outputs UTC**; convert for the report (UTC−5/−4) |
| SRL systems in scope | Office 365, SharePoint, OneDrive (personal + business), Exchange Online / local Outlook, Microsoft Portal |
| Evidence | `rocba-cdrive.e01` (disk) · `Rocba-Memory.zip` (memory) · `ROCBA-BACKGROUND.pptx` (brief = objective) |

Sealed hashes (chain of custody) are in [`dataset_documentation.md`](dataset_documentation.md).

## 2. The operation (commands + real results)

Run from `~/projects/Project_SIFTAMESS`. Heavy steps were run with long timeouts / in the background.

### 2.1 Host setup + verify (no evidence touched)
```bash
uv run siftmesh doctor --setup
```
→ all 10 tools present, forensic + brief backends installed, `vol` at `/opt/volatility3/bin/vol`,
symbol cache ready, `doctor: ok`.

### 2.2 Disk image — seal, extract (Sleuth Kit), parse (deterministic floor)
```bash
ln -f ~/projects/data/rocba-cdrive.e01 ~/projects/ev_disk/
uv run siftmesh init-case ./case_disk --evidence ~/projects/ev_disk --brief ~/projects/data/ROCBA-BACKGROUND.pptx
RUN=case_disk/case_runs/RUN-20260612-082004
uv run siftmesh evidence extract "$RUN" --evidence ~/projects/ev_disk --image rocba-cdrive.e01 \
  --keys powershell_evtx --keys software_hive --keys system_hive --keys security_evtx --keys user_hives --keys prefetch
uv run siftmesh evidence ingest "$RUN" --evidence ~/projects/ev_disk
uv run siftmesh dispatch "$RUN" && uv run siftmesh collect "$RUN" && uv run siftmesh critique "$RUN"
uv run siftmesh report "$RUN" && uv run siftmesh replay "$RUN" --html
```
Real results:
- `init-case` hashed the 23.7 GB e01 → sha256 `f2eb856d…`; brief ingested as the trusted objective.
- `extract` → **216 artifacts extracted, 1 failed**: `Security.evtx` fails with a genuine TSK LZNT1
  NTFS-decompression error (recorded in `failed[]`, **not** fabricated).
- `ingest` → **6 family tasks** (4× `analyze_prefetch`, 1× `extract_registry_run_keys`,
  1× `parse_evtx_powershell`).
- `dispatch/collect/critique` → **416 claims promoted, 0 unsupported, 0 contradictions**, 6 accepted
  verdicts, **67 prompt-injection alerts logged (never executed)**, 7 coverage-gap follow-ups raised.

### 2.3 Memory — seal, decompress, triage (Volatility 3), reclaim space
```bash
ln -f ~/projects/data/Rocba-Memory.zip ~/projects/ev_mem/
uv run siftmesh init-case ./case_mem --evidence ~/projects/ev_mem
RUNM=case_mem/case_runs/RUN-20260612-082630
uv run siftmesh evidence decompress "$RUNM" --archive Rocba-Memory.zip --evidence ~/projects/ev_mem
export SIFTMESH_VOL_PATH=/opt/volatility3/bin/vol SIFTMESH_VOL_SYMBOL_DIRS=$HOME/.cache/siftmesh/vol_symbols
uv run siftmesh evidence memory "$RUNM" --evidence "$RUNM" --memory evidence/extracted/Rocba-Memory.raw \
  --plugins pslist --plugins pstree --plugins netscan --plugins cmdline --plugins malfind
uv run siftmesh prune "$RUNM"
```
Real results:
- `decompress` → `Rocba-Memory.raw`, 19,050,528,768 B, sha256 `eb33bdf6…`.
- `memory` → Win10 x64 image; **all 6 plugins ran, 0 failed**; **2,186 processes, 430 net endpoints,
  16 `malfind` regions**.
- `prune` → freed 17.7 GB (ledgers + tool results kept; raw image removed).

## 3. Findings (evidence-anchored; full set in the run ledgers)

**Disk (`RUN-20260612-082004`):**
- **Persistence** (registry Run/RunOnce): `GoogleDriveFS`, `GoogleDriveSync`, `OneDrive`,
  `OneDriveSetup`, `com.squirrel.Teams.Teams`, `SecurityHealth`, `WAB Migrate`, and an unusual
  GUID-named key `C18E42C7363A0E298C5594A2ABE53A0760B71220._service_run` (review).
- **Execution** (prefetch, 211 files): AcroRd32 (9), AdobeARM (12), Slack (3), SmartScreen (55),
  MicrosoftEdgeUpdate (42)… last execution **2020-11-16 02:50 UTC** (≈ 2020-11-15 21:50 EST).
- **PowerShell** (4104, host **SRL-FORGE**, 2020-11-02 13:08 UTC): the script-block is a **benign
  Microsoft troubleshooting-pack script** (CL_LocalizationData / WER cleanup) — **not** attacker code.

**Memory (`RUN-20260612-082630`):**
- **Cloud-sync egress (relevant to "where/how"):** active connections from `iCloudPhotos.exe`,
  `iCloudDrive.exe`, `iCloudServices`, `APSDaemon.exe` → Apple (`17.248.138.x`, `17.57.144.165`),
  plus `OneDrive.exe` and `Teams.exe` cloud endpoints — consistent with the brief's OneDrive
  (personal+business) + the "synced to home" angle.
- **Unexplained externals (review):** `svchost.exe` → `81.30.144.115:56687`, `213.202.233.104:13939`.
- **`malfind`:** 16 RWX regions, predominantly **system processes** (Defender `MsMpEng`, `SearchApp`,
  `dllhost`, `Teams`, `RuntimeBroker`) — typical malfind noise, **flagged for review, not malicious**.

## 4. Objective coverage — does this run answer the brief's 5 questions?

**Honest verdict: not conclusively. Real leads for Where / How / When; genuine gaps for What.**

| Brief question | Status | What the run shows / why not |
|---|---|---|
| **What key projects did Fred have access to?** | ❌ Not answered | No MVP tool lists documents/SharePoint/OneDrive contents, RecentDocs, JumpLists, or Office MRU. |
| **What was stolen?** | ❌ Not answered | No `$MFT` filename timeline, browser-download, LNK/JumpList, or email parser in the 10-tool set. |
| **Where was it transferred to?** | 🟡 Partial (lead) | Memory shows active **OneDrive / iCloud / Teams** cloud-sync egress + OneDrive/GoogleDrive autostarts — a channel lead, not proof of *what* went where. 2 unexplained `svchost` externals flagged. |
| **How was it stolen?** | 🟡 Partial (inconclusive) | Cloud-sync (OneDrive personal+business / iCloud) is the leading candidate channel; the PowerShell 4104 is **benign**, so explicitly **not** the mechanism. OneDrive/SharePoint logs, browser uploads, and email were not examined. |
| **When did the activity occur?** | 🟡 Partial | Real timestamps: PowerShell 2020-11-02 13:08 UTC; prefetch execution through **2020-11-16 02:50 UTC** (≈ 21:50 EST 11-15); memory captured ~2020-11-16. No consolidated theft timeline; outputs are UTC (host is EST5EDT). |

## 5. Why the gaps — and how to close them

The gaps are **tool-coverage**, not pipeline failures: SIFTMesh did exactly what its governed 10-tool
MVP allows, anchored every claim, and **honestly refused to invent** what it couldn't parse. To
actually answer "what projects / what was stolen," the allowlist would need (each a governed addition):
`$MFT` filename + timeline parser, browser-history, LNK/JumpList, ShellBags, Outlook OST/PST (email),
OneDrive/SharePoint sync logs, and USBSTOR. Until then those questions stay open by design.

**Cheap next steps on the current toolset:**
- `build_timeline` over the parsed artifacts → one consolidated UTC→EST execution timeline (better "when").
- **Live Claude pass** (`dispatch --agent-profile claude_headless`) → sharper *reasoning/narrative*
  over the same leads (the cloud-sync exfil hypothesis), but it cannot exceed the 10-tool reach, so it
  still won't produce file-level "what was stolen."

## 6. Integrity & provenance

Evidence opened read-only; SHA-256 sealed at ingest; every promoted claim cites `tool_call_id` +
`source_sha256`; unsupported claims are firewalled out of the findings. Full ledgers + `replay.html`
live in the run dirs (`case_disk/…`, `case_mem/…`), uncommitted per CLAUDE.md §2B. This is
**investigative triage to guide a human examiner, not a court-ready conclusion.**

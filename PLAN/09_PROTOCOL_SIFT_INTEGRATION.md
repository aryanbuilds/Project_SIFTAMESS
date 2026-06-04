# PLAN 09 — Protocol SIFT Integration (inspect & govern, don't black-box)

_Authored 2026-06-04. **Authoritative for how SIFTMesh detects, inspects, and orchestrates Protocol SIFT.** Confirmed from the real `teamdfir/protocol-sift` repo (`install.sh`, `global/`, `skills/`) + the SANS blog. Re-confirm exact paths/versions on the live SANS SIFT VM at implementation time. Sources are listed at the bottom; do not add unsourced claims._

## 0. The one finding that changes our positioning

**Protocol SIFT is NOT an MCP server.** It is a **Claude Code configuration + skill library + permission framework** that `install.sh` copies into the user's `~/.claude/` directory (it also installs Claude Code itself if missing). So SIFTMesh must **inspect and govern** this layer — not treat Protocol SIFT as an opaque box. This is a differentiator: most hackathon teams will *use* Protocol SIFT; SIFTMesh becomes a **Protocol SIFT readiness + control layer** that knows the actual environment.

SANS framing (quote): *"Under this protocol, AI acts strictly as a constrained workflow assistant… deterministic DFIR utilities remain the sole source of analytical output… human oversight remains central to interpretation."* Protocol SIFT is explicitly **"not validated for forensic soundness… not court-admissible… initial research stage."** SIFTMesh adopts the same humility (explicit non-goal: not court-ready) and **strengthens** the informal model: Protocol SIFT enforces constraints via *prompts + a permission allowlist*; SIFTMesh enforces them **architecturally** (typed tools, claim ledger, deterministic critic, custody log).

## 1. The real `~/.claude/` layout (what `install.sh` creates)

```
~/.claude/
  CLAUDE.md            # global "Principal DFIR Orchestrator" rules; evidence mode = strict read-only;
                       #   UTC; "verify tool success after every run; on failure: read stderr ->
                       #   hypothesize -> correct -> retry" (their informal self-correction)
  settings.json        # permission framework: ALLOW ~200+ forensic CLIs (log2timeline.py, psort.py,
                       #   fls/icat/mactime, vol.py, dotnet EZ Tools, bulk_extractor, yara, tshark, ...);
                       #   DENY rm -rf / dd / wget / curl / ssh / WebFetch; Read deny ./secrets|*.key|*.pem;
                       #   hooks.Stop -> append summary to ./analysis/forensic_audit.log
  settings.local.json  # machine-local overrides (sudo apt, ~/.local/bin/claude, psort.py)
  skills/
    memory-analysis/SKILL.md     # Volatility 3 + Memory Baseliner
    plaso-timeline/SKILL.md      # log2timeline.py / psort.py / pinfo.py / image_export.py
    sleuthkit/SKILL.md           # TSK (fls/icat/ils/mactime/tsk_recover) + EWF mounting + carving
    windows-artifacts/SKILL.md   # EZ Tools: MFTECmd/EvtxECmd/RECmd/PECmd/Amcache/AppCompat/SRUM/...
    yara-hunting/SKILL.md        # YARA + Velociraptor
  case-templates/CLAUDE.md       # per-case template (evidence inventory, threat-actor context, paths)
  analysis-scripts/generate_pdf_report.py   # WeasyPrint HTML -> PDF report
```

**Expected tool paths (SANS SIFT host):** Volatility 3 = `python3 /opt/volatility3-2.20.0/vol.py` (NOT `/usr/local/bin/vol.py`, which is Vol2); EZ Tools = `dotnet /opt/zimmermantools/<Tool>.dll` (dotnet 6.0.x); YARA = `/usr/local/bin/yara`; Plaso/TSK/bulk_extractor on system PATH.

## 2. `siftmesh protocol-sift inspect` — detection checklist (read-only, env-only)

This needs **no forensic evidence** and is buildable/demoable early — a safe differentiator. It writes a validated capability map under the run dir (via path policy). Checks:

| Check | Path / probe | Tells us |
|---|---|---|
| Claude Code | `command -v claude` / `~/.local/bin/claude` | agent host available |
| Protocol SIFT core | `~/.claude/CLAUDE.md` contains "Principal DFIR Orchestrator" | Protocol SIFT installed |
| Permission posture | `~/.claude/settings.json` allow/deny + `hooks.Stop` audit hook | their constraint + audit model |
| Skills present | `~/.claude/skills/{memory-analysis,plaso-timeline,sleuthkit,windows-artifacts,yara-hunting}/SKILL.md` | which domains are available |
| Case template | `~/.claude/case-templates/CLAUDE.md` | per-case scaffolding present |
| Analysis scripts | `~/.claude/analysis-scripts/generate_pdf_report.py` | PDF reporting present |
| Volatility 3 | `/opt/volatility3-2.20.0/vol.py` | memory analysis available |
| EZ Tools | `/opt/zimmermantools/` (dir + `.dll`s) | Windows-artifact parsing |
| Plaso | `log2timeline.py` / `psort.py` | super-timeline available |
| SleuthKit | `fls`,`icat`,`tsk_recover` | filesystem forensics |
| YARA | `/usr/local/bin/yara` | threat hunting |
| WeasyPrint | `python3 -c "import weasyprint"` | PDF reporting dependency |

Commands: `siftmesh doctor --protocol-sift` (summary, fail-closed for SIFTMesh's own backends), `siftmesh protocol-sift inspect` (full capability map → `context/protocol_sift_capabilities.json`), `siftmesh protocol-sift skills list`. (`case-template import` is a deeper, optional follow-on — not MVP.)

## 3. SIFT-lane mapping (SiftLaneBackend → Protocol SIFT skill + tool path)

The optional, gated `SiftLaneBackend` (PLAN/03 D3) orchestrates Protocol SIFT's real tools behind SIFTMesh's identical typed interface, via fixed-argv `subprocess.run(shell=False)` on the SIFT host:

| SIFTMesh tool | Protocol SIFT skill | Real tool / path (SIFT host) |
|---|---|---|
| `parse_evtx_security` / `_powershell` | windows-artifacts | EvtxECmd: `dotnet /opt/zimmermantools/EvtxECmd.dll` |
| `analyze_prefetch` | windows-artifacts | PECmd: `dotnet /opt/zimmermantools/PECmd.dll` |
| `extract_registry_run_keys` | windows-artifacts | RECmd: `dotnet /opt/zimmermantools/RECmd.dll` |
| `build_timeline` | plaso-timeline | `log2timeline.py` + `psort.py` (super-timeline); MFTECmd for `$MFT` |
| (gap / future) memory | memory-analysis | `python3 /opt/volatility3-2.20.0/vol.py` (gated; VSL — subprocess only, never import) |
| (gap / future) filesystem/carving | sleuthkit | `fls`/`icat`/`mactime`/`tsk_recover` |
| (gap / future) hunting | yara-hunting | `/usr/local/bin/yara` |

**Note:** the **local real path stays the in-process Python libs** (PLAN/08 §3 — `evtx`/`regipy`/`pyscca`/`mft`); the SIFT-lane is the upgrade on the SANS host. Same typed interface, config flip.

## 4. MVP coverage vs. known gaps (honest scope)

- **MVP real coverage:** EVTX (Security + PowerShell), Prefetch, Registry Run/RunOnce, `$MFT`.
- **Known gaps (documented, not hidden):** Amcache, SRUDB, ShimCache/AppCompatCache, full Plaso super-timeline, memory forensics (Volatility 3). These are SIFT-lane / roadmap items, available on the SANS host but not part of the in-process MVP.

## 5. Integration principle (governance unchanged)

**Inspect and govern Protocol SIFT; never blindly depend on it.** SIFTMesh detects the environment, maps capabilities, and — when on a SIFT host — drives Protocol SIFT's real tools through the SIFT-lane. But every output still passes SIFTMesh's typed-tool boundary, claim ledger, deterministic critic, custody log, and path policy. Protocol SIFT's `settings.json` allowlist/deny + Stop-hook audit is the *prompt/permission* version of this; SIFTMesh enforces it in **code**. SIFTMesh **improves** Protocol SIFT's "verify → retry" loop into a typed, evidence-anchored, replayably-governed self-correction.

---

_Sources (re-confirm on the live SIFT VM): `https://raw.githubusercontent.com/teamdfir/protocol-sift/main/install.sh`; `.../global/CLAUDE.md`; `.../global/settings.json`; `.../global/settings.local.json`; `.../skills/{memory-analysis,plaso-timeline,sleuthkit,windows-artifacts,yara-hunting}/SKILL.md`; `.../case-templates/CLAUDE.md`; `.../analysis-scripts/generate_pdf_report.py`; SANS blog "Protocol SIFT: An Experimental Research Initiative for AI-Assisted DFIR" (sans.org); `findevil.devpost.com`._

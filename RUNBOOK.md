# SIFTMesh Runbook — testing on real evidence (ROCBA)

Line-by-line commands for driving SIFTMesh end-to-end against real DFIR evidence. Every command here
is **real** — real Sleuthkit, real Volatility 3, real deterministic critic, real live agent. Nothing
is mocked.

**Ground rule (CLAUDE.md §2B):** the maintainer runs these against real evidence; the tooling never
self-tests against forensic data. Run everything from the repo root:

```bash
cd ~/projects/Project_SIFTAMESS
```

All CLI commands are confirmed against `siftmesh … --help` and the current source.

---

## What the data is, and which tool handles it

| File (`~/projects/data/`) | Size | Tool path |
|---|---|---|
| `rocba-cdrive.e01` | 22.6 GB | disk image → `extract-artifacts` (Sleuthkit `mmls/ifind/icat/fls`) |
| `Rocba-Memory.zip` | 5.4 GB | memory, zipped → `decompress` → `analyze-memory` (Volatility 3, subprocess only). In `run --auto` this is **auto-decompressed + auto-ingested** (needs `7z`); staged, use §3 |
| `ROCBA-BACKGROUND.pptx` | 39 MB | **incident briefing = the TRUSTED objective** → pass with `--brief` so the agent investigates toward it (it is never fed to a forensic tool) |
| `standard_case_1/` | 2.6 GB | only a **partial** `rocba-cdrive.e01.download` — ignore it |

---

## 0 — Prove the host is ready (no evidence touched)

```bash
uv run siftmesh doctor
```

What matters:

- `[ ok ] gateway tool allowlist: 10 tools, no forbidden` — core is healthy.
- SIFT-lane lines for **Sleuthkit (mmls/ifind/icat/fls)**, **Volatility 3 (vol)**, **7z**. These are
  `[warn]` if absent (fine for `doctor`), but the tool **fails closed** when actually invoked. For the
  ROCBA disk + memory you need them present:
  - `which mmls ifind icat fls` (installed on SANS SIFT).
  - `which vol` — if it lives elsewhere: `export SIFTMESH_VOL_PATH=/opt/volatility3/bin/vol`.
  - `which 7z` (the memory zip wraps an inner archive).

Optionally inspect the Protocol SIFT layer: `uv run siftmesh doctor --protocol-sift`.

---

## 1 — (Optional) 60-second engine smoke, no keys, public fixtures

Confirms `init → plan → dispatch → collect → critique → report` works before spending time on 22 GB.

```bash
mkdir -p /tmp/smoke_ev
cp tests/fixtures/forensic/security_short.evtx /tmp/smoke_ev/Security.evtx
uv run siftmesh run ./case_smoke --evidence /tmp/smoke_ev --auto
```

Expect the run to reach `state: done`. This is the deterministic floor (real `evtx` parser, real
claims) — no agent, no keys.

---

## 2 — Disk image: real Sleuthkit extraction + orchestration

**2a. Curate a clean evidence dir** (hard-link = instant, same bytes; keeps the manifest focused and
avoids hashing the 2.6 GB partial in `standard_case_1/`):

```bash
mkdir -p ~/projects/ev_disk
ln ~/projects/data/rocba-cdrive.e01 ~/projects/ev_disk/ 2>/dev/null \
  || cp -n ~/projects/data/rocba-cdrive.e01 ~/projects/ev_disk/
```

**2b. Seal evidence** (hashes the 22.6 GB e01 once — expect ~1 min):

```bash
uv run siftmesh init-case ./case_disk --evidence ~/projects/ev_disk
RUN=$(ls -dt ./case_disk/case_runs/RUN-* | head -1); echo "RUN=$RUN"
```

Check: `cat "$RUN/evidence/evidence_manifest.json"` shows `rocba-cdrive.e01` with its SHA-256.

**2c. Extract Windows artifacts with real Sleuthkit** (writes to `$RUN/evidence/extracted/`, fully
audited; minutes on 22 GB, 1800 s timeout).

> **Scale note — extract a FOCUSED set.** Extracting *everything* (the default) pulls 200+ files
> (every prefetch `.pf` + every user hive). `ingest-derived` then makes **one task per file**, and the
> default cap is `max_agent_tasks=10` → `dispatch` would refuse. For a clean run, extract a few
> single-file, high-value keys (each becomes one task):

```bash
uv run siftmesh extract-artifacts "$RUN" --evidence ~/projects/ev_disk --image rocba-cdrive.e01 \
  --keys powershell_evtx --keys software_hive --keys system_hive --keys security_evtx
ls -la "$RUN/evidence/extracted/"
```

Curated keys: `security_evtx`, `powershell_evtx`, `system_evtx`, `software_hive`, `system_hive`,
`prefetch`, `user_hives`, `mft`. Missing artifacts are skipped; unreadable ones land in `failed[]`
(never fabricated — e.g. on the ROCBA e01, `security_evtx` fails with a real TSK NTFS-decompression
error and is honestly recorded, not faked). Omit `--keys` to take the full set, but then **raise the
cap**: `export SIFTMESH_CAPS__MAX_AGENT_TASKS=400`.

**2d. Make the extracted artifacts plannable, then run the deterministic pipeline over them.**
`ingest-derived` writes one task contract per extracted artifact **and** a minimal
`investigation_plan.yaml` (so `dispatch` works without a separate `plan` step — do **not** run `plan`
after a manual `extract-artifacts`, or it would create a fresh `extract_artifacts_from_image` task and
re-run the 22 GB extraction):

```bash
uv run siftmesh ingest-derived "$RUN" --evidence ~/projects/ev_disk
ls "$RUN/tasks/"                       # confirm the derived parse tasks were created
uv run siftmesh dispatch "$RUN"        # FULL set? prefix SIFTMESH_CAPS__MAX_AGENT_TASKS=400 (staged dispatch reads the env var; `run` takes --max-agent-tasks)
uv run siftmesh collect  "$RUN"
uv run siftmesh critique "$RUN"
uv run siftmesh report   "$RUN"
```

Note: only extracted artifacts that map to a typed tool get a task — PowerShell evtx →
`parse_evtx_powershell`, SOFTWARE/SYSTEM/user hives → `extract_registry_run_keys`, Prefetch →
`analyze_prefetch`, Security evtx → `parse_evtx_security`. `System.evtx` and `$MFT` have no dedicated
parser in the 10-tool allowlist and are reported as coverage gaps rather than parsed.

Inspect: `cat "$RUN/claims/claim_ledger.jsonl"` (evidence-anchored findings) and
`"$RUN/audit/critic_verdicts.jsonl"` (one verdict per task).

---

## 2′ — Full-auto in ONE command (the hackathon-demo shape)

A single `run --auto` drives the **whole** investigation itself: read the incident brief →
hash → **auto-decompress any archive (memory zip)** → plan → extract (Sleuthkit) → **auto re-ingest
the derived artifacts** (disk + memory) → parse (evtx/registry/prefetch/Volatility) → critique →
report — no staged commands. Put **everything** in one evidence dir and point `--brief` at the
incident document:

```bash
mkdir -p ~/projects/ev_all
ln ~/projects/data/rocba-cdrive.e01 ~/projects/ev_all/ 2>/dev/null || cp -n ~/projects/data/rocba-cdrive.e01 ~/projects/ev_all/
ln ~/projects/data/Rocba-Memory.zip ~/projects/ev_all/ 2>/dev/null || cp -n ~/projects/data/Rocba-Memory.zip ~/projects/ev_all/

uv run siftmesh run ./case_rocba --evidence ~/projects/ev_all \
  --brief ~/projects/data/ROCBA-BACKGROUND.pptx \
  --agent claude --auto --max-agent-tasks 400 --max-iterations 5
```

- **`--brief …pptx`** ingests the incident document as the **TRUSTED objective** (written to
  `context/incident_brief.md`, recorded as manifest metadata, never fed to a forensic tool). The
  objective is threaded into the case brief, the context pack, and **every agent prompt** — so the
  live agent investigates *toward* it, and `reports/final_report.md` gets an **"Answer to the incident
  objective"** section. (`.pptx`/`.docx` need `uv sync --extra brief`; `.txt`/`.md` need nothing.)
- **`--agent claude`** is the headline: a live, objective-driven investigation that self-corrects under
  the deterministic critic. Needs a logged-in `claude` CLI (consumes your subscription). Omit it for
  the key-free deterministic floor — `run`/`doctor` print a hint when claude is available but not
  selected. The floor is the reliable baseline; run it first.
- **Archives are auto-handled:** `Rocba-Memory.zip` is decompressed at the start of the run and the
  raw image is auto-ingested into a `analyze-memory` task (needs `7z` + `vol`; missing → logged
  `archive_decompress_skipped`, run continues). No manual `decompress` / `ingest-derived` needed.
- **One flagged task no longer strands the run:** in `--auto`, a task the critic sends to
  human-review/escalation is **quarantined** (recorded + surfaced in the report; its claims never
  become facts) and the run completes to `done`. Use `--auto-human-loop` if you want it to **halt**
  for `approve`/`reject` instead. `--max-agent-tasks 400` lifts the default-10 cap explicitly (the cap
  stays enforced; without it the run halts with the exact number to pass).

> First real run? Prefer the **staged** §2 flow with `--keys` (fast, focused, proven). Use this
> one-command form once the staged path looks right, for the clean "supply evidence + brief →
> autonomous → report" demo.

---

## 3 — Memory: decompress + real Volatility 3

**3a. Curate + seal** (point evidence at the zip's dir):

```bash
mkdir -p ~/projects/ev_mem
ln ~/projects/data/Rocba-Memory.zip ~/projects/ev_mem/ 2>/dev/null \
  || cp -n ~/projects/data/Rocba-Memory.zip ~/projects/ev_mem/
uv run siftmesh init-case ./case_mem --evidence ~/projects/ev_mem
RUNM=$(ls -dt ./case_mem/case_runs/RUN-* | head -1); echo "RUNM=$RUNM"
```

**3b. Decompress** (zip → inner 7z → raw image, into `$RUNM/evidence/extracted/`; needs `7z`):

```bash
uv run siftmesh decompress "$RUNM" --archive Rocba-Memory.zip --evidence ~/projects/ev_mem
ls -la "$RUNM/evidence/extracted/"        # note the EXACT decompressed filename
MEM=$(ls "$RUNM/evidence/extracted/" | head -1); echo "MEM=$MEM"
```

**3c. (Recommended) point Volatility's symbol cache at a writable dir** — vol downloads Windows PDB
symbols (needs internet, or pre-cached):

```bash
mkdir -p /tmp/vol_symbols
export SIFTMESH_VOL_SYMBOL_DIRS=/tmp/vol_symbols
```

**3d. Analyze** — `--evidence` is the **RUN dir** here (the raw image lives under it):

```bash
uv run siftmesh analyze-memory "$RUNM" --evidence "$RUNM" --memory "evidence/extracted/$MEM"
```

Defaults run `windows.pslist`, `pstree`, `netscan`, `cmdline`, `malfind` (per-plugin 900 s;
`netscan`/`malfind` are slow on a big dump). `windows.info` gates the rest — if symbols don't resolve
it fails closed (no fake rows). Narrow with `--plugins pslist --plugins pstree` to start. The full raw
Volatility JSON is preserved in the tool-call audit; the typed summary is in the tool result.

---

## 4 — Live Claude self-correction (subscription or API)

The live agent works on the **extracted** artifacts from §2 (it calls the typed tools, not the raw
e01). Do §2a–2d first, reusing that `$RUN`.

**4a. Authenticate Claude's own CLI** (the subscription only ever drives the real `claude` binary; it
is never proxied to another client):

```bash
claude setup-token            # interactive → sets CLAUDE_CODE_OAUTH_TOKEN
# …or for API billing instead:  export ANTHROPIC_API_KEY=sk-ant-...
which claude && echo "auth: ${CLAUDE_CODE_OAUTH_TOKEN:+oauth}${ANTHROPIC_AUTH_TOKEN:+bearer}${ANTHROPIC_API_KEY:+apikey}"
```

Any one of `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` makes the adapter
available; with none it silently falls back to the deterministic floor.

**4b. Opt into the live agent** (staged, capping iterations to control cost):

```bash
uv run siftmesh plan "$RUN"
uv run siftmesh dispatch "$RUN" --agent-profile claude_headless
uv run siftmesh collect  "$RUN"
uv run siftmesh critique "$RUN"
```

Or one-shot with the friendly flag (Claude preferred → OpenCode → floor; live until a gate):

```bash
uv run siftmesh run ./case_disk --evidence ~/projects/ev_disk --agent claude --auto-human-loop --max-iterations 2
```

`--agent` options: `claude` | `opencode` | `deterministic`. Default (no flag) stays the deterministic
floor. Per-agent models come from `siftmesh_core/adapters/agent_profiles.yaml`
(claude → `claude-opus-4-8`, opencode → `anthropic/claude-sonnet-4-6`).

**4c. Watch the self-correction loop happen** (in `$RUN`):

```bash
cat "$RUN/audit/orchestration_events.jsonl"   # adapter_unavailable? which adapter ran
cat "$RUN/audit/agent_calls.jsonl"            # attempt=1, attempt=2 …
cat "$RUN/audit/critic_verdicts.jsonl"        # verdict=retry_required → then accepted
cat "$RUN/claims/unsupported_claims.jsonl"    # the rejected, under-anchored over-claim (attempt 1)
cat "$RUN/claims/claim_ledger.jsonl"          # the corrected, anchored claim (attempt 2)
cat "$RUN/audit/retries.jsonl"                # the retry record + reasons
```

The story you're verifying: attempt 1 over-claims without a `tool_call_id` / `source_sha256` → the
critic returns `retry_required` and the claim lands only in `unsupported_claims.jsonl` → the rejection
reasons are injected into the retry prompt → attempt 2 cites the real anchor → it is accepted and
promoted to `claim_ledger.jsonl`. Claim IDs are attempt-scoped (`…-A1-…` vs `…-A2-…`) so the
correction never overwrites the rejection.

---

## 5 — Inspect / drive any run

```bash
uv run siftmesh status "$RUN"                  # state, mode, iteration, gates, per-task attempts
uv run siftmesh resume "$RUN"                  # continue an interrupted run
uv run siftmesh approve "$RUN" --gate plan     # gates: plan | dispatch | retry | report
uv run siftmesh reject  "$RUN" --gate retry
uv run siftmesh retry   "$RUN" TASK-001        # re-critique one task; tighten + re-dispatch if DECIDE says so
```

`tasks list` / `claims list` / `audit tail` are debug stubs — read the JSONL files directly (above).

---

## Practical notes

- **Path arg vs RUN-id:** staged commands (`plan/dispatch/collect/critique/status/resume/approve/
  reject/retry/extract-artifacts/analyze-memory/decompress/ingest-derived`) take a **RUN directory
  path** (hence `$RUN`). `init-case` / `run` take a **case dir**.
- **Cost/time:** hashing 22.6 GB ≈ ~1 min; Sleuthkit extraction = minutes; Volatility
  `netscan`/`malfind` = slow. For live runs start with `--max-iterations 1`–`2` and a narrow set of
  extracted artifacts.
- **Fail-closed:** a missing SIFT-lane tool yields a clean `BackendUnavailableError` when invoked —
  install the tool; never a fake result.
- **Config precedence:** init args > env (`SIFTMESH_*`) > `siftmesh.toml` > defaults. Useful env vars:
  `SIFTMESH_VOL_PATH`, `SIFTMESH_VOL_SYMBOL_DIRS`, `SIFTMESH_EXECUTOR_SELECTION` (`deterministic` |
  `live` | `auto`), `SIFTMESH_CAPS__MAX_ITERATIONS=N`.

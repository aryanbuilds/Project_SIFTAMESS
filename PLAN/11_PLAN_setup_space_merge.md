# PLAN 11 — One-command setup, space-aware portioned runs, cross-run merge + docs restructure

_Status: **approved, NOT yet executed** (maintainer-directed, 2026-06-10). Execute as a
bd-tracked refinement when scheduled. Supersedes nothing; additive to the shipped refinement
(incident brief / auto-quarantine / auto-decompress)._

## Context

Three maintainer asks rolled into one refinement:

1. **Too many setup commands** — `uv sync --all-extras`, vol-symbols mkdir/export, doctor… merge
   them: `siftmesh doctor --setup` checks AND installs/configures everything in one shot.
2. **No hard "25 GB free" rule** — the ROCBA set is reference data, not a benchmark. Instead a
   **pre-flight space estimator** computes how large the derived data can get from the *actual
   supplied evidence* (exact where archive headers tell us: `zipfile.infolist()` for zips,
   `7z l -slt` for 7z — confirmed via web research; labeled headroom where unknowable) and checks
   it against free disk. If it won't fit, don't just abort: **propose a partitioned plan** —
   split the evidence into portions that each fit, print the exact CLI commands per portion
   (run → prune the bulky derived data, keep ledgers → next portion), ending in a merge.
3. **Cross-run merge** (decided: deterministic core + agent loop) — `siftmesh merge` combines N
   completed runs' ledgers into one merged final report with per-run provenance and cross-run
   contradiction detection; opt-in `--agent claude` adds the deep-agent synthesis loop (agent
   reads all merged promoted claims → proposes a cross-run synthesis → deterministic validator
   checks every claim reference → retry on inconsistency → report; PLAN/01 "LLM proposes, code
   decides"). This lets the user analyze disk and memory in separate RUNs, delete the bulky one,
   and still get one combined report — the RUN concept tracks which run did what.
4. **README + RUNBOOK rewritten** around command tables with a clear **automated vs manual
   (deterministic, staged)** separation.

Hard constraints: CLAUDE.md §4 command names are frozen (nothing removed/renamed — `merge`,
`prune` are additive). `run --brief/--objective` stay (they carry the objective, not setup). CI
untouched (hard rule). No AI co-author. bd-tracked. Fixtures-only testing (§2B).

## Pillar A — `siftmesh doctor --setup` (check + install + configure)

`doctor.py` + `cli.py` doctor command:
- `run_doctor(*, protocol_sift=False, setup=False, settings=None)`. When `setup`:
  1. `subprocess.run([shutil.which("uv"), "sync", "--all-extras"], shell=False)`; uv absent →
     FAIL line + exit 1 (fail closed, never a pip fallback). `importlib.invalidate_caches()`
     after, so the dependency checks see the new packages.
  2. `mkdir -p` the vol symbol cache (new default below); report as a check line.
  3. Claude auth line gains the exact next step when absent (`claude setup-token` /
     `ANTHROPIC_API_KEY`) — login itself is interactive, doctor only instructs.
  4. Then the normal check report runs (proves setup worked). Plain `doctor` unchanged
     (existing 4 tests in `tests/EPIC_A_TESTS/test_doctor.py` stay green).
- Kill the env-var step forever: `config.py` `vol_symbol_dirs` default `None` →
  `~/.cache/siftmesh/vol_symbols` (default_factory); `memory_tools.py` mkdirs it before
  appending `--symbol-dirs`; `cli.py analyze-memory` falls back to settings when flag omitted.
- Message consistency: every "uv sync --extra …" pointer (doctor.py, intake/brief.py,
  mcp_gateway/backends/real.py ×3, pyproject comment) → "run `siftmesh doctor --setup`".

## Pillar B — pre-flight space estimator + partition plan + `siftmesh prune`

- **New `siftmesh_core/evidence/space.py`**:
  - `estimate_required(evidence_dir) -> SpaceEstimate` — per top-level evidence item:
    `.zip` → sum of `zipfile.infolist()` uncompressed sizes (exact, stdlib, no extraction; if a
    single member is itself a `.7z`/archive, add its `7z l -slt` listed size when `7z` present,
    else a labeled ×2 allowance); `.7z` → `7z l -slt` totals (fixed argv, no shell); `.gz` →
    labeled allowance (header size is mod-2³² unreliable); disk images (`.e01/.raw/...`) →
    labeled extraction allowance (configurable fraction, default 5% of image size — extracted
    triage artifacts are small relative to the image); everything else → 0 derived. Returns
    per-item rows {path, base_bytes, derived_bytes, exact|estimated} + totals.
  - `free_bytes(path)` via `shutil.disk_usage`.
  - `partition_plan(rows, budget_bytes) -> list[Portion]` — first-fit-decreasing bin-pack of
    evidence items into portions whose derived footprint fits the budget; deterministic, pure
    (code decides — no LLM needed for arithmetic).
- **Wire into `run`** (cli.py, before `vault_init_case` so nothing heavy starts): estimate vs
  free. Fits → one `space_check` line + proceed. Doesn't fit → exit 1 with: needed-vs-free
  table (exact/estimated labeled), sizes of existing `case_runs/RUN-*` dirs (what you could
  delete), and a **printed portion plan**: per portion the exact commands —
  `mkdir + ln` (hard-link the portion's files into `ev_pN/`), `siftmesh run ./case_pN
  --evidence ev_pN …`, `siftmesh prune <run>` between portions, and the final
  `siftmesh merge` command. `--force` skips the gate. Estimator failure (corrupt archive) →
  warn + proceed (the gate must never block on its own bug).
- **New `siftmesh prune <run>`**: delete the bulky `evidence/extracted/` derived files of a
  COMPLETED run while keeping every ledger/report/manifest (what merge needs); record a
  `derived_pruned` custody event + orchestration event listing freed bytes; refuse on a
  non-terminal run unless `--force`. This is what makes "analyze → free space → analyze next →
  merge" safe and auditable.

## Pillar C — `siftmesh merge` (deterministic core + agent synthesis loop)

- `siftmesh merge ./case_merged --run <RUN_A> --run <RUN_B> [...] [--agent claude]`:
  - Creates a fresh merge run dir (`case_merged/case_runs/RUN-*`, standard subtree) so outputs
    stay path-policed and inspectable like any run.
  - Loads each source run via the existing `load_report_view` (reports/loader.py — graceful on
    pruned runs since ledgers are kept); writes `claims/merged_claims.jsonl` (one line per
    source claim wrapped with `source_run` provenance — avoids fighting the strict Claim schema)
    and a `context/merge_sources.json` (run ids, manifests, objectives).
  - **Cross-run contradiction pass**: expose the critic's `_detect_contradictions` as a public
    pure function and run it over the COMBINED promoted claims; results into the merged report.
  - `reports/final_report.md` (deterministic, code-built like Epic J): per-run summary table
    (run id, evidence, findings counts, quarantined), combined findings with `source_run` on
    every anchor, cross-run contradictions, combined "Answer to the incident objective"
    (objectives from any source manifest), merged limitations.
- **Agent synthesis loop (opt-in `--agent claude`)**: build a spotlighted prompt containing the
  merged PROMOTED claims (id + text + anchor rows via `wrap_evidence`; the objective as the
  TRUSTED section); the agent proposes a cross-run synthesis narrative citing claim ids; a
  **deterministic validator** checks every cited id exists in the merged set and no uncited
  factual sentence introduces an unanchored artifact/host name (structural checks only);
  invalid → retry once with the validator's reasons (the existing critic-feedback prompt
  pattern); valid → a clearly-labeled "Cross-run analyst synthesis (agent-proposed; every
  reference validated)" section; failure/absence → report completes without it (fail-soft,
  key-free floor intact). Reuses the claude adapter subprocess seam; unit tests mock the
  subprocess exactly like `tests/EPIC_F_TESTS/test_live_adapters.py`.

## Pillar D — README.md + RUNBOOK.md restructure (tables, automated vs manual)

- **README**: pitch → Setup (`uv sync` + `uv run siftmesh doctor --setup`) → the one-command
  autonomous run (`--brief|--objective`, `--agent claude`, `--auto`) → **three command tables**
  (one row = command + short description):
  1. *Automated*: `run` (4 modes), `resume`, `status`, `approve`, `reject`, `merge`,
     `doctor [--setup]`.
  2. *Manual / deterministic staged*: `init-case`, `plan`, `dispatch`, `collect`, `critique`,
     `report`, `replay`, `extract-artifacts`, `analyze-memory`, `decompress`, `ingest-derived`,
     `retry`, `prune` — with the note that `run --auto` does all of this itself.
  3. *Inspection (read-only)*: `tasks list|show`, `claims list|show`, `audit tail`,
     `protocol-sift inspect`, `skills list`.
  → dev gates + license.
- **RUNBOOK**: §0 Setup = `doctor --setup` (one command). §1 AUTOMATED: fixture smoke + the
  full ROCBA one-command run + the **space-aware portioned workflow** (what the printed plan
  looks like; run → prune → run → merge), `resume/status/approve` drive table. §2 MANUAL /
  DETERMINISTIC: old §2+§3 merged into one staged table (disk + memory lanes), keeping `--keys`
  guidance + the "don't re-plan after manual extract" warning; no vol-symbols step (default
  now). §3 live agent notes (auth, models, watching self-correction + merge synthesis ledgers).
  §4 the same three command tables + practical notes — **the space note describes the
  estimator/portion flow, no fixed GB number**.

## bd + tests + ship

- bd: parent issue + children (doctor-setup, space/partition/prune, merge+synthesis, docs);
  `bd remember` the estimator + merge facts. Close with evidence.
- Tests (fixtures only): doctor `--setup` argv/mkdir/fail-closed (monkeypatched subprocess +
  which); config default symbol dir + env override; `space.py` (zip with known uncompressed
  sizes → exact estimate; fits vs not; FFD portion plan determinism); `prune` (extracted gone,
  ledgers intact, custody event, refuses non-terminal); `merge` (two `make_real_run` runs →
  merged report with provenance + combined objective answer; a seeded cross-run contradiction
  detected); synthesis validator (mocked agent: valid refs accepted, invalid ref → retry →
  fail-soft).
- Gates: ruff check/format, mypy, pytest. Update PROJECT_CONTEXT/OVERALL_PLAN header notes.
  Commit (no AI co-author) → push.

## Critical files
- NEW: `siftmesh_core/evidence/space.py`, `siftmesh_core/reports/merge_report.py` (or
  `orchestrator/merge.py`), tests for space/prune/merge/doctor-setup.
- EDIT: `siftmesh_core/doctor.py`, `siftmesh_core/cli.py` (doctor flag, space gate in `run`,
  new `prune` + `merge` commands, analyze-memory fallback), `siftmesh_core/config.py`,
  `siftmesh_core/mcp_gateway/tools/memory_tools.py`, `siftmesh_core/orchestrator/critic.py`
  (publicize `_detect_contradictions`), `siftmesh_core/intake/brief.py` +
  `mcp_gateway/backends/real.py` (message pointers), `README.md`, `RUNBOOK.md`,
  `PROJECT_CONTEXT.md`/`OVERALL_PLAN_DETAILED.md` headers, `pyproject.toml` (comment).
- REUSE: `load_report_view` (reports/loader.py), `wrap_evidence`/spotlight, claude adapter
  subprocess seam + mock pattern, `MarkdownBuilder`/`compose_report` (reports/render.py),
  custody ledger append, `make_real_run` test factory.

## Verification (when executed)
1. `uv run siftmesh doctor --setup` → installs all extras, creates the symbol cache, full
   report, exit 0; no more `--all-extras`/export steps anywhere in docs.
2. Fixture smoke: tiny evidence + a zip with known uncompressed size → `run` prints the space
   line; artificially small budget (env/monkeypatch) → portion plan with exact commands printed.
3. Two fixture runs → `prune` the first (ledgers intact) → `merge` produces one combined report
   answering the objective with per-run provenance; with mocked agent, the synthesis section
   appears only when every reference validates.
4. `uv run pytest -q`, ruff, mypy green. README/RUNBOOK tables render with the
   automated-vs-manual split. Push clean.

## Research notes
- 7z uncompressed sizes without extraction: `7z l` / `7z l -slt`
  (https://sourceforge.net/p/sevenzip/discussion/45798/thread/cca702d04a,
  https://stackoverflow.com/questions/3865892/7z-get-total-size-of-uncompress-contents).
- zip: `zipfile.infolist()` carries exact uncompressed sizes (stdlib; no extraction).
- gzip header size field is mod-2³² → unreliable for >4 GB; use a labeled allowance.
- No off-the-shelf DFIR pre-flight space formula exists (Plaso et al. only advise "ample
  space"), so the deterministic estimator + FFD portion plan is an original, code-decides design.

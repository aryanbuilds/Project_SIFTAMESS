# PLAN 06 — Reports, Demo & Security (Epics J, K, L)

_Phases 10–11 + the security workstream. Reports/replay generated deterministically from ledgers (J), the reproducible demo case + deterministic real self-correction (K), and the threat model + bypass-test suite that proves constraints hold architecturally (L). Serves criteria 1, 2, 4, 5._

---

## Foundational decision driving J/K/L

**The headline is the live autonomous agent run; a recorded-golden run (its real ledgers) is the reproducible spine.** The live agent investigates real evidence and self-corrects emergently (needs an LLM at run time). Four of the eight mandatory artifacts — (2) demo video, (6) accuracy/FP report, (7) working software, (8) execution logs — require a *reproducible run to exist*; so we **record one real agent run and commit its ledgers as the golden** (real artifacts, not a mock — the deterministic governance + report generation are byte-deterministic over those ledgers). Consequences baked into J/K/L:
1. The committed artifacts (recorded-golden ledgers + generated reports) reproduce with **no API keys and no network**, Linux-first; a fresh *live* run needs an LLM/agent (dev + target = SANS SIFT / Ubuntu; see PLAN/08 §0.1, §6).
2. The **live autonomous agent is core (never cut)** — it is the product's point; the recorded-golden run + deterministic governance is the reproducible safety-net floor, not a replacement.
3. Reports (J) are **byte-deterministic** functions of the JSONL ledgers — both the snapshot-test backbone (Epic M) and the "replayable audit" differentiator (Epic L).

**Cut-line invariant:** a cut is only legal if it preserves (a) all 8 submission artifacts, (b) **the live autonomous agent + its genuine self-correction** (claim rejected/downgraded → retry **or follow-up task** → corrected claim) **+ the chain-of-custody + claim ledgers**, and (c) the green bypass-test suite. **Governance gates quality, not quantity** — the agent must still surface multiple candidate findings; the critic downgrades/labels rather than silently dropping, so breadth/depth is not starved.

---

# EPIC J — Reports & Replay

**Goal:** Generate every judge-facing report deterministically from run-dir JSONL/JSON ledgers. **Criteria:** 2 (FP self-assessment, traceable findings), 5 (traceability, replay), 6 (documentation); supports 1 (surfaces self-correction). **Deps:** C schemas (frozen), ledgers from Epics F–H, demo ledgers from Epic K for golden fixtures.

### J — Determinism contract (write once, enforced by Epic M)
Reports MUST be a pure function of run-dir files: (1) read-only from `claims/*.jsonl`, `audit/*.jsonl`, `results/*.json`, `evidence/evidence_manifest.json`; (2) stable sort (claims by `claim_id`, events by `(timestamp_utc, sequence)`, tools by `tool_call_id`); (3) pinned Jinja2 env (fixed `trim_blocks`/`lstrip_blocks`, `\n` newlines, sorted dict rendering); (4) generation timestamp + host metadata **segregated** into a delimited header block that golden tests exclude. The report *body* is byte-stable across two runs of identical ledgers — this byte-stability is the proof of the replayable-audit differentiator.

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| J1 | Report data-loader | Read-only loader → validated Pydantic view-models from all ledgers + manifest; stable sort; no side effects. | `reports/loader.py` | C | identical ordered structures across 2 calls; malformed JSONL → line-numbered error. | M | schema drift → pin to frozen C |
| J2 | Determinism harness | Shared Jinja2 env factory + `render_body()`/`render_header()` split so golden tests compare only the body. | `reports/render.py`, `reports/templates/_macros.j2` | J1 | two renders of same ledgers → identical body bytes; header differs only in ts/host. | S | locale/newline → force `\n`, UTC, sorted |
| J3 | `final_report.md` generator + template | Sections: exec summary; confirmed findings; inferred (labeled); rejected/unsupported claims; contradictions + handling; self-correction events (from `retries.jsonl` + verdicts); tool-execution appendix (every tool_call_id → artifact → sha256); limitations incl. "NOT court-ready forensic soundness". | `reports/final_report.py`, `templates/final_report.md.j2` | J1,J2 | on demo run: confirmed findings present; planted unsupported claim ONLY in rejected section; ≥1 self-correction rendered; appendix lists every tool call w/ hash. | L | unsupported leaking into facts → golden test |
| J4 | `accuracy_report.md` generator + template | Precision / FP rate by diffing claim ledger vs `examples/demo_case/expected_findings.md`; list TPs, FPs, FNs, the rejected FP, contradiction handling; self-assessment narrative. | `reports/accuracy_report.py`, `templates/accuracy_report.md.j2` | J1, K2 | numbers match hand-computed values; planted FP counted as caught-by-critic, not a fact. | M | ground-truth alignment → co-design w/ K2 |
| J5 | `dataset_documentation.md` generator | Provenance, structure, license, ground-truth of demo dataset; provenance headers per artifact; generated from manifest. | `reports/dataset_documentation.py`, `templates/dataset_documentation.md.j2` | K1 | every demo artifact listed w/ sha256 + license + provenance; matches manifest byte-for-byte. | S | drift → generate from manifest |
| J6 | `architecture_notes.md` generator | Run-specific notes (modes used, gates hit, guardrails active); complements static `docs/architecture.md`. | `reports/architecture_notes.py`, `templates/architecture_notes.md.j2` | J1 | names each security boundary crossed + each gate decision in the run. | S | overlap w/ N → run-specific here |
| J7 | `replay` command + `replay.html` | `siftmesh replay RUN_PATH` replays `orchestration_events.jsonl` as ordered timestamped trace (transitions, dispatches, tool calls, verdicts, retries). Emit text replay (terminal) AND self-contained static `replay.html` (no JS frameworks, inline CSS). | `reports/replay.py`, `templates/replay.html.j2` | J1,J2 | text replay reconstructs full timeline from JSONL alone; HTML opens offline w/ zero external assets; both deterministic. | M | HTML scope creep → text is MVP, HTML degrades first |
| J8 | Report wiring into CLI/state machine | Hook generators to `siftmesh report` + REPORT state; all reports land under `reports/`. | `reports/__init__.py`, `cli.py` | J3–J7 | `siftmesh report RUN_PATH` writes all 5 report files + replay.html. | S | — |

**Design (J):** Deterministic Jinja2 from ledgers over LLM-written prose — guarantees reproducibility, snapshot-testability, the replayable-audit claim. Any LLM-authored narrative (e.g., exec summary) is stored as a ledger field and rendered verbatim, never regenerated at report time. HTML replay degrades first; text replay shares the same loader so cutting HTML costs nothing structurally. The limitations section is mandatory content (carries the court-readiness non-goal + known FP rate).

---

# EPIC K — Demo Case & Self-Correction Scenario

**Goal:** A small, fully reproducible `examples/demo_case/` with documented ground truth and a deterministic, reliable real self-correction sequence (a deterministic engine over real tool output) that runs with zero live LLM, Linux-first (dev + target = SANS SIFT / Ubuntu; see PLAN/08 §0.1). Tool/connector licenses are not a blocker — replaceable backends; the project itself stays Apache-2.0. **The submission spine.** **Criteria:** 1 (self-correction — tiebreaker), 2 (FP ground truth), 3 (breadth), 6 (reproducible run). **Deps:** Epics D–G (real executor, critic, retry), J4 (accuracy report consumes K2). **K and J4 are co-designed.**

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| K1 | Real demo evidence set (maintainer-provided) | Small, self-contained, real Windows-triage artifacts (real EVTX / prefetch / registry hive / `$MFT` files — Windows OS forensic artifacts analyzed on the Linux SIFT box, NOT a multi-GB image). Maintainer provides the real files at this stage — **STOP and ask, do not fabricate** (see PLAN/08 §4). Documented provenance, precomputed hashes. | `examples/demo_case/evidence/*`, `examples/demo_case/README.md` | — | total < a few MB; runs natively on the Linux SIFT target; every file hashed; documented provenance (sample-data license not a blocker — see PLAN/08 §5). | M | the only real gate is real evidence (not tool buildability or license) → STOP-and-ask gate; maintainer supplies real triage artifacts (PLAN/08 §4) |
| K2 | `expected_findings.md` ground truth (co-designed w/ J4) | Enumerate true-positive findings; the ONE unsupported/FP claim the critic must reject; the contradiction pair + resolution; optional injection string. | `examples/demo_case/expected_findings.md` | K1 | lists each TP/FP/FN with artifact+evidence; J4 computes precision/FP directly. | M | drift → author K2 + J4 together; assert in a test |
| K3 | Deterministic REAL self-correction | Deterministic engine over real K1 evidence (PLAN/08 §6): an under-specified first-pass contract (`success_criteria` not yet requiring `source_sha256` + `tool_call_id`) lets the real in-process tool emit a real claim that genuinely lacks the evidence binding → critic structural check returns `retry_required` → DECIDE retries with a tightened contract → the second real attempt over the same real tools passes and is promoted to `claim_ledger.jsonl`. Integration-gated until K1 lands. | `examples/demo_case/scenarios/*`, `adapters/executor.py`, `orchestrator/ultraworker.py` | F,G,K1 | run reliably: under-specified claim → `retry_required` → retry task → corrected claim → report shows corrected finding + logs self-correction; reproducible ≥10/10. | L | flakiness → determinism comes from real tools over fixed committed evidence with no LLM and no randomness |
| K4 | Optional prompt-injection demo event | Evidence field contains an instruction-like string; Prompt-Injection Guard flags to `injection_alerts.jsonl`; agent treats as evidence only. OPTIONAL. | `examples/demo_case/evidence/*` (injection row) | K1, L4 | injection string logged as alert, never acted on; appears in report injection section. | S | first cut-line item; doesn't break the spine |
| K5 | `run_demo.sh` (Linux/SIFT primary) | One-command reproducible demo on the Linux SIFT target, invoking `siftmesh run ./examples/demo_case --evidence … --auto-human-loop` (+ `--auto` non-interactive variant for CI/video). Optional `run_demo.ps1` convenience wrapper only (not required — judges run on Linux/SIFT). | `examples/demo_case/run_demo.sh` (+ optional `run_demo.ps1`) | K1–K3 | the Linux `run_demo.sh` produces all MVP run artifacts + self-correction, no network/keys. | S | path/EOL → pathlib in core; scripts thin |
| K6 | Demo golden run snapshot | Commit reference run output (or golden report bodies) over **real tool output** so regressions are detectable and the video matches the repo. Integration-gated on K1 real evidence. | `examples/demo_case/golden/`, `tests/test_demo_end_to_end.py` | K1, K3, J3 | re-running reproduces golden report bodies byte-for-byte (excl. segregated header). | M | golden churn → update intentionally; CI diff catches drift |

**Design (K):** **Real, maintainer-provided evidence for the guaranteed path** — public datasets (EVTX-ATTACK-SAMPLES, OTRF/Mordor, BOTS v3) are documented in `dataset_documentation.md` as *optional upgrade datasets the architecture supports*, but the reproducible demo uses real Windows-triage artifacts the maintainer provides (STOP-and-ask gate at K1; keeps the run small and Linux-native on the SIFT target; sample-data license is not a blocker — see PLAN/08 §4–§5). **Self-correction is real and deterministic, not scripted** — a deterministic engine over real tool output (PLAN/08 §6) guarantees it fires every time because determinism comes from real tools over fixed committed evidence with no LLM and no randomness; emergent LLM self-correction is shown in the video as an upgrade. **K2 ⇄ J4 are one logical artifact pair.**

---

# EPIC L — Security & Threat Model + Bypass Suite

**Goal:** Document the threat model and **prove** — via code-enforced guardrails and an enumerated bypass-test suite — that constraints hold regardless of which agent/harness runs. **The primary differentiator for criterion 4.** **Criteria:** 4 (architectural, bypass-tested constraints — high value), 5 (audit), 2 (injection/hallucination mitigation). **Deps:** `evidence/path_policy.py`, forbidden-tool registry (Epic D), `ledgers/injection_alerts.py`, critic (Epic G). Threat-model doc is *design*, authorable Day 1–2.

### L — Differentiation framing
CAO enforces tool restrictions at the *harness* layer (role/allowlist, tmux isolation, working-dir canonicalization) — but some providers only **soft-enforce via prompts**, and CAO does not model *evidence as hostile*. Valhuntir adds an HMAC-signed approval ledger. **SIFTMesh's differentiator:** a *forensic policy layer above the harness* — code-decided `path_policy` (writes only under the run dir) + a forbidden-tool registry that hold no matter which provider executes, plus evidence-as-hostile spotlighting and an injection-alert ledger. The repeated framing: **"LLM proposes / code decides"** — show the deterministic gate, not the prompt that asks nicely. **The local real path is 100% in-process** — 7 of the 8 MVP tools are typed Python library calls (no subprocess, no shell), so there is literally no command string to inject into; this *strengthens* criterion 4 rather than complicating it (see PLAN/08 §1). **The same policy layer governs A2A-discovered remote/opaque agents** via the `x_siftmesh` overlay (untrusted-by-default + conformance gate), so adopting standardized agent interop never widens what any agent is permitted to do — a point worth making explicitly for criterion 4.

| Task | Title | Description | Key files | Deps | Acceptance | Eff | Risk |
|---|---|---|---|---|---|---|---|
| L1 | `docs/threat_model.md` | Threats: prompt injection from evidence; MCP tool-poisoning & confused-deputy; path traversal / write escape; evidence tampering; over-broad/hallucinated claims; **untrusted A2A remote agent** (over-claimed Agent Card capabilities, confused-deputy, supply-chain via a malicious card). Map each → OWASP LLM Top 10, a code-enforced control, and a bypass test. Position vs CAO + Valhuntir. | `docs/threat_model.md` | — | every threat has: control(code) + owning module + bypass-test ID + residual-risk note. | M | vague prose → require threat→control→test triple |
| L2 | Path-policy guardrail spec | Document + specify `path_policy`: all writes canonicalized + restricted to run dir; system paths blocked; symlink resolution enforced; originals read-only. | `evidence/path_policy.py`, `readonly.py`, `docs/threat_model.md` | Epic B | spec lists allowed write roots + rejection rules; matched by `test_write_paths_restricted_to_run_directory`. | M | — |
| L3 | Forbidden-tool registry spec | Registry makes the 7 forbidden tools un-exposable + un-callable; allowlist-only MCP surface. | `mcp_gateway/server.py`, `registry.py`, `docs/threat_model.md` | Epic D | registering/calling any forbidden tool raises; matched by `test_forbidden_tool_not_exposed`. | M | bypass via dynamic dispatch → allowlist by explicit enum, no eval |
| L4 | Evidence-as-hostile + spotlighting spec | Specify normalize-to-JSON-rows before any LLM; quote/label attacker-controlled fields; spotlighting delimiters; injection-alert logging; never pass raw large logs to Planner. | `ledgers/injection_alerts.py`, `evidence/*`, `docs/threat_model.md`, `docs/evidence_integrity.md` | Epic D | spec defines spotlighting markers + "instruction-like evidence → `injection_alerts.jsonl`, never executed"; matched by `test_bypass_injection`. | M | soft-only → pair with critic behavior check (code) |
| L5 | **Bypass-test suite** (the proof) | Enumerated adversarial tests asserting guardrails hold architecturally. | `tests/test_bypass_path_escape.py`, `test_bypass_forbidden_tool.py`, `test_bypass_injection.py`, `test_bypass_evidence_readonly.py`, `test_bypass_claim_no_toolcall.py` | L2–L4, Epic G | all five bypass attempts blocked/logged, not executed; suite green in CI. | L | tests asserting prompt text not behavior → assert the gate's *effect* |
| L6 | Architecture diagram w/ security boundaries | Diagram (artifact #3): evidence-vault, MCP typed-tool, run-dir write, evidence-as-hostile, critic boundaries + human gates. Source + exported SVG/PNG. | `docs/architecture.md`, `docs/diagrams/security_boundaries.*` | L1 | diagram labels all 5 boundaries; referenced from README + threat model. | M | shared w/ N3 — single source of truth |

**Bypass-test → guardrail → required-test mapping (L5):**

| Bypass attempt | Guardrail | Maps to |
|---|---|---|
| Write outside run dir | `path_policy` blocks | `test_write_paths_restricted_to_run_directory` |
| Expose/call a forbidden tool | registry rejects | `test_forbidden_tool_not_exposed` |
| Prompt-injection string in evidence | logged to `injection_alerts.jsonl`, never executed | `test_bypass_injection` |
| Modify original evidence | read-only enforcement blocks | `test_original_evidence_not_modified` |
| Claim missing `tool_call_id`/evidence ref | critic rejects | `test_critic_rejects_missing_tool_call_id` |
| Untrusted A2A agent over-claims powers / asserts final claims | policy overlay (untrusted-by-default) + conformance gate + critic governs every output | `test_a2a_overlay_untrusted_by_default` / `test_a2a_output_passes_critic` |

**Design (L):** Guardrails in code, not prompts — every constraint judged under criterion 4 is a deterministic gate with a test; prompt instructions are defense-in-depth only. The policy layer sits *above* the harness so it holds even if CAO runs a permissive profile. The threat model is authored Day 1–2 (design, not code) so it shapes module APIs rather than being retrofitted.

---

## Sequencing (Days 7–9, threaded)

```
Day 7: J3 final_report + J4 accuracy (after critic G); L4 evidence-as-hostile spec
Day 8: J7 text replay; L5 bypass suite
Day 5–6: K1/K2 demo evidence + ground truth; K3 deterministic real self-correction
Day 9: K5 run_demo + K6 golden run; J6/J8 wiring; L6 diagram (with N3)
```
L1/L2/L3 are authored on Days 1–4 alongside the modules they constrain. `replay.html` (J7) is the degrade-first item; K4 injection event is the first optional cut.

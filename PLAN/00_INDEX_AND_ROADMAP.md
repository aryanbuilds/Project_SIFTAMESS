# SIFTMesh — Master Index & Roadmap

_Plan set version 1.0 · authored 2026-06-04 · expands `OVERALL_PLAN_DETAILED.md` into a Plan → Epic → Task structure._

> **Fact-hygiene note (read first).** The scope drivers below — submission deadline, the 6 judging criteria, the 8 mandatory artifacts, and the real tool list (tool/connector licenses are **not a blocker** — replaceable; see `PLAN/08 §0.1`) — come from research against `findevil.devpost.com` and primary tool/SDK sources. **Re-confirm the deadline, judging rubric, and artifact list against the live `findevil.devpost.com/rules` page before locking the schedule.** The claim "Protocol SIFT is a config/skill layer, not an MCP server" is our *best current understanding*; the chosen **hybrid** architecture is deliberately robust whether or not Protocol SIFT exposes MCP, so nothing in this plan breaks if that detail differs.
>
> **Real-only delivery (no mocks/placeholders): see `PLAN/08_REAL_TOOL_STACK.md` (authoritative, research-confirmed).**

---

## 0. How to read this plan set

The work is decomposed three levels deep: **Plan (file) → Epic (A–P) → Task (A1, A2 …)**. Eight grouped files:

| File | Epics | Theme |
|---|---|---|
| `00_INDEX_AND_ROADMAP.md` (this) | — | Index, deltas, criteria matrix, schedule, risks, roadmap |
| `01_ARCHITECTURE.md` | — | Hybrid architecture, layers, security boundaries, state machine, stack |
| `02_PLAN_foundation_evidence.md` | A, B, C | Skeleton · Evidence vault · Schemas & ledgers |
| `03_PLAN_mcp_tool_gateway.md` | D | Typed, evidence-safe MCP tool gateway |
| `04_PLAN_orchestration_critic.md` | E, F, G, H | Planner · Executors · **Critic/self-correction (hero)** · State machine |
| `05_PLAN_agents_automation.md` | I, **P** | Agent profiles · CAO/adapters · automation modes · **A2A interop (Epic P)** |
| `06_PLAN_reports_demo_security.md` | J, K, L | Reports/replay · Demo case · **Threat model + bypass suite** |
| `07_PLAN_testing_docs_submission.md` | M, N, O | Testing/CI · Docs & submission matrix · Optional TUI |

Each Epic file carries: goal, judging-criteria mapping, dependencies, a **full Task table** (ID · description · key files · deps · testable acceptance · owning role · effort S/M/L · risk), key design decisions, and tests-to-add.

---

## 1. Mission (one paragraph)

SIFTMesh is a **CLI-first, evidence-safe, agent-agnostic control plane for autonomous DFIR** on SANS SIFT / Protocol SIFT. It turns a forensic investigation into a deterministic state machine that dispatches narrow task contracts to agents, runs typed read-only forensic tools, records every finding as an evidence-anchored claim, runs an adversarial critic that rejects unsupported claims and drives self-correction, and produces replayable, judge-ready reports. **The CLI is the source of truth; the LLM proposes, deterministic code decides.**

**Protocol stack (who does what):** **MCP = agent→tool** (typed SIFT forensic tools) · **A2A = agent→agent** (Agent Card discovery + remote delegation, optional) · **CAO = local terminal-agent harness** (Claude Code / OpenCode / Codex / Gemini in tmux) · **SIFTMesh = DFIR control plane** (policy, evidence, claims, retries, reports). MCP and A2A are complementary; A2A never replaces SIFTMesh's governance (see Epic P + `01_ARCHITECTURE.md §2.1`).

---

## 2. What changed & why — deltas vs `OVERALL_PLAN_DETAILED.md` (the "improve" half)

The request was to **analyze and improve**, not only restructure. The substantive improvements:

| # | Change | Why |
|---|---|---|
| Δ1 | **12-day schedule → 11-day reality**, with **2 reserved no-code days** for SIFT-VM validation + video + Devpost submission. | Submission closes **Jun 15, 2026, 11:45 PM EDT**; today is Jun 4 (~11 days). The original assumed 12 days and left submission/recording friction unscheduled — a classic deadline-day failure mode. |
| Δ2 | **Two new Epics the original had no days for:** **L — Security & Threat Model** (with a *bypass-test suite*) and **M — Testing & CI** (threaded as TDD, not bolted on). | "Constraint Implementation" and "Audit Trail Quality" are **two of six equally-weighted judged criteria**, and constraints must be *architectural, bypass-tested* — not prose. The original plan had testing only implicitly and no threat model. |
| Δ3 | **MCP gateway reframed** from "implement forensic parsers" to **thin, audited, evidence-safe wrappers** around the best **real** tools (license not a blocker — replaceable backends; see `PLAN/08 §0.1`, §5) — 8 real in-process backends now (`hashlib`/`evtx`/`regipy`/`pyscca`/`mft` + own-code; see `PLAN/08_REAL_TOOL_STACK.md §3`), with Plaso/SIFT-lane CLIs as gated upgrades behind the same typed interface (no placeholder backends). | Protocol SIFT + SIFT Workstation already ship 200+ tools; reimplementing parsers in 11 days is wasteful and risky. The wrapper's value is *typed output + provenance + safety + audit*, not parsing. |
| Δ4 | **Explicit criteria→Epic mapping** + an **8-artifact traceability matrix and go/no-go checklist**. | Makes every task accountable to a scored dimension and guarantees no mandatory submission artifact is missed. |
| Δ5 | **Linux-first (dev + target = SANS SIFT / Ubuntu)** — `pathlib` discipline (good hygiene), **Ubuntu-primary CI (= the SIFT target)**, and a **deterministic-governance + recorded-golden reproducibility floor** under the live autonomous agent (the agent is the headline; the deterministic critic/decide + a recorded real run give a no-keys reproducible regression — *not* a mock; see `PLAN/08 §6`). | Development and target are both Linux (SANS SIFT / Ubuntu); the plan is authored on Windows but no code is built or run there, so Windows is not a constraint (see `PLAN/08 §0.1`). The in-process real tools install natively on Linux; the live agent needs an LLM at run time, while the recorded-golden artifacts reproduce with no API keys/network. |
| Δ6 | **Self-correction elevated to "the hero"** and engineered as a deterministic, reproducible sequence (not emergent). | "Autonomous Execution Quality / real-time self-correction" is the **designated tiebreaker**. A **deterministic engine over REAL tool output** guarantees it fires every demo run: a genuinely under-specified first-pass contract makes the real claim fail the Critic, and the tightened retry makes the 2nd real attempt pass. Determinism comes from real tools over fixed committed evidence with no LLM and no randomness (see `PLAN/08_REAL_TOOL_STACK.md §6`); emergent LLM correction is shown as an upgrade in the video. |
| Δ7 | **The live autonomous agent is the product headline (core)**; the deterministic path is the reliability *floor*, not the headline. | The point is a genuinely autonomous investigator that figures out a black-box dataset on its own (see `PLAN/01` / `PLAN/08 §6`). The live LLM agent is core and never cut; the deterministic governance + a recorded-golden run is the regression/safety-net floor. CAO is *one* optional harness; the simplest headless adapter (`claude -p`/OpenCode) is the core path. |
| Δ8 | **Hybrid Protocol-SIFT positioning** (optional SIFT-orchestration lane behind the same typed interface). | Aligns with the hackathon's "improve Protocol SIFT / how agents use SIFT tools" framing while keeping a portable, demoable core. |
| Δ9 | **A2A (Agent2Agent) added at the interop layer** as a new **Epic P** (Agent Card discovery + remote delegation, governed by an `x_siftmesh` policy overlay), with the protocol stack made explicit (MCP=tools, A2A=agents, CAO=local harness). | The original plan hand-maintained the agent registry and modeled only local agents. A2A standardizes discovery and unlocks remote/opaque agents — while SIFTMesh keeps all governance — strengthening the interop story without weakening constraints. **Optional / not MVP-mandatory.** |

---

## 3. Scope drivers (confirm against live sources before locking)

- **Deadline:** Jun 15, 2026, 11:45 PM EDT. Judging Jun 19–Jul 3. Prizes $22k ($10k / $7.5k / $4.5k).
- **6 judging criteria, equal weight** (see §4 matrix). Tiebreaker = **Autonomous Execution Quality** (self-correction).
- **8 mandatory submission artifacts** (see §6 and Epic N).
- **Environment:** must run on Linux / SANS SIFT Workstation (Ubuntu). Repo must be public with **MIT or Apache 2.0** license (we use **Apache 2.0**).
- **Reference bar:** Valhuntir (SANS). **Our lane:** image-based post-breach triage. **Our edge:** evidence/claim ledger + adversarial critic + deterministic state machine + replayable audit — a forensic policy layer *above* the harness.

---

## 4. Judging criteria → Epic matrix (every criterion has a primary owner)

| # | Criterion (equal weight) | Primary Epics | Supporting |
|---|---|---|---|
| 1 | **Autonomous Execution Quality** — real-time self-correction *(tiebreaker)* | **G** (critic/self-correction), **H** (state machine), **K** (real self-correction scenario) | F, J, M5 |
| 2 | **IR Accuracy** — hallucination mitigation, false-positive assessment | **C** (claim validators), **G** (critic), **J4** (accuracy report) | D9, K2, L4 |
| 3 | **Breadth & Depth** of analysis | **D** (8 typed tools), **E** (plan coverage), **K** (case realism) | I, J, N |
| 4 | **Constraint Implementation** — architectural, bypass-tested guardrails | **L** (threat model + bypass suite), **B** (path policy), **D** (forbidden-tool registry) | C, H caps, M4 |
| 5 | **Audit Trail Quality** — traceability, chain of custody, JSONL+timestamps | **B** (manifest/hashes), **D2** (audited exec), **J7** (replay) | C7 ledgers, H8, N8 |
| 6 | **Usability & Documentation** — deployment, extensibility | **N** (docs/runbook), **A**/**H** (clean CLI), **M6** (CI) | K5, J, O |

> If two submissions tie, criterion 1 decides — so the deterministic self-correction sequence (Epic G + K) is the highest-leverage investment in the plan.

---

## 5. Epic catalogue (A–P at a glance)

| Epic | Title | File | Effort | Criteria |
|---|---|---|---|---|
| A | Project Skeleton & Config | 02 | M | 6 |
| B | Evidence Vault & Run Directory | 02 | M | 4,5,2 |
| C | Schemas & Ledgers | 02 | M | 2,5,4 |
| D | Typed MCP Tool Gateway | 03 | L | 4,5,3 |
| E | Planner & Deep Context | 04 | M | 3,5,6 |
| F | Executor Adapters & Dispatch/Collect | 04 | M | 1,4,5 |
| G | **Critic & Self-Correction (HERO)** | 04 | L | 1,2,4,5 |
| H | Ultraworker State Machine & `run` | 04 | L | 1,4,5,6 |
| I | Agent Profiles & CAO Integration | 05 | M | 3,6 |
| J | Reports & Replay | 06 | L | 2,5,6 |
| K | Demo Case & Self-Correction Scenario | 06 | M | 1,2,3 |
| L | Security & Threat Model + Bypass Suite | 06 | L | 4,5,2 |
| M | Testing & CI | 07 | L | 4,5,6 |
| N | Documentation & Submission | 07 | M | 6,5 |
| O | Optional Ratatui TUI (deferred) | 07 | M | 6 |
| **P** | **A2A Interoperability Layer (stretch, > TUI)** | 05 | M | 3,4,6 |

---

## 6. The 8-artifact submission traceability matrix (go/no-go backbone)

Every row must be green to submit (owned in full by Epic N9 checklist).

| # | Mandatory artifact | Owning task | Produced file(s) |
|---|---|---|---|
| 1 | Public repo + MIT/Apache-2.0 license | A1 / N6 | `LICENSE` (Apache 2.0) |
| 2 | Demo video ≤5 min (live terminal + narration) | K5 / N7 | recorded video, `docs/demo_script.md` |
| 3 | Architecture diagram **with security boundaries** | L6 / N3 | `docs/diagrams/security_boundaries.*` |
| 4 | Written project description | N1 | `README.md`, `docs/project_description.md` |
| 5 | Dataset documentation | J5 / N4 | `docs/dataset_documentation.md` |
| 6 | Accuracy / false-positive report | J4 / N5 | `docs/accuracy_report.md` |
| 7 | Local-deploy instructions / working software | N2 / M6 | `docs/try_it_out.md`, `docs/judge_runbook.md` |
| 8 | Structured agent execution logs (JSONL + timestamps) | run output / N8 | `audit/*.jsonl`, `execution_logs_sample.md` |

---

## 7. Dependency graph (epic-level critical path)

```
A (skeleton/CI)
 └─> B (evidence vault, path policy) ──> L2 (path-policy spec)
       └─> C (schemas+ledgers, FREEZE) ──> J1/J2 (report loader + determinism)
             ├─> D (typed gateway) ──> L3 (forbidden-tool registry)
             │     └─> E (plan/tasks) ──> K1/K2 (demo evidence + ground truth)
             │           └─> F (real dispatch/collect) ──> K3 (real self-correction)
             │                 └─> G (critic + decide + retry) ──> L4 (evidence-as-hostile)
             │                       └─> H (run/modes/gates/caps/resume)
             ├─> I (profiles/adapters; CAO best-effort)        L1 (threat model, early/design)
             └─> L5 (bypass suite) ─────────────┐
J3..J7 + K3/K6 ──────────────────────────────┴─> M3/M5 (golden + e2e) ──> M6 (CI)
all J/K/L/M ──> N (docs) ──> N9 (GO/NO-GO) ──> SUBMIT
                               └─(gated on CLI stable)─> O (TUI)
```

**Critical chain:** A→B→C→D→E→F→**G**→H → K3 → J3 → M5 → N → N9 → submit. L and M attach to each node (threaded TDD). O hangs off the end and is the first legal cut.

---

## 8. 11-day schedule (MVP-first) with threaded security/testing

| Day | Date | Core focus | Threaded (L/M/J/K) | Cut-line if behind |
|---|---|---|---|---|
| 1 | Jun 4 | A: skeleton, Apache LICENSE, CLI stubs, run-dir, JSONL logger, Ubuntu-primary CI (= SIFT target) | L1 threat_model draft; M1 fixtures | — |
| 2 | Jun 5 | B: evidence vault, manifest, hashes, **path policy**, audit | L2 spec; M2 evidence/path tests | — |
| 3 | Jun 6 | C: schemas + ledgers — **freeze schemas** | J1 loader, J2 determinism; M2 schema tests | — |
| 4 | Jun 7 | D: real in-process tool gateway (`evtx`/`regipy`/`pyscca`/`mft`) + **forbidden-tool registry** | L3 spec; J5 dataset-doc gen | trim to 4 core tools |
| 5 | Jun 8 | E: plan/task generation; review-only | K1 demo evidence + K2 ground truth | — |
| 6 | Jun 9 | F: **deterministic real-tool dispatch/collect** | K3 real self-correction (under-specified→retry→corrected); M5 e2e skeleton | — |
| 7 | Jun 10 | G: critic + retry/escalate + report generators | L4 spotlighting; J3/J4 reports — **freeze the hero** | — |
| 8 | Jun 11 | H: `run` modes/gates/caps/resume | L5 bypass suite; J7 text replay; M2 mode tests | defer `replay.html` |
| 9 | Jun 12 | **Spine lock:** live autonomous-agent run + genuine self-correction; record the golden run; CI | M3 golden, M5 e2e, M6 CI; J6/J8 wiring | cut extra harnesses/CAO (keep the core `claude -p` agent) |
| 10 | Jun 13 | Hardening, coverage; N1/N3/N4/N6 + L6 diagram + N8 logs — **freeze code** | — | cut O (TUI), K4 injection event |
| 11a | Jun 14 | *No-code:* validate on the SANS SIFT VM (Linux-native); N2 try_it_out + judge_runbook; N5; N7 script | — | ship Ubuntu CI-Linux evidence if the local VM is unavailable |
| 11b | Jun 15 | *No-code:* record ≤5-min video; make repo public; **N9 go/no-go**; Devpost submit w/ buffer | — | submit minimum-winning even if polish slips |

**Cut order (first→last):** O (TUI) → **A2A / Epic P** → `replay.html` (keep text replay) → MCP tools beyond the core → optional prompt-injection demo event. **The live autonomous agent is NOT in the cut order — it is the product headline (core).** CAO and *extra* harnesses are optional (the simplest `claude -p`/OpenCode headless adapter is the core path); the deterministic governance + recorded-golden run is the regression/safety-net floor (also never cut). *(Build priority: **P1 core incl. the autonomous agent** > P2 CAO/extra harnesses > P3 A2A > P4 TUI — least-important cut first.)*
**Never cut:** the 8 artifacts · **the autonomous agent + its genuine self-correction** · the deterministic governance (critic/decide/evidence-safety) + the recorded-golden floor · the bypass suite.

---

## 9. Minimum winning submission (definition of done)

A **live autonomous-agent run** of
`siftmesh run ./examples/demo_case --evidence ./examples/demo_case/evidence --auto`
(and the `--auto-human-loop` variant for the video) — a real LLM agent investigates the **real demo evidence blind** with the real in-process tools (`evtx`/`regipy`/`pyscca`/`mft`; see `PLAN/08_REAL_TOOL_STACK.md`), governed by deterministic code — **plus a committed recorded-golden run** (its real ledgers) so the artifacts also reproduce on a fresh clone on Ubuntu/SANS SIFT with **no API keys and no network**. The run:

1. Produces every required run artifact (`evidence_manifest.json`, `tasks/*.yaml`, `results/*.json`, `claim_ledger.jsonl`, `unsupported_claims.jsonl`, `contradiction_ledger.jsonl`, `agent_calls.jsonl`, `tool_calls.jsonl`, `retries.jsonl`, `final_report.md`, `accuracy_report.md`).
2. Shows a visible, **genuine** self-correction — the agent forms a real unsupported/over-broad claim, the deterministic critic rejects it → ultraworker-retry with the critic's reason fed back → the agent corrects to an evidence-backed claim — with the unsupported claim appearing only in the rejected section (never as a fact).
3. Has the **bypass-test suite green** (write-escape blocked, forbidden tool un-exposable, injection logged-not-executed, evidence read-only, claim-without-`tool_call_id` rejected).
4. Satisfies **all 8 mandatory artifacts** (§6 + Epic N matrix + N9 checklist).

> **Evidence note.** The real demo evidence — host-triage artifacts (EVTX / prefetch / registry hive / `$MFT`) analyzed *on Linux* — is **maintainer-provided on the SANS SIFT workstation** and is therefore **integration-gated** (K1/K3/M3/M5; see `PLAN/08_REAL_TOOL_STACK.md §4`). Real evidence (not tool buildability) is the only gate; every backend installs natively on Linux. The in-process real tools themselves run **locally now with no API keys/network** and are independently testable against any small committed real artifact.

Everything else (live agents, CAO, **A2A interop (Epic P)**, `replay.html`, tools beyond the core four, injection demo event, TUI) is an **upgrade** and a **legal cut**.

---

## 10. Risk register

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Live self-correction varies / flaky in demo | Med | High (tiebreaker) | Self-correction is genuine/emergent (live agent + deterministic critic). Mitigate with a **recorded-golden run** (real ledgers) as the demo safety net + deterministic governance; tests assert **properties** (≥1 genuine self-correction), byte-exact only vs the recorded golden (`PLAN/08 §6`) | K3, M5 |
| R2 | Reports non-deterministic → golden tests flap | Med | Med | J2 determinism contract (UTC, sorted, header-segregated); M3 enforces | J2, M3 |
| R3 | Linux-native breakage surfaces late on the SIFT target | Low | Med | Dev + target are both Linux (SANS SIFT / Ubuntu), so there is no cross-OS gap; `pathlib` discipline; Ubuntu-primary CI from Day 1–2; SANS SIFT VM validation Day 11a | M6, N2 |
| R4 | A submission artifact missed | Low | Fatal | 8-artifact matrix + N9 go/no-go | N |
| R5 | Live-agent harness fragility (env-dependent) — now **core** | High | High | The autonomous agent is core, so don't depend on a heavy harness: the simplest headless adapter (`claude -p`/OpenCode) is the core path; CAO + extra harnesses are optional; the recorded-golden run + deterministic governance is the floor if a live run fails in the room | I, roadmap |
| R6 | Bypass test asserts prompt text not behavior (false security) | Med | High (crit. 4) | Tests assert the code gate's *effect*; "LLM proposes/code decides" | L5, M4 |
| R7 | Project-license requirement (public repo must be MIT/Apache-2.0) not met | Low | Med | Keep `LICENSE` = Apache-2.0; do **not copy source** from restrictive projects. Tool/connector licenses are **not a blocker** — runtime deps are replaceable (see `PLAN/08 §0.1`, §5) | N6 |
| R8 | Video/submission friction on Jun 15 | Med | Fatal | Two no-code days reserved with buffer | N7, roadmap |
| R9 | Scope creep (TUI/web/extra tools) | Med | Med | Cut-line invariant + explicit cut order; O gated on CLI-stable | roadmap, O |
| R10 | Overclaiming court-ready forensic soundness | Low | Med (credibility) | Explicit non-goal in report limitations + `evidence_integrity.md` | J3, N4 |
| R11 | A scope-driver fact (deadline/rubric) shifted on the live site | Low | High | Re-confirm `findevil.devpost.com/rules` before Day 1 schedule lock | — |
| R12 | A2A adds complexity / a new remote-agent attack surface | Med | Med | A2A is optional stretch (Epic P), cut before it touches the hero; remote agents **untrusted-by-default**, gated by conformance + policy overlay; output governed by the critic — surface already contained | Epic P, L |

---

## 11. Product roadmap (post-hackathon — first-class)

Phased beyond Jun 15; each phase a one-line goal. These are explicitly **out of the 11-day MVP** and exist so the architecture's extensibility is legible.

| Phase | Goal | Builds on |
|---|---|---|
| **R1 — Gated-backend hardening** | Harden the gated SIFT-lane / Plaso upgrade backends (EvtxECmd / PECmd / Plaso / MFTECmd / Volatility-3, behind the same typed interface as the shipped real in-process tools; see `PLAN/08_REAL_TOOL_STACK.md §4`), each with golden-output tests and digest/version pinning. | Epic D |
| **R2 — Full SIFT-lane orchestration** | Drive the real 200+ SIFT / Protocol-SIFT tools on the SANS SIFT Workstation behind the same typed interface; inherit/extend Protocol SIFT skills. | Epics D, I |
| **R3 — Live-agent & A2A integration** | Harden headless Claude Code / OpenCode / Codex / Gemini adapters + CAO; real cost-based Budget Router; parallel multi-agent fan-out; **graduate A2A** (Epic P) from discovery-only to full delegation + exposing SIFTMesh agents as A2A servers. | Epics F, I, **P**, H |
| **R4 — Artifact breadth** | Add Amcache/ShimCache, USN Journal ($J), WMI-persistence, SRUM, ShellBags, browser-history parsers; **Sigma-rule detection** (rules as data, license-clean). | Epics D, E |
| **R5 — Scale & search** | OpenSearch / Timesketch evidence indexing for retrieval-augmented planning over large multi-host cases. | Epics B, E, J |
| **R6 — Operator UX & distribution** | Ratatui TUI cockpit (Epic O graduated); PyPI packaging, container image, signed releases, plugin SDK for custom tools/adapters. | Epics O, A |

---

## 12. Cross-references

- Architecture, layers, security boundaries, full repo tree → `01_ARCHITECTURE.md`.
- Per-Epic task tables → files `02`–`07`.
- Source guidance honored throughout: `CLAUDE.md` (§4 commands, §5 run-dir, §6 safety, §9–12 claim/critic/autonomy, §14 tests), `GUIDELINES.md`, `PROJECT_CONTEXT.md`, `AGENT.md`.

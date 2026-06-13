# SIFTMesh: Project Story

## What it does

SIFTMesh is a **CLI-first, evidence-safe controller for autonomous DFIR**. You point it at real
forensic evidence (a disk image, a memory capture) and an incident objective. It hashes and seals the
evidence read-only, plans the investigation, sends an agent to work the case, and runs a **deterministic
critic** that checks every claim against actual tool output before it can become a reported finding. The
governing principle is **"the LLM proposes; the code decides."**

Against the provided **ROCBA** dataset (a 23.7 GB Windows disk image plus a 19 GB memory capture) it ran
**19 real typed forensic tools**: Sleuth Kit, Volatility 3, Plaso, evtx, regipy, prefetch, `$MFT`,
registry, browser history, LNK/JumpLists, shellbags, Amcache/ShimCache, and the USN journal. It
produced **634 evidence-anchored claims (0 unsupported, 0 contradictions)** that materially answer the
brief's five questions. Stolen **ADAMANTIUM** research was exfiltrated to a **personal Google Drive** and
**USB**, with **SDelete** plus **47,966 USN deletions** as cleanup, on a **5.7 M-event super-timeline**.
Every finding cites the `tool_call_id` and the SHA-256 of the bytes it came from
([`findings_rocba.md`](findings_rocba.md), [`execution_logs_sample.md`](execution_logs_sample.md)).

## How we built it

Python throughout: a **Typer** CLI, **Pydantic** schemas, a **deterministic finite-state machine** for
the engine (`plan → dispatch → critique → decide → report`), and append-only **JSONL ledgers** for
claims, contradictions, and the full audit trail. The agent reaches forensic tools through a typed
**MCP** boundary whose allowlist is a single `frozenset` of 19 names. There is no raw shell and no
arbitrary code. The key design decisions and tradeoffs:

- **Autonomy in the agent; determinism in the governance.** The agent investigates freely, but code
  makes every security-relevant decision (what counts as a fact, what tool may run, where a file may be
  written), and that code runs regardless of which agent drives: Claude, OpenCode, Gemini, Codex, or the
  no-keys **deterministic floor**. We kept a native FSM instead of a generic graph framework (ADR
  PLAN/12) because typed state, `decide()`, and a resumable `run_state.json` already give the value
  without re-introducing nondeterminism.
- **A recorded-golden floor as the safety net.** The deterministic real-tool run is byte-reproducible
  and golden-tested, so the demo and the regression suite never depend on a flaky live model.
- **Agent-neutral, headless-first.** Adding an agent is a profile row, not a new adapter. Only Claude
  reaches the typed tools today, and the others are honestly labelled unconstrained opt-ins.

## Challenges

- **Making autonomy safe without trusting the prompt.** A prompt that says "don't touch the evidence"
  is not a control. We put the guardrails in the gate the model's output must pass through: read-only
  evidence with hash-before-analysis, a `safe_write_path` write-jail, the tool allowlist, and a critic
  that rejects any claim lacking a real anchor.
- **Forensic evidence is hostile input.** Real artifacts contain strings that look like instructions,
  and this run flagged **3,949** injection-like strings. We treat evidence as data, never as
  instructions (raw bytes never enter a prompt; only `{path, sha256}` rows do), log every alert, and let
  the critic force human-review on any affected claim. The honest claim is **containment plus
  traceability, not prevention.**
- **Real evidence breaks tools in real ways.** Two failures only a live run could surface: (1) the
  ROCBA image is a **partial/sparse acquisition** whose VSS backup header is unreadable, which crashed
  Plaso's volume scan, so we added a recorded fallback that builds the timeline over the extracted
  artifacts (still 5.7 M events); (2) `Security.evtx` is **genuinely LZNT1-corrupt**, failing
  identically across three independent NTFS implementations, so we **fail closed**, record it in
  `failed[]`, and never fabricate a result. We document both as signal rather than hide them.
- **Streaming real-time logs without breaking determinism.** Operators wanted a live tagged log, while
  golden tests require byte-identical run dirs. We tapped the two ledger chokepoints after the durable
  write and stream only to stderr, so the terminal lights up while the committed bytes never change.

## What we learned

- **Evidence-safety has to be architectural.** Anything enforced only by a prompt fails the moment the
  model ignores it. The only durable controls are the ones in code that run no matter what the agent
  does. That reframing (guardrails in the gate, not the prompt) drove the whole design.
- **Honest gaps are a feature.** A corrupt log, a partial image, a tool that cannot run: documenting
  the failure mode is stronger than papering over it, and it is what a forensic examiner trusts.
- **The right split is autonomous proposal plus deterministic adjudication.** Let the model be creative,
  and let the code be the one that decides truth, safety, and what reaches the report.

## What's next

- **A2A** agent-to-agent interop (optional, governed by the SIFTMesh policy overlay).
- **ACP round 2** so Gemini/Codex reach the typed tools (only Claude does today).
- **Sigma / pySigma** detection breadth.
- **Phase D** parsers: Outlook OST / OneDrive ODL (deferred until a clean Linux parse is confirmed).
- **SRUM** per-app network bytes (no viable parser on this host yet).

---

*Repository: Apache-2.0. Architecture plus trust boundaries: [`architecture.md`](architecture.md) and
[`threat_model.md`](threat_model.md). Try it: [`try_it_out.md`](try_it_out.md). All eight submission
components: [`submission.md`](submission.md). The full committed ledgers for both runs are at
`docs/logs/rocba-disk-RUN-20260612-163324/` and `docs/logs/rocba-memory-RUN-20260612-082630/`.*

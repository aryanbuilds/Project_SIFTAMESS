# SIFTMesh — Project Story

## What it does

SIFTMesh is a **CLI-first, evidence-safe controller for autonomous DFIR**. You point it at real
forensic evidence (a disk image, a memory capture) and an incident objective; it hashes and seals the
evidence read-only, plans the investigation, sends an agent to work the case, and uses a **deterministic
critic** to check every claim against actual tool output before it can become a reported finding. The
governing principle is **"the LLM proposes; the code decides."**

Against the provided **ROCBA** dataset (a 23.7 GB Windows disk image + a 19 GB memory capture) it ran
**19 real typed forensic tools** — Sleuth Kit, Volatility 3, Plaso, evtx, regipy, prefetch, `$MFT`,
registry, browser history, LNK/JumpLists, shellbags, Amcache/ShimCache, and the USN journal — and
produced **634 evidence-anchored claims (0 unsupported, 0 contradictions)** that materially answer the
brief's five questions: stolen **ADAMANTIUM** research exfiltrated to a **personal Google Drive** and
**USB**, with **SDelete** + **47,966 USN deletions** as cleanup, on a **5.7 M-event super-timeline**.
Every finding cites the `tool_call_id` and the SHA-256 of the bytes it came from
([`findings_rocba.md`](findings_rocba.md), [`execution_logs_sample.md`](execution_logs_sample.md)).

## How we built it

Python throughout — **Typer** CLI, **Pydantic** schemas, a **deterministic finite-state machine** for
the engine (`plan → dispatch → critique → decide → report`), and append-only **JSONL ledgers** for
claims, contradictions, and the full audit trail. The agent reaches forensic tools through a typed
**MCP** boundary whose allowlist is a single `frozenset` of 19 names — no raw shell, no arbitrary code.
Key design decisions and tradeoffs:

- **Autonomy in the agent; determinism in the governance.** The agent freely investigates, but every
  security-relevant decision (what's a fact, what tool may run, where a file may be written) is made by
  code that runs *regardless of which agent drives* — Claude, OpenCode, Gemini, Codex, or the no-keys
  **deterministic floor**. We kept a native FSM instead of a generic graph framework (ADR PLAN/12)
  because typed state + `decide()` + a resumable `run_state.json` already give the value without
  re-introducing nondeterminism.
- **A recorded-golden floor as the safety net.** The deterministic real-tool run is byte-reproducible
  and golden-tested, so the demo and the regression suite never depend on a flaky live model.
- **Agent-neutral, headless-first.** Adding an agent is a profile row, not a new adapter; only Claude
  reaches the typed tools today (others are honestly labelled unconstrained opt-ins).

## Challenges

- **Making autonomy safe without trusting the prompt.** A prompt that says "don't touch the evidence"
  is not a control. We put the guardrails **in the gate the model's output must pass through**:
  read-only evidence + hash-before-analysis, a `safe_write_path` write-jail, the tool allowlist, and a
  critic that rejects any claim lacking a real anchor.
- **Forensic evidence is hostile input.** Real artifacts contain strings that look like instructions —
  this run flagged **3,949** injection-like strings. We treat evidence as data, never as instructions
  (raw bytes never enter a prompt; only `{path, sha256}` rows do), log every alert, and let the critic
  force human-review on any affected claim. The honest claim is **containment + traceability, not
  prevention.**
- **Real evidence breaks tools in real ways.** Two failures only a live run could surface: (1) the
  ROCBA image is a **partial/sparse acquisition** whose VSS backup header is unreadable, which crashed
  Plaso's volume scan — we added a recorded fallback that builds the timeline over the *extracted*
  artifacts (still 5.7 M events); (2) `Security.evtx` is **genuinely LZNT1-corrupt**, failing
  identically across three independent NTFS implementations — so we **fail closed**, record it in
  `failed[]`, and never fabricate a result. Both are documented as signal, not hidden.
- **Streaming real-time logs without breaking determinism.** Operators wanted a live tagged log; golden
  tests require byte-identical run dirs. We tapped the two ledger chokepoints *after* the durable write
  and stream only to stderr — so the terminal lights up while the committed bytes never change.

## What we learned

- **Evidence-safety has to be architectural.** Anything enforced only by a prompt fails the moment the
  model ignores it; the only durable controls are the ones in code that run no matter what the agent
  does. That reframing ("guardrails in the gate, not the prompt") drove the whole design.
- **Honest gaps are a feature.** A corrupt log, a partial image, a tool that can't run — documenting
  the failure mode is stronger than papering over it, and it's exactly what a forensic examiner trusts.
- **The right split is autonomous proposal + deterministic adjudication.** Let the model be creative;
  let the code be the one that decides truth, safety, and what reaches the report.

## What's next

- **A2A** agent-to-agent interop (optional, governed by the SIFTMesh policy overlay).
- **ACP round 2** so Gemini/Codex reach the typed tools (only Claude does today).
- **Sigma / pySigma** detection breadth.
- **Phase D** parsers: Outlook OST / OneDrive ODL (deferred — confirm a clean Linux parse first).
- **SRUM** per-app network bytes (no viable parser on this host yet).

---

*Repository: Apache-2.0. Architecture + trust boundaries: [`architecture.md`](architecture.md) +
[`threat_model.md`](threat_model.md). Try it: [`try_it_out.md`](try_it_out.md). All eight submission
components: [`submission.md`](submission.md).*

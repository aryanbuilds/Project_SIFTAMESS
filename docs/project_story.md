# SIFTMesh: Project Story

## Inspiration

- Got handed a real insider-theft case (ROCBA): one suspect, a 23 GB disk, a 19 GB memory dump, and 5 questions I actually had to answer.
- Two options, both bad: work it by hand and age ten years, or unleash an AI agent and pray it doesn't invent a culprit. In forensics, a confident wrong answer is worse than "I don't know."
- So I went for door three: **the LLM proposes, the code decides.** Speed of an agent, spine of a deterministic pipeline.

## What it does

- CLI-first, evidence-safe controller for autonomous DFIR. Give it evidence and a question; it does the work and shows its receipts.
- Seals evidence read-only (SHA-256), plans, sends an agent in, and a **deterministic critic** fact-checks every claim against real tool output before it's allowed to be a "finding."
- Drives **19 real forensic tools** (Sleuth Kit, Volatility 3, Plaso, evtx, regipy, prefetch, `$MFT`, registry, browser, LNK, shellbags, Amcache/ShimCache, USN). No mocks, no vibes.
- On the real ROCBA evidence: **634 findings, 0 unsupported, 0 contradictions.** It basically caught the guy: ADAMANTIUM research siphoned to a personal Google Drive and a USB, then SDelete and ~48K USN deletions to cover the tracks, all on a 5.7M-event timeline.
- Every finding links back to the exact tool call and the hash of the bytes it came from. Trust, but verify - and here you can actually verify.

## How we built it

- Python: a Typer CLI, Pydantic schemas, a deterministic state machine (`plan → dispatch → critique → decide → report`), and JSONL ledgers for everything.
- The agent only touches tools through an MCP allowlist of exactly 19 names. No raw shell. (It asked to run "just one bash command." The answer was no.)
- Core: an evidence vault, a write-jail so nothing escapes the run dir, a critic that's the **only** thing allowed to bless a finding, and a state machine that decides retry / escalate / human-review.
- Stuff I bolted on while using it and getting annoyed:
  - **Minimal TUI** - the cockpit was bloated, so I trimmed it to the stuff I actually look at.
  - **Real-time logs by default** - tagged `[info] [agent] [tool_log] [alert] [result] [tasks]`, per task, with a live % so I'm not staring at a frozen screen wondering if it died.
  - **Auto-parallel for live agents** - watching one run tasks one at a time was painful, so now it parallelizes itself.

## Challenges we ran into

- **Plaso refused to cooperate.** The disk is a partial acquisition whose shadow-copy header points 81 GB into a 23 GB file (sure). It crashed even when told to skip VSS. I ran it over the extracted artifacts instead and still got 5.7M events.
- **A genuinely corrupt event log.** `Security.evtx` died in three different NTFS readers at the same spot. For once, not my bug. I made it fail closed and say so instead of faking it.
- **The agent went rogue and the critic caught it red-handed.** Testing parallel `claude_headless` plus an OpenCode judge, every run came back unparseable. I opened the raw output and the agent had wandered into a *different conversation*: reaching for Bash, hitting "Request interrupted by user," and literally echoing my own "wait, is this prompt injection?" rant back at me. I thought the evidence had pwned it. Nope. The critic had already thrown the whole mess out; the real bug was session isolation (headless Claude inherited my env with no pinned session, so a live session bled in). Fixed with a fresh session id, no persistence, and a minimal env.
- **Evidence is hostile.** 3,949 strings tried to look like instructions. I log all of them and run none. Honest pitch: containment, not "we solved prompt injection" (nobody has).
- **The small, real, dumb ones:** the brief field kept only a filename instead of the full path; my workstation hit 94% disk and started gasping (freed ~61 GB with prune / portions / merge); and I found my own GitHub token loitering in the git remote URL and rotated it before it caused trouble.

## Accomplishments that we're proud of

- A real autonomous run that answered all 5 questions: **634 findings, none unsupported, none contradictory**, every one traceable to a tool call and a hash.
- A critic that actually did its job and tossed a misbehaving live agent instead of trusting it.
- I left the failures **in** (corrupt log, partial timeline). Honesty over polish.
- Evidence came out untouched: the end hash matched the ingest seal.
- Determinism I can prove: parallel == sequential, byte for byte, and a golden run reproduces it with zero keys.

## What we learned

- **Safety has to be in the code, not the prompt.** "Please don't touch the evidence" is a wish, not a control. The guardrails live in the gate the agent's output has to pass through.
- **The agent will surprise you** - so the whole game is the governance that catches the surprise (see: rogue agent reading my diary, above).
- **Honest gaps are a feature.** A documented "this is corrupt" beats a confident lie every time.
- The split that kept working: **agent proposes, code decides.**

## What's next for SIFTMESH

- **A2A** so remote agents play by the same rules.
- **ACP round 2** so Gemini and Codex reach the typed tools (only Claude does today).
- **Sigma / pySigma** for more detections.
- Deferred parsers (**Outlook OST**, **OneDrive ODL**) once a clean Linux parse exists, plus **SRUM** for per-app bytes.
- Smarter low-disk handling so my workstation stops gasping.

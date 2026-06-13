# Accuracy & False-Positive Report: ROCBA

SIFTMesh generated this report (`siftmesh report`, no LLM at report time) from the real **19-tool** run against
the ROCBA disk image, `RUN-20260612-163324` over `rocba-cdrive.e01`
(sha256 `f2eb856d6fb48e3928e6b6d388b2f116a57b735137354a7eaddca951d81b5c67`). The findings summary lives in
[`findings_rocba.md`](findings_rocba.md). No ground-truth answer key was supplied, so this is an
**honest self-assessment**. SIFTMesh never fabricates precision/recall.

## Results summary

- Confirmed findings: **220**
- Inferred findings: **414**
- Unsupported (rejected, never reported as fact): **0**
- Contradictions detected: **0**
- Critic confidence downgrades: **0**
- Critic verdicts (across tasks + self-correction iterations): **44 accepted · 14 human_review_required
  · 5 retry_required** (63 total over 25 tasks). A flag is not a fabrication: the critic surfaces a `human_review_required` task for an analyst and quarantines it in `--auto` (its claims never become facts), while `retry_required`
  drives the self-correction loop. TASK-002 cycled through retries; the firewall held (0 unsupported).

## Confidence distribution (final, post-critic)

| Confidence band | Findings |
| --- | --- |
| 0.90-1.00 | 204 |
| 0.70-0.89 | 372 |
| 0.50-0.69 | 58 |
| 0.00-0.49 | 0 |

## Corroboration

- Multi-claim groups (≥2 claims on the same artifact + type): **204**
- Single-source groups (lower confidence by construction): **219**

## False-positive control (the hallucination firewall)

- Claims rejected for missing evidence anchor: **0**. Appendix B
  of the run's `final_report.md` confines any such claim, which never gets asserted as fact.
- Over-broad claims downgraded by the critic: **0**.
- Contradictions escalated rather than asserted: **0**.
- Prompt-injection-like evidence strings flagged + logged (never executed): **3,949**. This 19-tool run
  parsed far more text: a 5.7 M-event super-timeline, 383 K USN records, and a 479 K-file `$MFT`, so many
  more strings pattern-matched instruction-like text. SIFTMesh logs each one and executes none.

## Coverage

- Coverage / derived follow-ups raised: **23** (the `--auto` derived-gap loop re-ingesting carved
  hives/journals into the plannable set).
- Manifest artifacts with no finding: **0**. The sealed manifest's sole artifact, the `.E01`, produced
  findings. Separately, the *derived* `Security.evtx` failed extraction with a genuine TSK LZNT1
  NTFS-decompression error, recorded in `failed[]`, reported honestly, never fabricated.

## Memory triage (companion run)

`RUN-20260612-082630` over `Rocba-Memory.raw` (sha256 `eb33bdf6…`): Volatility 3 ran all 6 plugins
(`windows.info/pslist/pstree/netscan/cmdline/malfind`), **0 failed**. The run recorded 2,186 processes, 430 network
endpoints, and 16 `malfind` RWX regions flagged for review. Most of those regions belong to system processes, so SIFTMesh does not assert them
as malicious. See [`findings_rocba.md`](findings_rocba.md).

## Method & limitations

- Deterministic real tools run over real evidence; every promoted claim anchors to a `tool_call_id` +
  `source_sha256`. The Tier-1 critic is the sole promoter.
- Treat this as **automated triage to guide an analyst, not a court-ready conclusion.** Confidence values
  are heuristic, and absence of a finding is not proof of absence.
- Full ledgers + replay live in the run dirs (uncommitted per CLAUDE.md §2B); reproduce via
  [`dataset_documentation.md`](dataset_documentation.md). The committed full ledgers for both runs are checked in under [`docs/logs/rocba-disk-RUN-20260612-163324/`](logs/rocba-disk-RUN-20260612-163324/) and [`docs/logs/rocba-memory-RUN-20260612-082630/`](logs/rocba-memory-RUN-20260612-082630/).

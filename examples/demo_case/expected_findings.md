# Expected findings - demo case (ground truth)

This is the K2 ground-truth baseline for `examples/demo_case`. When this file is present, the
accuracy report (`siftmesh report`) switches to **diff mode** (precision/recall vs these facts)
instead of an honest self-assessment.

The evidence is `evidence/Security.evtx` (7 Windows Security event records, public `evtx` test
fixture). The facts below are deterministically verifiable by the real `parse_evtx_security` backend.

## Must find (true positives)

- **7 Security events parsed** from `Security.evtx` (the full record count).
- **A failed-logon event - EventID 4625** is present in the log.
- A **unified timeline** is built spanning the parsed events (1 source).

Every reported finding MUST be anchored to a real tool call (`tool_call_id` + `source_sha256` of
`Security.evtx`). On the deterministic floor this produces, in `claims/claim_ledger.jsonl`:

| Claim | Status | Anchored to |
| --- | --- | --- |
| Parsed 7 Security event(s) | confirmed | `parse_evtx_security` → `Security.evtx` |
| Security EventID 4625 (failed logon) observed | confirmed | `parse_evtx_security` → `Security.evtx` |
| Unified timeline built (7 events, 1 source) | inferred | `build_timeline` |

## Must NOT report (false-positive control)

- **No incident-level conclusion** (e.g. "the host was compromised") - the evidence is a 7-record
  sample with no such support; an executor must not assign final severity.
- **No claim without a `tool_call_id` + `source_sha256`** may appear as a fact. An unanchored claim
  must be rejected by the critic and confined to Appendix B (unsupported) of the report - never the
  findings body. This is the hallucination firewall.
- **No invented EventIDs / hosts / timestamps** beyond what the tool actually returned.

## Notes

- This is a deliberately small, synthetic fixture for a fast, key-free demo - not a full incident.
  The point is to prove the *governance* (anchoring, the critic gate, replayable audit), not breadth.
- The richer ROCBA disk/memory walkthrough (real 22.6 GB image, live agent) is maintainer-gated and
  documented in `RUNBOOK.md` (§2B - never run autonomously against real evidence).

# Accuracy & False-Positive Report

> **Provenance.** A committed copy of SIFTMesh's **deterministic, code-generated** accuracy report
> (no LLM at report time), from the golden regression run (`tests/golden/recorded_run/RUN-GOLDEN`).
> With no `expected_findings.md` baseline it is an **honest self-assessment** — it never fabricates
> precision/recall. When a case ships ground truth (e.g. `examples/demo_case/expected_findings.md`)
> the same generator switches to **diff mode** (true/false positives vs the baseline). Regenerate at
> `case_runs/RUN-*/reports/accuracy_report.md`.

---

# Accuracy & False-Positive Report — RUN-GOLDEN

_No ground-truth baseline — honest self-assessment (no fabricated precision/recall)._

## Results summary

- Confirmed findings: 5
- Inferred findings: 2
- Unsupported (rejected, not facts): 0
- Contradictions detected: 0
- Confidence downgrades by critic: 0

## Confidence distribution (final, post-downgrade)

| Confidence band | Findings |
| --- | --- |
| 0.90-1.00 | 3 |
| 0.70-0.89 | 3 |
| 0.50-0.69 | 1 |
| 0.00-0.49 | 0 |

## Corroboration

- Multi-claim (corroborated ≥2 on same artifact+type) groups: 3
- Single-source finding groups: 1 (lower confidence by construction)

## False-positive control

- Claims rejected by the critic for missing evidence: 0 (never reported as fact — Appendix B of the
  final report).
- Over-broad claims downgraded: 0.
- Contradictions escalated rather than asserted: 0.

## Coverage gaps

- Coverage/derived follow-ups raised: 0.
- Manifest artifacts with no finding: 0.

## How accuracy is enforced (not just measured)

The numbers above are a *consequence* of the architecture, not a claim about it:

- **Hallucination firewall** — a claim without a `tool_call_id` + `source_sha256` cannot be a
  `confirmed`/`inferred` fact (Pydantic validator + the deterministic critic). Rejected claims live
  only in Appendix B.
- **Executors never assign final severity** — incident-level conclusions are out of an executor's
  scope; the critic downgrades over-broad claims.
- **Contradictions are escalated, not asserted** — two artifacts that disagree raise a contradiction
  record rather than a confident finding.
- **Honest by default** — with no ground truth, SIFTMesh reports a self-assessment instead of
  inventing precision/recall (this report). The bypass suite (`tests/EPIC_L_TESTS/`, 80+ effect
  tests) proves each gate fires on hostile input.

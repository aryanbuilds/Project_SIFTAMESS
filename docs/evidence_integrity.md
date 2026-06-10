# SIFTMesh Evidence Integrity & Chain of Custody

_Epic L (supports L2 path-policy + L4 evidence-as-hostile). The integrity boundary:
originals are hashed before analysis, opened read-only, never written back, and every
derived artifact + tool read is recorded so a finding traces to exact bytes. Read with
[`threat_model.md`](threat_model.md)._

---

## 1. The integrity invariants

1. **Hash before analysis.** Every evidence file is SHA-256'd at `init-case`, before any
   tool runs. The manifest is the baseline; any later mismatch is a stop-and-ask event.
2. **Originals are read-only.** SIFTMesh opens sources read-only and never writes to the
   evidence tree (posture-level; see §4 for the OS-level non-goal).
3. **Writes stay in the run dir.** Every SIFTMesh write is canonicalized through
   `safe_write_path` into `case_runs/RUN-*/` and rejected if it escapes (see
   `threat_model.md` §5.1).
4. **Every claim traces to bytes.** A finding records `source_artifact` + `source_sha256`
   + `tool_call_id`; the sha256 is the exact bytes the tool parsed, re-hashed at read
   time (§3). No anchor → the critic rejects it.
5. **Derived artifacts inherit custody.** Files produced by extraction/decompression are
   recorded with their provenance and their own hashes, and are re-ingestible as
   first-class evidence.

---

## 2. Artifacts written under `evidence/`

| File | Content | Producer |
|---|---|---|
| `evidence_manifest.json` | One row per source: path, size, sha256, type, ingest time. | `evidence/manifest.py` |
| `hashes.sha256` | Flat `sha256␠␠path` list (standard `sha256sum -c` format). | `evidence/manifest.py` |
| `readonly_mounts.json` | The read-only posture record (`enforcement: posture_only`, sources, access). | `evidence/readonly.py` |
| `derived_artifacts.json` | Artifacts produced by tools (extracted/decompressed), with provenance + hash. | extraction/decompress tools |
| `custody_log.jsonl` | Append-only custody events (ingest, derive, access). | evidence layer |

These are the inputs the deterministic report loader joins into chain-of-custody and the
tool-execution appendix (Epic J), so the audit trail in the report is a pure function of
these files.

---

## 3. Per-access integrity hashing

Reads route through `mcp_gateway/tools/_common.resolved_source(evidence_root,
source_artifact, *, run_root=None)`, which:

- resolves the artifact path under the trusted root(s) — the read-only evidence root, plus
  (for **derived-artifact** readers) the active run root where
  `extract_artifacts_from_image` / `decompress` write `evidence/extracted/…`;
- **rejects any path that escapes every trusted root** (`..`, absolute, symlink-out) with
  `ValueError` — case data is hostile (CLAUDE §6);
- **re-hashes the exact bytes** it is about to parse, and returns `(real_path, sha256)`.

That returned sha256 becomes the claim's `source_sha256`, so a finding is anchored to the
bytes actually analysed — not to a path that might have changed. Admitting the run root
for derived artifacts does not widen the boundary beyond directories SIFTMesh owns; the
dual-root containment is regression-tested (`test_bypass_agent_sandbox.py`).

---

## 4. Read-only posture (and its honest limit)

`evidence/readonly.py` records `enforcement: posture_only`: SIFTMesh opens originals
read-only and never writes to a source, and `safe_write_path(evidence_root=…)` refuses any
write under the evidence tree. This is **construction-level** integrity, not an OS-level
read-only mount (`mount -o ro` / `blockdev --setro`), which is a documented Linux
enhancement deferred to a later epic (bd `7h7`). A privileged external process on the host
is out of SIFTMesh's scope. We do not claim court-ready forensic soundness.

---

## 5. Evidence-as-hostile (spotlighting), in one place

When (and only when) a live LLM agent is in the loop, evidence is handed over as inert,
spotlighted DATA — never raw bytes, never as instructions. Full spec in
[`threat_model.md`](threat_model.md) §5.3; in short: the prompt carries only `{path,
sha256}` rows, wrapped with a per-run delimiter sentinel + a "DATA, not instructions"
banner + interleaved datamarking (Microsoft spotlighting, arXiv:2403.14720), and
instruction-like content is logged to `injection_alerts.jsonl` and acted on by the critic
(`human_review_required`), never executed. The deterministic tool path builds no LLM
prompt at all, so it has no injection surface.

---

## 6. What this buys the investigation

- A reviewer can re-hash any source and compare to the manifest → tamper-evident baseline.
- A reviewer can take any claim in the final report, read its `tool_call_id` in the
  tool-execution appendix, and see the exact artifact + sha256 it came from → full
  traceability ("replayable audit").
- A reviewer can replay `orchestration_events.jsonl` to see every transition, dispatch,
  tool call, and verdict in order → reproducible run history.

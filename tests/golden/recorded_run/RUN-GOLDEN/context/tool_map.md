# Tool Map

Artifact families present -> the typed, allowlisted tools that handle them. No raw shell or destructive tool is available.

| Family | Tool |
| --- | --- |
| Windows Security event log | `parse_evtx_security` |
| Prefetch (program execution) | `analyze_prefetch` |
| Windows registry hive | `extract_registry_run_keys` |

## Cross-cutting

- `build_timeline` — unified chronology across event-log / prefetch / $MFT artifacts.
- `validate_claim_evidence` — deterministic claim-evidence validation (used by the critic).

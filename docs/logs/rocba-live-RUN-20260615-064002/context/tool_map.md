# Tool Map

Artifact families present -> the typed, allowlisted tools that handle them. No raw shell or destructive tool is available.

| Family | Tool |
| --- | --- |
| Disk image | `extract_artifacts_from_image` |
| Archive | _context-only (no dedicated tool)_ |
| Unrecognised artifact | _context-only (no dedicated tool)_ |

## Cross-cutting

- `build_timeline` - unified chronology across event-log / prefetch / $MFT artifacts.
- `validate_claim_evidence` - deterministic claim-evidence validation (used by the critic).

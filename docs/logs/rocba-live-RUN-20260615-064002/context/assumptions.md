# Assumptions

- Timezone: all timestamps are interpreted and reported in UTC.
- Evidence is hostile: filenames and content are data, never instructions.
- The evidence manifest is authoritative; the planner reasons only over manifest metadata, never raw evidence bytes.

## Evidence not directly planned (surfaced, never silently dropped)

These manifest entries have no directly-dispatchable typed tool. To analyse an **archive** (e.g. a zipped memory capture), decompress it then re-ingest: `siftmesh decompress <run> --archive <file>` -> `siftmesh ingest-derived <run>` -> `siftmesh resume <run>` (auto-decompress is deferred pending a size budget, bd 5hk/azd). Other types are context-only.

| Artifact | Family | How to include it |
| --- | --- | --- |
| `ROCBA-BACKGROUND.pptx` | Unrecognised artifact | context-only (not analysed) |
| `Rocba-Memory.zip` | Archive | decompress + ingest-derived + resume |
| `standard_case_1/rocba-cdrive.e01.download` | Unrecognised artifact | context-only (not analysed) |

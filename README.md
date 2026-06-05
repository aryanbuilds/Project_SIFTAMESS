# SIFTMesh

CLI-first, evidence-safe, agent-agnostic orchestration layer for autonomous DFIR
on SANS SIFT and Protocol SIFT.

## Quickstart (uv-managed; do not use pip/venv)

```bash
uv sync                  # installs deps + dev group (ruff/mypy/pytest)
uv run siftmesh --help   # CLI = source of truth
uv run ruff check .
uv run mypy siftmesh_core
uv run pytest
```

Optional forensic backends (opt-in; fail closed if missing):

```bash
uv sync --extra sift     # evtx, libscca-python, mft
uv sync --extra a2a      # a2a-sdk
```

License: Apache-2.0.

"""Run-directory generator (A4).

Every run's state lives under one inspectable directory ``case_runs/RUN-*`` with
a fixed subtree (CLAUDE.md §5). Run IDs are UTC; creation is collision-safe so a
same-second second call never clobbers the first. ``pathlib`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

RUN_SUBDIRS: tuple[str, ...] = (
    "context",
    "evidence",
    "tasks",
    "results",
    "claims",
    "audit",
    "reports",
)

RUN_ID_FORMAT = "RUN-%Y%m%d-%H%M%S"
DEFAULT_BASE = "case_runs"


@dataclass(frozen=True)
class RunPaths:
    """Typed accessor for a run directory's standard locations."""

    root: Path

    @property
    def run_id(self) -> str:
        return self.root.name

    @property
    def context(self) -> Path:
        return self.root / "context"

    @property
    def evidence(self) -> Path:
        return self.root / "evidence"

    @property
    def tasks(self) -> Path:
        return self.root / "tasks"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def claims(self) -> Path:
        return self.root / "claims"

    @property
    def audit(self) -> Path:
        return self.root / "audit"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def evidence_manifest(self) -> Path:
        return self.evidence / "evidence_manifest.json"

    @property
    def custody_log(self) -> Path:
        """Chain-of-custody ledger (B9). One CustodyEvent per line."""
        return self.evidence / "custody_log.jsonl"

    @property
    def claim_ledger(self) -> Path:
        return self.claims / "claim_ledger.jsonl"

    @property
    def tool_calls(self) -> Path:
        return self.audit / "tool_calls.jsonl"

    @property
    def orchestration_events(self) -> Path:
        return self.audit / "orchestration_events.jsonl"

    def subdirs(self) -> list[Path]:
        return [self.root / name for name in RUN_SUBDIRS]


def utc_run_id() -> str:
    """Return a UTC run id, e.g. ``RUN-20260605-143001``."""
    return datetime.now(UTC).strftime(RUN_ID_FORMAT)


def new_run_dir(base: Path | str = DEFAULT_BASE, run_name: str | None = None) -> RunPaths:
    """Create a fresh run directory + full subtree; return its :class:`RunPaths`.

    Collision-safe: if the chosen name already exists, a ``-NN`` suffix is added
    so a second call within the same second never clobbers the first.
    """
    base = Path(base)
    name = run_name or utc_run_id()
    root = base / name
    if root.exists():
        n = 1
        while (base / f"{name}-{n:02d}").exists():
            n += 1
        root = base / f"{name}-{n:02d}"
    # exist_ok=False is intentional: root is guaranteed fresh by the check above,
    # so a race here surfaces loudly rather than silently reusing a directory.
    root.mkdir(parents=True, exist_ok=False)
    for subdir in RUN_SUBDIRS:
        (root / subdir).mkdir(exist_ok=False)
    return RunPaths(root=root)

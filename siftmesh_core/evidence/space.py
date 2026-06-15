"""Pre-flight disk-space estimator + partition planner (scale fixes / PLAN 11).

A real run writes large DERIVED data into the run dir (a 5.4 GB memory zip → ~19 GB raw; a 22 GB
disk image → extracted triage artifacts) while the originals stay read-only and are never copied.
This module estimates how much derived space the supplied evidence will need - exactly where an
archive header tells us (``zipfile.infolist`` uncompressed sizes; ``7z l`` listed sizes), with a
labelled allowance where it cannot - checks it against free disk, and if it will not fit proposes a
deterministic first-fit-decreasing partition so the operator can run the evidence in portions
(run → ``prune`` the bulky derived data → next portion → ``merge``). No LLM; pure arithmetic.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Derived-size heuristics (labelled "estimated" when used).
_NESTED_ARCHIVE_FACTOR = 3.0  # a zip whose member is itself a .7z/.gz → final raw is larger
_GZIP_FACTOR = 4.0  # gzip header size is mod-2^32 unreliable; use a compressed-times-N allowance
_IMAGE_EXTRACTION_FRACTION = 0.05  # extracted triage artifacts ≈ a few % of a disk image
_SAFETY_FACTOR = 1.2  # headroom over the raw estimate for working files/ledgers
_NESTED_SUFFIXES = frozenset({".7z", ".gz", ".zip", ".tar"})
_DISK_IMAGE_SUFFIXES = frozenset({".e01", ".raw", ".dd", ".img", ".vmdk"})


@dataclass(frozen=True)
class SpaceItem:
    """One evidence file's footprint: bytes on disk + estimated derived bytes it will produce."""

    path: str  # evidence-relative
    base_bytes: int  # size of the original (read-only; NOT copied into the run dir)
    derived_bytes: int  # estimated derived data written into the run dir
    exact: bool  # True if derived is read from an archive header, False if a labelled allowance


@dataclass(frozen=True)
class SpaceEstimate:
    """The full estimate: per-item rows + totals + free disk at the run location."""

    items: list[SpaceItem]
    free_bytes: int

    @property
    def total_derived(self) -> int:
        return sum(i.derived_bytes for i in self.items)

    @property
    def needed_bytes(self) -> int:
        """Derived data + a safety margin - what the run dir's filesystem must have free."""
        return int(self.total_derived * _SAFETY_FACTOR)

    @property
    def fits(self) -> bool:
        return self.needed_bytes <= self.free_bytes

    @property
    def any_estimated(self) -> bool:
        return any(not i.exact and i.derived_bytes for i in self.items)


def _zip_derived(path: Path) -> tuple[int, bool]:
    """(derived_bytes, exact) for a .zip from its central directory (no extraction)."""
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError):
        return int(path.stat().st_size * _NESTED_ARCHIVE_FACTOR), False
    total = sum(zi.file_size for zi in infos)
    nested = any(Path(zi.filename).suffix.lower() in _NESTED_SUFFIXES for zi in infos)
    if nested:  # zip → inner archive → larger raw; we cannot read the inner header cheaply
        return int(total * _NESTED_ARCHIVE_FACTOR), False
    return total, True


def _sevenzip_derived(path: Path) -> tuple[int, bool]:
    """(derived_bytes, exact) for a .7z via ``7z l`` (no extraction); allowance if 7z absent."""
    exe = next((shutil.which(n) for n in ("7z", "7za", "7zr") if shutil.which(n)), None)
    if exe is None:
        return int(path.stat().st_size * _NESTED_ARCHIVE_FACTOR), False
    try:
        proc = subprocess.run(  # fixed argv, shell=False
            [exe, "l", str(path)], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return int(path.stat().st_size * _NESTED_ARCHIVE_FACTOR), False
    # The `7z l` footer line: "<n> files, <m> folders" preceded by a totals row whose first
    # column is the summed uncompressed size. Parse the last all-digit first column.
    total = 0
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit() and parts[1].isdigit():
            total = max(total, int(parts[0]))  # the totals row carries the largest size
    if total <= 0:
        return int(path.stat().st_size * _NESTED_ARCHIVE_FACTOR), False
    return total, True


def _item(evidence_root: Path, file: Path) -> SpaceItem:
    rel = file.relative_to(evidence_root).as_posix()
    base = file.stat().st_size
    suffix = file.suffix.lower()
    if suffix == ".zip":
        derived, exact = _zip_derived(file)
    elif suffix == ".7z":
        derived, exact = _sevenzip_derived(file)
    elif suffix == ".gz":
        derived, exact = int(base * _GZIP_FACTOR), False
    elif suffix in _DISK_IMAGE_SUFFIXES:
        derived, exact = int(base * _IMAGE_EXTRACTION_FRACTION), False
    else:
        derived, exact = 0, True  # parsed/analysed in place; no large derived output
    return SpaceItem(path=rel, base_bytes=base, derived_bytes=derived, exact=exact)


def free_bytes(path: Path | str) -> int:
    """Free bytes on the filesystem holding ``path`` (walks up to an existing ancestor)."""
    p = Path(path).resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def estimate_required(evidence_dir: Path | str, *, run_location: Path | str = ".") -> SpaceEstimate:
    """Estimate derived-space need for everything under ``evidence_dir`` vs free disk."""
    root = Path(evidence_dir)
    items = [_item(root, f) for f in sorted(root.rglob("*")) if f.is_file()]
    return SpaceEstimate(items=items, free_bytes=free_bytes(run_location))


def partition_plan(items: list[SpaceItem], budget_bytes: int) -> list[list[SpaceItem]]:
    """First-fit-decreasing bin-pack of items into portions whose derived footprint ≤ budget.

    Deterministic (sort by derived desc, then path). An item whose derived alone exceeds the budget
    gets its own (over-budget) portion - surfaced so the operator knows it needs more disk.
    """
    if budget_bytes <= 0:
        return [[i] for i in items]
    ordered = sorted(items, key=lambda i: (-i.derived_bytes, i.path))
    bins: list[list[SpaceItem]] = []
    loads: list[int] = []
    for it in ordered:
        placed = False
        for b, load in enumerate(loads):
            if load + it.derived_bytes <= budget_bytes:
                bins[b].append(it)
                loads[b] += it.derived_bytes
                placed = True
                break
        if not placed:
            bins.append([it])
            loads.append(it.derived_bytes)
    return bins


def human_bytes(n: int) -> str:
    """Compact human-readable size (deterministic)."""
    step = 1024.0
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < step or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= step
    return f"{size:.1f} TB"

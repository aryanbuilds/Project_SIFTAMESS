"""SHA-256 hashing + deterministic, symlink-loop-safe directory walk (B1).

Streaming via :func:`hashlib.file_digest` (Python 3.11+) keeps memory constant
regardless of file size - a 100GB artifact hashes in one read pass without OOM.
The walk produces a stable, sorted ordering (reproducible manifests) and guards
against symlink loops with a visited ``(st_dev, st_ino)`` set. Symlinks are not
followed: SIFTMesh hashes only the real files inside the evidence tree, never an
out-of-tree target (the MVP forensic-safe choice).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class FileFact:
    """One file's integrity facts, relative to the walked root."""

    rel_path: str  # POSIX-style relative path
    sha256: str
    size_bytes: int
    mtime_utc: datetime


def sha256_file(path: Path | str) -> str:
    """Return the hex SHA-256 of ``path``, streamed (constant memory)."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _iter_regular_files(base: Path) -> Iterator[tuple[Path, os.stat_result]]:
    """Yield ``(path, stat)`` for every real (non-symlink) regular file.

    Deterministic order (sorted dirs + files), symlinks skipped, directory
    loops guarded, unreadable entries skipped.
    """
    visited: set[tuple[int, int]] = set()
    for root, dirs, files in os.walk(base, followlinks=False):
        root_path = Path(root)
        try:
            root_stat = root_path.stat()
        except OSError:
            dirs[:] = []
            continue
        key = (root_stat.st_dev, root_stat.st_ino)
        if key in visited:  # loop guard (defense in depth alongside followlinks=False)
            dirs[:] = []
            continue
        visited.add(key)

        dirs.sort()
        for name in sorted(files):
            fpath = root_path / name
            if fpath.is_symlink():
                continue  # never follow links out of the evidence tree (MVP)
            try:
                fstat = fpath.stat()
            except OSError:
                continue
            if not fpath.is_file():
                continue
            yield fpath, fstat


def scan_totals(base: Path | str) -> tuple[int, int]:
    """Cheap stat-only pre-scan: ``(file_count, total_bytes)`` - no hashing.

    Used to drive the ingest progress/ETA counter without reading file bytes.
    """
    count = 0
    total = 0
    for _path, fstat in _iter_regular_files(Path(base)):
        count += 1
        total += fstat.st_size
    return count, total


def walk_files(
    base: Path | str,
    *,
    on_progress: Callable[[FileFact], None] | None = None,
) -> list[FileFact]:
    """Walk ``base`` recursively, returning sorted :class:`FileFact`s.

    Deterministic ordering (sorted by POSIX rel_path). ``on_progress`` (if given)
    is called once per hashed file, in walk order, before the final sort.
    """
    base = Path(base)
    facts: list[FileFact] = []
    for fpath, fstat in _iter_regular_files(base):
        try:
            digest = sha256_file(fpath)
        except OSError:
            continue
        fact = FileFact(
            rel_path=fpath.relative_to(base).as_posix(),
            sha256=digest,
            size_bytes=fstat.st_size,
            mtime_utc=datetime.fromtimestamp(fstat.st_mtime, tz=UTC),
        )
        facts.append(fact)
        if on_progress is not None:
            on_progress(fact)

    facts.sort(key=lambda fact: fact.rel_path)
    return facts

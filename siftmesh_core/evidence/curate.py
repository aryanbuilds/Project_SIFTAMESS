"""Curate a focused evidence directory from operator-selected files/folders (TUI wizard + reuse).

The TUI evidence picker lets the operator choose several files AND folders from the filesystem; the
vault then ingests ONE evidence root. ``curate_evidence`` assembles that root by **hard-linking**
the selected items into a destination dir (``os.link`` - same inode, zero extra disk, originals
untouched; falls back to ``shutil.copy2`` across filesystems). This is the programmatic form of the
RUNBOOK §2a ``ln … || cp -n …`` step. Originals are NEVER written to.

Single-folder shortcut: if exactly one directory is selected (and nothing else), it is used directly
as the evidence root - no curation, no extra inodes.

The destination MUST live under the case dir (not /tmp), because the run records the evidence root's
absolute path in ``readonly_mounts.json`` and resume reads it back (``recover_evidence_root``).
"""

from __future__ import annotations

import errno
import os
import shutil
from collections.abc import Sequence
from pathlib import Path


class CurateError(RuntimeError):
    """Evidence curation refused (missing source, name collision, or non-empty destination)."""


def _link_or_copy(src: Path, dst: Path) -> None:
    """Hard-link ``src`` -> ``dst``; copy across filesystems. Never modifies ``src``."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError as exc:
        if exc.errno == errno.EXDEV:  # cross-device link → fall back to a content copy
            shutil.copy2(src, dst)
        else:
            raise


def curate_evidence(selected_paths: Sequence[Path | str], dest_dir: Path | str) -> Path:
    """Assemble an evidence root from the selected files/folders; return the root to ingest.

    - exactly one directory selected → return it as-is (no curation).
    - otherwise hard-link (or copy on EXDEV) every selected file, and every file under every
      selected folder (relative subtree preserved), into ``dest_dir``; return ``dest_dir``.

    Raises ``CurateError`` on: no selection, a missing source, a non-empty ``dest_dir``, or a
    destination-path collision between two distinct sources.
    """
    paths = [Path(p) for p in selected_paths]
    if not paths:
        raise CurateError("no evidence selected")
    for p in paths:
        if not p.exists():
            raise CurateError(f"selected path does not exist: {p}")

    if len(paths) == 1 and paths[0].is_dir():
        return paths[0].resolve()  # single-folder shortcut: ingest it directly

    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()):
        raise CurateError(f"destination is not empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    seen: set[Path] = set()  # relative dest paths, to catch true collisions across sources
    for src in paths:
        if src.is_dir():
            base = src.resolve()
            for f in sorted(base.rglob("*")):
                if f.is_file():
                    rel = Path(src.name) / f.relative_to(base)
                    _place(f, dest, rel, seen)
        else:
            _place(src.resolve(), dest, Path(src.name), seen)
    return dest.resolve()


def _place(src: Path, dest: Path, rel: Path, seen: set[Path]) -> None:
    if rel in seen:
        raise CurateError(f"two selected sources collide on {rel} - rename or select one")
    seen.add(rel)
    _link_or_copy(src, dest / rel)

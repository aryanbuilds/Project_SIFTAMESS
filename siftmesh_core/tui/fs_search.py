"""Filesystem-wide fuzzy file/folder finder for the evidence picker (Textual-free, deterministic).

The evidence picker's bottom search box parses ``#file <q>`` / ``#folder <q>`` and calls
``fuzzy_find`` in a worker thread. Strategy (maintainer choice): use the fast ``fd``/``find`` CLI
when present (fixed-argv, ``shell=False``) to enumerate subsequence-matching paths, else a bounded
``os.walk``; then rank every candidate with Textual's ``fuzzy.Matcher`` (score in ``[0, ∞)``, 0 = no
match → keep ``>0``, sort DESC then by path for determinism).

Read-only: only ``scandir``/``stat`` - never opens or mutates a candidate (evidence-safe). Bounded
by ``max_depth`` + ``limit`` and a skip-list (dotdirs, ``node_modules``, ``/proc`` ``/sys`` ``/dev``
``/run``) so a search from ``$HOME`` or ``/`` stays responsive and skips pseudo-filesystems.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

Mode = Literal["file", "folder", "both"]

# Directory names never worth walking for evidence (noise / huge / volatile).
_NOISE_NAMES = frozenset({"node_modules", "__pycache__", ".git", ".cache", "snap", ".venv"})
# Absolute prefixes that are pseudo/volatile filesystems - never recurse them.
_SYSTEM_PREFIXES = ("/proc", "/sys", "/dev", "/run")
_ENUM_TIMEOUT_S = 15


def _should_skip(path: Path) -> bool:
    """True if any path component is hidden/noise or it lives under a pseudo-filesystem."""
    s = str(path)
    if any(s == p or s.startswith(p + "/") for p in _SYSTEM_PREFIXES):
        return True
    return any(part.startswith(".") or part in _NOISE_NAMES for part in path.parts)


def _subseq_regex(query: str) -> str:
    """Case-insensitive subsequence regex for ``fd`` (e.g. 'sevtx' → '(?i).*?s.*?e.*?v.*?t.*?x')."""
    import re

    chars = [re.escape(c) for c in query if not c.isspace()]
    return "(?i).*?" + ".*?".join(chars) if chars else "(?i)."


def _subseq_glob(query: str) -> str:
    """Case-insensitive subsequence glob for ``find -iname`` (e.g. 'sx' → '*s*x*')."""
    parts = []
    for c in query:
        if c.isspace():
            continue
        parts.append("[" + c + "]" if c in "*?[]\\" else c)  # neutralize glob metachars
    return "*" + "*".join(parts) + "*" if parts else "*"


def _run(argv: list[str]) -> list[str] | None:
    """Run a fixed-argv enumerator; stdout lines, or None on failure (→ try the next strategy)."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=_ENUM_TIMEOUT_S, shell=False, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode not in (0, 1):  # find returns 1 on permission errors but still prints hits
        return None
    return [ln for ln in proc.stdout.splitlines() if ln]


def _enumerate_fd(fd: str, root: Path, query: str, mode: Mode, max_depth: int) -> list[str] | None:
    argv = [fd, "--ignore-case", "--color", "never", "--max-depth", str(max_depth)]
    if mode == "file":
        argv += ["--type", "f"]
    elif mode == "folder":
        argv += ["--type", "d"]
    for name in _NOISE_NAMES:
        argv += ["--exclude", name]
    argv += [_subseq_regex(query), str(root)]
    return _run(argv)


def _enumerate_find(
    find: str, root: Path, query: str, mode: Mode, max_depth: int
) -> list[str] | None:
    argv = [find, str(root), "-maxdepth", str(max_depth)]
    if mode == "file":
        argv += ["-type", "f"]
    elif mode == "folder":
        argv += ["-type", "d"]
    argv += ["-iname", _subseq_glob(query)]
    return _run(argv)


def _enumerate_walk(root: Path, mode: Mode, max_depth: int, limit: int) -> list[str]:
    """Pure-Python bounded walk (fallback). Returns up to ~limit*4 candidates before ranking."""
    hits: list[str] = []
    cap = limit * 4
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel = Path(dirpath)
        # directory depth relative to root (root=0); an ENTRY here is at depth `dd + 1`.
        dd = len(rel.parts) - len(root.parts)
        # prune hidden/noise/system dirs from both descent and folder-listing
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in _NOISE_NAMES
            and not _should_skip(Path(dirpath) / d)
        ]
        if dirpath != root_str and _should_skip(rel):
            dirnames[:] = []
            continue
        # list entries only when their depth (dd+1) is within max_depth (fd-style: root=depth 0)
        if dd < max_depth:
            if mode in ("folder", "both"):
                hits.extend(str(rel / d) for d in dirnames)
            if mode in ("file", "both"):
                hits.extend(str(rel / f) for f in filenames if not f.startswith("."))
        if dd + 1 >= max_depth:  # nothing deeper can be within range → stop descending
            dirnames[:] = []
        if len(hits) >= cap:
            break
    return hits


def _rank(query: str, candidates: list[str], limit: int) -> list[Path]:
    """Rank candidate paths by fuzzy score on the basename (>0), DESC, then path (deterministic)."""
    from textual.fuzzy import Matcher

    matcher = Matcher(query)
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        p = Path(c)
        if _should_skip(p):
            continue
        score = matcher.match(p.name)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda sp: (-sp[0], sp[1]))
    return [Path(c) for _score, c in scored[:limit]]


def fuzzy_find(
    query: str, *, root: str | Path, mode: Mode = "both", limit: int = 500, max_depth: int = 6
) -> list[Path]:
    """Fuzzy-search files/folders under ``root`` whose name subsequence-matches ``query``.

    ``mode``: ``file`` / ``folder`` / ``both``. Empty query or non-dir root → ``[]``. Prefers
    ``fd`` then ``find`` for enumeration, falls back to a bounded ``os.walk``; always ranked by
    ``textual.fuzzy.Matcher``. Deterministic: same tree + query → same order.
    """
    q = query.strip()
    base = Path(root).expanduser()
    if not q or not base.is_dir():
        return []
    candidates: list[str] | None = None
    fd = shutil.which("fdfind") or shutil.which("fd")  # Debian/Ubuntu ships fd as `fdfind`
    if fd:
        candidates = _enumerate_fd(fd, base, q, mode, max_depth)
    if candidates is None:
        find = shutil.which("find")
        if find:
            candidates = _enumerate_find(find, base, q, mode, max_depth)
    if candidates is None:
        candidates = _enumerate_walk(base, mode, max_depth, limit)
    return _rank(q, candidates, limit)

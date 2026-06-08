"""Sleuthkit-backed image access (SIFT-lane) — extract loose artifacts from a disk image.

The eight typed parsers each consume a single loose Windows artifact; real evidence
arrives as a disk image (``.E01``/raw). This module bridges the two by extracting the
high-value artifacts out of the image with **The Sleuth Kit** (``mmls``/``ifind``/
``icat``/``fls``), which reads EWF/``.E01`` natively.

Safety (CLAUDE.md §6, criterion 4): every call is a **fixed-argv** ``subprocess`` with
``shell=False``. The only variable argv elements are the validated image path, a numeric
partition offset, and a TSK metadata address — never an attacker-controlled string spliced
into a shell. A missing TSK binary **fails closed** (:class:`BackendUnavailableError`),
never a fake result. Originals are opened read-only by TSK; output is written by the
caller through ``safe_write_path``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_DEFAULT_TIMEOUT = 1800  # seconds; large-volume MFT/dir walks over a 23GB image are slow

# Curated high-value Windows artifacts (NTFS paths inside the C: volume). Each entry is
# (logical key, kind, ntfs_path_or_dir). "file" = single file; "glob" = every *.pf in a
# dir; "userhive" = NTUSER.DAT under each profile; "mft" = the $MFT (metadata addr 0).
ARTIFACT_MAP: tuple[tuple[str, str, str], ...] = (
    ("security_evtx", "file", "/Windows/System32/winevt/Logs/Security.evtx"),
    (
        "powershell_evtx",
        "file",
        "/Windows/System32/winevt/Logs/Microsoft-Windows-PowerShell%4Operational.evtx",
    ),
    ("system_evtx", "file", "/Windows/System32/winevt/Logs/System.evtx"),
    ("software_hive", "file", "/Windows/System32/config/SOFTWARE"),
    ("system_hive", "file", "/Windows/System32/config/SYSTEM"),
    ("prefetch", "glob", "/Windows/Prefetch"),
    ("user_hives", "userhive", "/Users"),
    ("mft", "mft", "0"),
)

_FS_TYPE = "ntfs"


@dataclass(frozen=True)
class Partition:
    """One row of the image's partition table (sectors)."""

    addr: int
    start_sector: int
    length_sectors: int
    description: str


@dataclass(frozen=True)
class ExtractedFile:
    """One artifact extracted out of the image into the run dir."""

    key: str
    ntfs_path: str
    inode: str
    dest: Path  # absolute path written under the run dir
    sha256: str
    size_bytes: int


def _require(tool: str) -> str:
    """Resolve a TSK binary on PATH or fail closed."""
    found = shutil.which(tool)
    if found is None:
        raise BackendUnavailableError(
            f"Sleuthkit tool {tool!r} not found on PATH (install 'sleuthkit'); fails closed"
        )
    return found


def _safe_name(name: str) -> str:
    """Reduce an NTFS filename to a safe flat basename (case data is hostile, §6)."""
    base = Path(name.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._%+-]", "_", base).strip("._")
    return cleaned or "artifact"


# ── TSK primitives (fixed-argv, shell=False) ────────────────────────────────


def list_partitions(image: Path, *, timeout: int = 120) -> list[Partition]:
    """Return NTFS partitions from ``mmls``; empty if the image has no partition table."""
    exe = _require("mmls")
    proc = subprocess.run(  # fixed argv, shell=False, validated path
        [exe, "-M", str(image)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    # mmls exits non-zero / prints nothing for a single-volume image (no table) —
    # that is expected, not an error; callers then use offset 0.
    parts: list[Partition] = []
    row = re.compile(r"^\s*(\d+):\s+\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$")
    for line in proc.stdout.splitlines():
        m = row.match(line)
        if m and "NTFS" in m.group(5).upper():
            parts.append(
                Partition(
                    addr=int(m.group(1)),
                    start_sector=int(m.group(2)),
                    length_sectors=int(m.group(4)),
                    description=m.group(5).strip(),
                )
            )
    return parts


def resolve_offset(image: Path) -> int:
    """Pick the NTFS partition start sector, or 0 for a single-volume image."""
    parts = list_partitions(image)
    return parts[0].start_sector if parts else 0


def find_inode(
    image: Path, offset: int, ntfs_path: str, *, timeout: int = _DEFAULT_TIMEOUT
) -> str | None:
    """Resolve an NTFS path to its TSK metadata address via ``ifind -n``; None if absent."""
    exe = _require("ifind")
    proc = subprocess.run(  # fixed argv, shell=False
        [exe, "-f", _FS_TYPE, "-o", str(offset), "-n", ntfs_path, str(image)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out or "not found" in out.lower():
        return None
    token = out.split()[0]
    # A valid address is a number, optionally with TSK type/id suffix (e.g. 65-128-1).
    return token if re.fullmatch(r"\d+(?:-\d+)*", token) else None


def list_dir(
    image: Path, offset: int, inode: str, *, timeout: int = _DEFAULT_TIMEOUT
) -> list[tuple[str, str, str]]:
    """List a directory's entries via ``fls`` → ``[(type, name, inode), ...]``."""
    exe = _require("fls")
    proc = subprocess.run(  # fixed argv, shell=False
        [exe, "-f", _FS_TYPE, "-o", str(offset), str(image), str(inode)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    entries: list[tuple[str, str, str]] = []
    row = re.compile(r"^(.)/(.)\s+(\*?\s*[\d-]+):\s+(.*)$")
    for line in proc.stdout.splitlines():
        m = row.match(line)
        if not m:
            continue
        meta_addr = m.group(3).replace("*", "").strip()
        entries.append((m.group(1), m.group(4).strip(), meta_addr))
    return entries


def extract_inode(
    image: Path, offset: int, inode: str, dest: Path, *, timeout: int = _DEFAULT_TIMEOUT
) -> Path:
    """Stream a file's bytes out of the image via ``icat`` into ``dest`` (no buffering)."""
    exe = _require("icat")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        proc = subprocess.run(  # fixed argv, shell=False
            [exe, "-f", _FS_TYPE, "-o", str(offset), str(image), str(inode)],
            stdout=handle,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"icat failed for inode {inode}: {err or 'non-zero exit'}")
    return dest


# ── High-level extraction ───────────────────────────────────────────────────


def _record(key: str, ntfs_path: str, inode: str, dest: Path) -> ExtractedFile:
    return ExtractedFile(
        key=key,
        ntfs_path=ntfs_path,
        inode=inode,
        dest=dest,
        sha256=sha256_file(dest),
        size_bytes=dest.stat().st_size,
    )


def _extract_file(
    image: Path, offset: int, key: str, ntfs_path: str, dest_dir: Path
) -> ExtractedFile | None:
    inode = find_inode(image, offset, ntfs_path)
    if inode is None:
        return None
    dest = dest_dir / _safe_name(ntfs_path)
    extract_inode(image, offset, inode, dest)
    return _record(key, ntfs_path, inode, dest)


def _extract_glob(
    image: Path, offset: int, key: str, dir_path: str, dest_dir: Path
) -> list[ExtractedFile]:
    dir_inode = find_inode(image, offset, dir_path)
    if dir_inode is None:
        return []
    out: list[ExtractedFile] = []
    sub = dest_dir / _safe_name(Path(dir_path).name)
    for kind, name, inode in list_dir(image, offset, dir_inode):
        if kind != "r" or not name.lower().endswith(".pf"):
            continue
        dest = sub / _safe_name(name)
        try:
            extract_inode(image, offset, inode, dest)
        except RuntimeError:
            continue
        out.append(_record(key, f"{dir_path}/{name}", inode, dest))
    return out


def _extract_user_hives(
    image: Path, offset: int, key: str, users_dir: str, dest_dir: Path
) -> list[ExtractedFile]:
    users_inode = find_inode(image, offset, users_dir)
    if users_inode is None:
        return []
    out: list[ExtractedFile] = []
    sub = dest_dir / "user_hives"
    for kind, name, _inode in list_dir(image, offset, users_inode):
        if kind != "d" or name in (".", "..", "Public", "Default", "All Users"):
            continue
        hive_path = f"{users_dir}/{name}/NTUSER.DAT"
        hive_inode = find_inode(image, offset, hive_path)
        if hive_inode is None:
            continue
        dest = sub / f"{_safe_name(name)}_NTUSER.DAT"
        try:
            extract_inode(image, offset, hive_inode, dest)
        except RuntimeError:
            continue
        out.append(_record(key, hive_path, hive_inode, dest))
    return out


def extract_artifacts(
    image: Path,
    *,
    dest_dir: Path,
    offset: int | None = None,
    keys: frozenset[str] | None = None,
) -> list[ExtractedFile]:
    """Extract the curated artifacts (or a subset by ``keys``) from ``image`` into ``dest_dir``.

    ``dest_dir`` must already be a path the caller validated with ``safe_write_path``.
    Missing artifacts are skipped (a Windows box may lack a PowerShell-Operational log);
    a missing TSK binary fails closed via the primitives above.
    """
    image = Path(image)
    dest_dir.mkdir(parents=True, exist_ok=True)
    off = offset if offset is not None else resolve_offset(image)
    results: list[ExtractedFile] = []
    for key, kind, path in ARTIFACT_MAP:
        if keys is not None and key not in keys:
            continue
        if kind == "file":
            one = _extract_file(image, off, key, path, dest_dir)
            if one is not None:
                results.append(one)
        elif kind == "glob":
            results.extend(_extract_glob(image, off, key, path, dest_dir))
        elif kind == "userhive":
            results.extend(_extract_user_hives(image, off, key, path, dest_dir))
        elif kind == "mft":
            dest = dest_dir / "MFT"
            extract_inode(image, off, path, dest)
            results.append(_record(key, "/$MFT", path, dest))
    return results

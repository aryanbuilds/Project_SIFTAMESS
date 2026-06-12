"""Sleuthkit-backed image access (SIFT-lane) — extract loose artifacts from a disk image.

The typed parsers each consume a single loose Windows artifact; real evidence
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
# dir; "userhive" = NTUSER.DAT under each profile; "userfile" = a per-user file at a
# profile-relative path (one optional ``*`` wildcard segment); "usertree" = every file under a
# per-user directory tree (recursive); "mft" = the $MFT (addr 0).
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
    ("chrome_history", "userfile", "AppData/Local/Google/Chrome/User Data/Default/History"),
    ("edge_history", "userfile", "AppData/Local/Microsoft/Edge/User Data/Default/History"),
    ("firefox_history", "userfile", "AppData/Roaming/Mozilla/Firefox/Profiles/*/places.sqlite"),
    ("usrclass_hives", "userfile", "AppData/Local/Microsoft/Windows/UsrClass.dat"),
    ("recent_jumplists", "usertree", "AppData/Roaming/Microsoft/Windows/Recent"),
    ("mft", "mft", "0"),
)

_FS_TYPE = "ntfs"
_USERS_DIR = "/Users"  # per-user artifacts ("userfile") resolve under each profile here
_SKIP_PROFILES = (".", "..", "Public", "Default", "All Users", "Default User")


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


@dataclass(frozen=True)
class ExtractionFailure:
    """One artifact that could not be extracted (e.g. corrupt NTFS compression in image)."""

    key: str
    ntfs_path: str
    error: str


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
        dest.unlink(missing_ok=True)  # drop the partial/corrupt output — never keep garbage
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


def _extract_one(
    image: Path, offset: int, key: str, ntfs_path: str, inode: str, dest: Path
) -> tuple[ExtractedFile | None, ExtractionFailure | None]:
    """Extract one known-inode file. A corrupt file is recorded as a failure, never fatal."""
    try:
        extract_inode(image, offset, inode, dest)
    except RuntimeError as exc:
        return None, ExtractionFailure(key=key, ntfs_path=ntfs_path, error=str(exc))
    return _record(key, ntfs_path, inode, dest), None


def _extract_file(
    image: Path, offset: int, key: str, ntfs_path: str, dest_dir: Path
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    inode = find_inode(image, offset, ntfs_path)
    if inode is None:
        return [], []
    ok, fail = _extract_one(image, offset, key, ntfs_path, inode, dest_dir / _safe_name(ntfs_path))
    return ([ok] if ok else []), ([fail] if fail else [])


def _extract_glob(
    image: Path, offset: int, key: str, dir_path: str, dest_dir: Path
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    dir_inode = find_inode(image, offset, dir_path)
    if dir_inode is None:
        return [], []
    ok: list[ExtractedFile] = []
    failed: list[ExtractionFailure] = []
    sub = dest_dir / _safe_name(Path(dir_path).name)
    for kind, name, inode in list_dir(image, offset, dir_inode):
        if kind != "r" or not name.lower().endswith(".pf"):
            continue
        one, fail = _extract_one(
            image, offset, key, f"{dir_path}/{name}", inode, sub / _safe_name(name)
        )
        if one:
            ok.append(one)
        if fail:
            failed.append(fail)
    return ok, failed


def _extract_user_hives(
    image: Path, offset: int, key: str, users_dir: str, dest_dir: Path
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    users_inode = find_inode(image, offset, users_dir)
    if users_inode is None:
        return [], []
    ok: list[ExtractedFile] = []
    failed: list[ExtractionFailure] = []
    sub = dest_dir / "user_hives"
    for kind, name, _inode in list_dir(image, offset, users_inode):
        if kind != "d" or name in (".", "..", "Public", "Default", "All Users"):
            continue
        hive_path = f"{users_dir}/{name}/NTUSER.DAT"
        hive_inode = find_inode(image, offset, hive_path)
        if hive_inode is None:
            continue
        one, fail = _extract_one(
            image, offset, key, hive_path, hive_inode, sub / f"{_safe_name(name)}_NTUSER.DAT"
        )
        if one:
            ok.append(one)
        if fail:
            failed.append(fail)
    return ok, failed


def _expand_user_relpaths(image: Path, offset: int, user_root: str, rel_path: str) -> list[str]:
    """Resolve a profile-relative path that may contain ONE ``*`` directory wildcard.

    No ``*`` -> the path unchanged. With ``*`` -> one expansion per subdirectory of the
    wildcard's parent (e.g. each Firefox ``Profiles/<rnd>`` dir).
    """
    if "*" not in rel_path:
        return [rel_path]
    before, after = rel_path.split("*", 1)
    before = before.rstrip("/")
    after = after.lstrip("/")
    parent_inode = find_inode(image, offset, f"{user_root}/{before}")
    if parent_inode is None:
        return []
    out: list[str] = []
    for kind, name, _inode in list_dir(image, offset, parent_inode):
        if kind == "d" and name not in (".", ".."):
            out.append(f"{before}/{name}/{after}")
    return out


def _extract_per_user(
    image: Path, offset: int, key: str, users_dir: str, rel_path: str, dest_dir: Path
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    """Extract a per-user file at ``Users/<u>/<rel_path>`` (one optional ``*`` segment).

    Extracted files KEEP their real basename (``History`` / ``places.sqlite`` / ``UsrClass.dat``)
    and disambiguate by ``<key>/<user>/`` subdirs — the artifact router classifies on basename.
    """
    users_inode = find_inode(image, offset, users_dir)
    if users_inode is None:
        return [], []
    ok: list[ExtractedFile] = []
    failed: list[ExtractionFailure] = []
    sub = dest_dir / key
    for kind, user, _inode in list_dir(image, offset, users_inode):
        if kind != "d" or user in _SKIP_PROFILES:
            continue
        for rel in _expand_user_relpaths(image, offset, f"{users_dir}/{user}", rel_path):
            full = f"{users_dir}/{user}/{rel}"
            inode = find_inode(image, offset, full)
            if inode is None:
                continue
            dest = sub / _safe_name(user) / _safe_name(Path(rel).name)
            one, fail = _extract_one(image, offset, key, full, inode, dest)
            if one:
                ok.append(one)
            if fail:
                failed.append(fail)
    return ok, failed


def _walk_tree(
    image: Path, offset: int, key: str, ntfs_dir: str, inode: str, dest_dir: Path, depth: int
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    """Recursively extract every regular file under ``ntfs_dir`` (bounded depth)."""
    if depth <= 0:
        return [], []
    ok: list[ExtractedFile] = []
    failed: list[ExtractionFailure] = []
    for kind, name, child in list_dir(image, offset, inode):
        if name in (".", ".."):
            continue
        child_path = f"{ntfs_dir}/{name}"
        if kind == "d":
            sub_ok, sub_fail = _walk_tree(
                image, offset, key, child_path, child, dest_dir / _safe_name(name), depth - 1
            )
            ok.extend(sub_ok)
            failed.extend(sub_fail)
        elif kind == "r":
            one, fail = _extract_one(
                image, offset, key, child_path, child, dest_dir / _safe_name(name)
            )
            if one:
                ok.append(one)
            if fail:
                failed.append(fail)
    return ok, failed


def _extract_user_tree(
    image: Path, offset: int, key: str, users_dir: str, rel_dir: str, dest_dir: Path
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    """Extract every file under ``Users/<u>/<rel_dir>`` (e.g. the Recent / JumpList tree).

    Files keep their real basename (``*.lnk`` / ``*.automaticDestinations-ms``) and disambiguate
    by ``<key>/<user>/...`` subdirs so the artifact router classifies them on basename/suffix.
    """
    users_inode = find_inode(image, offset, users_dir)
    if users_inode is None:
        return [], []
    ok: list[ExtractedFile] = []
    failed: list[ExtractionFailure] = []
    root_sub = dest_dir / key
    for kind, user, _inode in list_dir(image, offset, users_inode):
        if kind != "d" or user in _SKIP_PROFILES:
            continue
        base = f"{users_dir}/{user}/{rel_dir}"
        base_inode = find_inode(image, offset, base)
        if base_inode is None:
            continue
        sub_ok, sub_fail = _walk_tree(
            image, offset, key, base, base_inode, root_sub / _safe_name(user), depth=4
        )
        ok.extend(sub_ok)
        failed.extend(sub_fail)
    return ok, failed


def extract_artifacts(
    image: Path,
    *,
    dest_dir: Path,
    offset: int | None = None,
    keys: frozenset[str] | None = None,
) -> tuple[list[ExtractedFile], list[ExtractionFailure]]:
    """Extract the curated artifacts (or a subset) from ``image`` into ``dest_dir``.

    Returns ``(extracted, failed)``. A single unreadable artifact — e.g. an NTFS-compressed
    file that is corrupt in the image (LZNT1 decompression fails identically across TSK,
    ntfs-3g, and libfsntfs) — is recorded in ``failed`` and never aborts the whole run.
    Missing artifacts are skipped; a missing TSK binary fails closed via the primitives.
    ``dest_dir`` must already be a path the caller validated with ``safe_write_path``.
    """
    image = Path(image)
    dest_dir.mkdir(parents=True, exist_ok=True)
    off = offset if offset is not None else resolve_offset(image)
    results: list[ExtractedFile] = []
    failures: list[ExtractionFailure] = []
    for key, kind, path in ARTIFACT_MAP:
        if keys is not None and key not in keys:
            continue
        if kind == "file":
            ok, fail = _extract_file(image, off, key, path, dest_dir)
        elif kind == "glob":
            ok, fail = _extract_glob(image, off, key, path, dest_dir)
        elif kind == "userhive":
            ok, fail = _extract_user_hives(image, off, key, path, dest_dir)
        elif kind == "userfile":
            ok, fail = _extract_per_user(image, off, key, _USERS_DIR, path, dest_dir)
        elif kind == "usertree":
            ok, fail = _extract_user_tree(image, off, key, _USERS_DIR, path, dest_dir)
        elif kind == "mft":
            one, one_fail = _extract_one(image, off, key, "/$MFT", path, dest_dir / "MFT")
            ok = [one] if one else []
            fail = [one_fail] if one_fail else []
        else:
            ok, fail = [], []
        results.extend(ok)
        failures.extend(fail)
    return results, failures

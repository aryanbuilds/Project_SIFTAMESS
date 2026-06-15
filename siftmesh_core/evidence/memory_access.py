"""Memory-image acquisition (Epic D deepening) - unpack a compressed memory capture.

SANS memory captures arrive as ``Rocba-Memory.zip`` → ``.7z`` → a raw/crash/LiME image.
This module unzips (stdlib) and 7z-decompresses (fixed-argv ``7z x``, ``shell=False``) the
capture into the run dir, identifies the image format by magic, and returns the decompressed
image's path/hash so a memory tool can analyse it. A missing ``7z`` binary **fails closed**
(:class:`BackendUnavailableError`). The intermediate ``.7z`` is removed after a successful
decompression to conserve disk.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from siftmesh_core.evidence.hash_utils import sha256_file
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_DEFAULT_TIMEOUT = 3600  # seconds; multi-GB 7z decompression

# First-bytes magic → memory image format.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"PAGEDU64", "windows_crashdump64"),
    (b"PAGEDUMP", "windows_crashdump32"),
    (b"EMiL", "lime"),
)


@dataclass(frozen=True)
class MemoryImage:
    """A decompressed memory capture ready for analysis."""

    path: Path
    image_format: str
    size_bytes: int
    sha256: str


def detect_format(path: Path) -> str:
    """Identify a memory image by leading magic; default ``raw``."""
    with Path(path).open("rb") as handle:
        head = handle.read(8)
    for magic, name in _MAGIC:
        if head.startswith(magic):
            return name
    return "raw"


def _require_7z() -> str:
    for name in ("7z", "7za", "7zr"):
        found = shutil.which(name)
        if found is not None:
            return found
    raise BackendUnavailableError("'7z' not found on PATH (install 'p7zip-full'); fails closed")


def _largest_file(directory: Path, *, exclude: set[Path]) -> Path | None:
    candidates = [p for p in directory.rglob("*") if p.is_file() and p.resolve() not in exclude]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def decompress(
    zip_path: Path | str, dest_dir: Path, *, timeout: int = _DEFAULT_TIMEOUT
) -> MemoryImage:
    """Unzip + 7z-decompress a memory capture into ``dest_dir``; return the image.

    ``dest_dir`` must already be a caller-validated (``safe_write_path``) directory.
    """
    zip_path = Path(zip_path)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1) Unzip the outer .zip (stdlib) - guard against zip-slip (hostile member names).
    extracted_members: list[Path] = []
    if zipfile.is_zipfile(zip_path):
        with zipfile.ZipFile(zip_path) as zf:
            dest_resolved = dest_dir.resolve()
            for member in zf.namelist():
                target = (dest_dir / Path(member).name).resolve()
                if not target.is_relative_to(dest_resolved):
                    raise RuntimeError(f"zip member escapes dest dir: {member!r}")
                if member.endswith("/"):
                    continue
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_members.append(target)
    else:
        # Not a zip - treat the input itself as the (possibly .7z) capture.
        local = dest_dir / zip_path.name
        if local.resolve() != zip_path.resolve():
            shutil.copyfile(zip_path, local)
        extracted_members.append(local)

    # 2) 7z-decompress any .7z members (fixed-argv).
    seven_zips = [p for p in extracted_members if p.suffix.lower() == ".7z"]
    intermediate: set[Path] = {p.resolve() for p in extracted_members}
    for archive in seven_zips:
        exe = _require_7z()
        proc = subprocess.run(  # fixed argv, shell=False, validated path
            [exe, "x", "-y", f"-o{dest_dir}", str(archive)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"7z extraction failed: {proc.stderr.strip() or 'non-zero exit'}")

    # 3) The memory image is the largest file that is not an intermediate archive.
    image = _largest_file(dest_dir, exclude=intermediate)
    if image is None:  # only archives were present (or nothing) - fall back to the largest member
        image = _largest_file(dest_dir, exclude=set())
    if image is None:
        raise RuntimeError("no memory image found after decompression")

    # 4) Tidy intermediates to conserve disk (they are our own derived temps).
    for archive in seven_zips:
        if archive.resolve() != image.resolve():
            archive.unlink(missing_ok=True)

    return MemoryImage(
        path=image,
        image_format=detect_format(image),
        size_bytes=image.stat().st_size,
        sha256=sha256_file(image),
    )

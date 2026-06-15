"""Memory-image acquisition (Epic D deepening): unzip/7z, format detect, fail-closed.

7z subprocess is mocked; the outer zip is a real stdlib zip. No real memory image is used.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from siftmesh_core.evidence import memory_access
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError


def test_detect_format_by_magic(tmp_path: Path) -> None:
    raw = tmp_path / "mem.raw"
    raw.write_bytes(b"PAGEDU64" + b"\x00" * 16)
    assert memory_access.detect_format(raw) == "windows_crashdump64"
    plain = tmp_path / "plain.raw"
    plain.write_bytes(b"\x00" * 32)
    assert memory_access.detect_format(plain) == "raw"


def test_decompress_plain_zip_no_7z_needed(tmp_path: Path) -> None:
    """A zip whose member is the raw image directly needs no 7z step."""
    zip_path = tmp_path / "Memory.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("memory.raw", b"PAGEDU64" + b"\x01" * 4096)
    dest = tmp_path / "extracted"
    img = memory_access.decompress(zip_path, dest)
    assert img.path.is_file()
    assert img.image_format == "windows_crashdump64"
    assert img.size_bytes > 0
    assert len(img.sha256) == 64


def test_decompress_7z_path_invokes_fixed_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    zip_path = tmp_path / "Memory.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Rocba-Memory.7z", b"7z-bytes-placeholder")
    dest = tmp_path / "extracted"

    monkeypatch.setattr(memory_access.shutil, "which", lambda name: f"/usr/bin/{name}")
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> object:
        seen["argv"] = argv
        # Simulate 7z writing out the decompressed memory image.
        (dest / "rocba.mem").write_bytes(b"\x00" * 8192)

        class _P:
            returncode = 0
            stdout = ""
            stderr = ""

        return _P()

    monkeypatch.setattr(memory_access.subprocess, "run", fake_run)
    img = memory_access.decompress(zip_path, dest)
    assert isinstance(seen["argv"], list) and seen["argv"][1] == "x"  # `7z x ...`
    assert img.path.name == "rocba.mem"
    assert not (dest / "Rocba-Memory.7z").exists()  # intermediate archive tidied away


def test_decompress_fails_closed_without_7z(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    zip_path = tmp_path / "Memory.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Rocba-Memory.7z", b"7z-bytes")
    monkeypatch.setattr(memory_access.shutil, "which", lambda name: None)
    with pytest.raises(BackendUnavailableError):
        memory_access.decompress(zip_path, tmp_path / "extracted")


def test_zip_member_basename_neutralises_traversal(tmp_path: Path) -> None:
    """A hostile member name is reduced to its basename - never escapes dest."""
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../etc/pwned.raw", b"PAGEDU64" + b"\x00" * 16)
    dest = tmp_path / "extracted"
    img = memory_access.decompress(zip_path, dest)
    assert img.path.parent.resolve() == dest.resolve()
    assert not (tmp_path / "etc" / "pwned.raw").exists()

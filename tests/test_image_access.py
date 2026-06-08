"""Sleuthkit image-access layer (Epic D deepening): fixed-argv, fail-closed, parsing.

All subprocess calls are mocked — no real TSK binaries or evidence are touched, so this
runs unchanged in CI. The real run is validated separately (human-gated) on the SIFT host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from siftmesh_core.evidence import image_access
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError

_MMLS_NTFS = """DOS Partition Table
Units are in 512-byte sectors

      Slot      Start        End          Length       Description
000:  Meta      0000000000   0000000000   0000000001   Primary Table (#0)
001:  -------   0000000000   0000002047   0000002048   Unallocated
002:  000:000   0000002048   0000206847   0000204800   NTFS / exFAT (0x07)
"""


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_which(monkeypatch: pytest.MonkeyPatch, present: bool = True) -> None:
    monkeypatch.setattr(
        image_access.shutil,
        "which",
        (lambda name: f"/usr/bin/{name}") if present else (lambda name: None),
    )


def test_tsk_tool_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch, present=False)
    with pytest.raises(BackendUnavailableError):
        image_access.list_partitions(Path("/x.e01"))


def test_list_partitions_parses_ntfs_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    monkeypatch.setattr(image_access.subprocess, "run", lambda *a, **k: _Proc(stdout=_MMLS_NTFS))
    parts = image_access.list_partitions(Path("/x.e01"))
    assert len(parts) == 1
    assert parts[0].start_sector == 2048
    assert "NTFS" in parts[0].description.upper()
    assert image_access.resolve_offset(Path("/x.e01")) == 2048


def test_resolve_offset_defaults_to_zero_for_single_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    # ROCBA's image: mmls exits non-zero / empty (no partition table) -> single volume @ 0.
    monkeypatch.setattr(image_access.subprocess, "run", lambda *a, **k: _Proc(returncode=1))
    assert image_access.resolve_offset(Path("/rocba.e01")) == 0


def test_find_inode_parses_and_handles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    monkeypatch.setattr(image_access.subprocess, "run", lambda *a, **k: _Proc(stdout="65-128-1\n"))
    assert image_access.find_inode(Path("/x.e01"), 0, "/Windows/foo") == "65-128-1"
    monkeypatch.setattr(
        image_access.subprocess, "run", lambda *a, **k: _Proc(stdout="Inode not found")
    )
    assert image_access.find_inode(Path("/x.e01"), 0, "/missing") is None


def test_extract_artifacts_orchestration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Drive the high-level walk with the primitives stubbed (no subprocess)."""
    dest = tmp_path / "extracted"

    monkeypatch.setattr(image_access, "resolve_offset", lambda image: 0)

    # Only the Security.evtx + $MFT artifacts "exist"; everything else is absent/skipped.
    def fake_find_inode(image: Path, offset: int, path: str, **kw: object) -> str | None:
        return "65-128-1" if path.endswith("Security.evtx") else None

    def fake_extract_inode(
        image: Path, offset: int, inode: str, dest_path: Path, **kw: object
    ) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"REAL-EXTRACTED-BYTES")
        return dest_path

    monkeypatch.setattr(image_access, "find_inode", fake_find_inode)
    monkeypatch.setattr(image_access, "extract_inode", fake_extract_inode)
    monkeypatch.setattr(image_access, "list_dir", lambda *a, **k: [])

    files = image_access.extract_artifacts(Path("/rocba.e01"), dest_dir=dest, offset=0)
    keys = {f.key for f in files}
    assert "security_evtx" in keys  # single-file path
    assert "mft" in keys  # $MFT (inode 0) always extracted
    for f in files:
        assert f.dest.is_file()
        assert len(f.sha256) == 64
        assert f.size_bytes > 0


def test_fixed_argv_uses_no_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """icat must be invoked with a list argv and shell never enabled (criterion 4)."""
    _patch_which(monkeypatch)
    seen: dict[str, object] = {}

    def fake_run(argv: object, **kwargs: object) -> _Proc:
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        handle = kwargs.get("stdout")
        if hasattr(handle, "write"):
            handle.write(b"bytes")  # type: ignore[union-attr]
        return _Proc(returncode=0)

    monkeypatch.setattr(image_access.subprocess, "run", fake_run)
    dest = tmp_path / "out.bin"
    image_access.extract_inode(Path("/x.e01"), 0, "12345", dest)
    assert isinstance(seen["argv"], list)  # argv is a list, not a shell string
    assert "shell" not in seen["kwargs"]  # default shell=False
    assert subprocess  # imported for type context

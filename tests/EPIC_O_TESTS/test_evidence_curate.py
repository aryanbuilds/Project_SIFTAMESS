"""Curated-evidence assembly (TUI wizard picker) — hardlink, originals untouched, EXDEV fallback."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest
from siftmesh_core.evidence.curate import CurateError, curate_evidence


def test_single_folder_shortcut_returns_it_directly(tmp_path: Path) -> None:
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "a.evtx").write_bytes(b"x")
    out = curate_evidence([ev], tmp_path / "dest")
    assert out == ev.resolve()  # used directly, no curation dir created
    assert not (tmp_path / "dest").exists()


def test_files_and_folders_hardlinked_originals_untouched(tmp_path: Path) -> None:
    f1 = tmp_path / "Security.evtx"
    f1.write_bytes(b"evtx-bytes")
    folder = tmp_path / "hives"
    (folder / "sub").mkdir(parents=True)
    (folder / "SYSTEM").write_bytes(b"hive")
    (folder / "sub" / "NTUSER.DAT").write_bytes(b"ntuser")
    before = {p: p.read_bytes() for p in (f1, folder / "SYSTEM", folder / "sub" / "NTUSER.DAT")}

    dest = tmp_path / "curated"
    out = curate_evidence([f1, folder], dest)
    assert out == dest.resolve()
    assert (dest / "Security.evtx").read_bytes() == b"evtx-bytes"
    assert (dest / "hives" / "SYSTEM").read_bytes() == b"hive"
    assert (dest / "hives" / "sub" / "NTUSER.DAT").read_bytes() == b"ntuser"
    # hard links share the inode (same filesystem) — zero extra disk
    assert (dest / "Security.evtx").stat().st_ino == f1.stat().st_ino
    # originals are byte-for-byte unchanged
    for p, data in before.items():
        assert p.read_bytes() == data


def test_cross_device_falls_back_to_copy(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    f1 = tmp_path / "a.evtx"
    f1.write_bytes(b"data")
    f2 = tmp_path / "b.evtx"
    f2.write_bytes(b"data2")

    def _exdev(src, dst):  # type: ignore[no-untyped-def]
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(os, "link", _exdev)
    dest = tmp_path / "curated"
    curate_evidence([f1, f2], dest)
    assert (dest / "a.evtx").read_bytes() == b"data"  # copied, not linked
    assert (dest / "a.evtx").stat().st_ino != f1.stat().st_ino  # distinct inode (a copy)


def test_empty_selection_and_missing_and_nonempty_dest_error(tmp_path: Path) -> None:
    with pytest.raises(CurateError):
        curate_evidence([], tmp_path / "d")
    with pytest.raises(CurateError):
        curate_evidence([tmp_path / "nope.evtx"], tmp_path / "d")
    dest = tmp_path / "d2"
    dest.mkdir()
    (dest / "stale").write_bytes(b"x")
    f = tmp_path / "f.evtx"
    f.write_bytes(b"y")
    with pytest.raises(CurateError):
        curate_evidence([f, tmp_path / "f.evtx"], dest)  # non-empty dest refused


def test_true_collision_errors(tmp_path: Path) -> None:
    fa = tmp_path / "dup.txt"
    fa.write_bytes(b"a")
    with pytest.raises(CurateError):  # the same file selected twice → dest-path collision
        curate_evidence([fa, fa], tmp_path / "c")

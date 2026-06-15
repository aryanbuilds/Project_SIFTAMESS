"""B1: streaming SHA-256 + deterministic, symlink-safe directory walk."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from siftmesh_core.evidence.hash_utils import FileFact, sha256_file, walk_files


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    data = b"forensic evidence \x00\x01\x02" * 1000
    target.write_bytes(data)
    assert sha256_file(target) == hashlib.sha256(data).hexdigest()


def test_sha256_streams_large_file(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    chunk = b"x" * (1024 * 1024)
    expected = hashlib.sha256()
    with target.open("wb") as out:
        for _ in range(20):  # 20 MiB - exercises the streaming read path
            out.write(chunk)
            expected.update(chunk)
    assert sha256_file(target) == expected.hexdigest()


def test_walk_deterministic_and_relative(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")

    facts = walk_files(tmp_path)
    assert [f.rel_path for f in facts] == ["a.txt", "b.txt", "sub/c.txt"]
    assert walk_files(tmp_path) == facts  # stable across calls
    assert all(isinstance(f, FileFact) for f in facts)

    first = next(f for f in facts if f.rel_path == "a.txt")
    assert first.sha256 == hashlib.sha256(b"a").hexdigest()
    assert first.size_bytes == 1
    assert first.mtime_utc.tzinfo is not None


def test_walk_skips_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("data")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this host")
    assert [f.rel_path for f in walk_files(tmp_path)] == ["real.txt"]

"""Filesystem fuzzy finder: ranking/determinism, modes, bounds, skip-list, walk fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")  # Matcher lives in textual

from siftmesh_core.tui import fs_search
from siftmesh_core.tui.fs_search import fuzzy_find


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small filesystem with evidence-ish files, a noise dir, and a hidden dir."""
    (tmp_path / "Security.evtx").write_text("x")
    (tmp_path / "System.evtx").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "PowerShell-Operational.evtx").write_text("x")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "deep.evtx").write_text("x")
    hidden = tmp_path / ".secret"
    hidden.mkdir()
    (hidden / "hidden.evtx").write_text("x")
    noise = tmp_path / "node_modules"
    noise.mkdir()
    (noise / "junk.evtx").write_text("x")
    return tmp_path


def _force_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make fuzzy_find use the pure-Python walk (no fd/find) for deterministic, CI-safe testing."""
    monkeypatch.setattr(fs_search.shutil, "which", lambda _name: None)


def test_walk_files_match_and_skip(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    hits = fuzzy_find("evtx", root=tree, mode="file")
    names = {p.name for p in hits}
    assert "Security.evtx" in names and "System.evtx" in names
    assert "PowerShell-Operational.evtx" in names and "deep.evtx" in names
    assert "notes.txt" not in names  # no fuzzy 'evtx' match
    # skip-list: hidden + node_modules contents excluded
    assert all(".secret" not in str(p) for p in hits)
    assert all("node_modules" not in str(p) for p in hits)


def test_walk_folders_only(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    hits = fuzzy_find("logs", root=tree, mode="folder")
    assert [p.name for p in hits] == ["logs"]
    # a folder query in file mode finds nothing here
    assert fuzzy_find("logs", root=tree, mode="file") == []


def test_deterministic_order(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    a = fuzzy_find("evtx", root=tree, mode="file")
    b = fuzzy_find("evtx", root=tree, mode="file")
    assert a == b  # same tree + query → identical order


def test_empty_query_and_bad_root(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    assert fuzzy_find("", root=tree) == []
    assert fuzzy_find("evtx", root=tree / "does-not-exist") == []
    assert fuzzy_find("evtx", root=tree / "Security.evtx") == []  # a file, not a dir


def test_max_depth_bounds(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    # depth 1 → only top-level files; subdir/deep.evtx (depth 2) excluded
    shallow = {p.name for p in fuzzy_find("evtx", root=tree, mode="file", max_depth=1)}
    assert "Security.evtx" in shallow
    assert "deep.evtx" not in shallow


def test_limit_cap(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _force_walk(monkeypatch)
    assert len(fuzzy_find("evtx", root=tree, mode="file", limit=2)) == 2


def test_default_enumerator_matches_walk(tree: Path) -> None:
    """Whatever enumerator is installed (fd/find) must return the same logical file set."""
    names = {p.name for p in fuzzy_find("evtx", root=tree, mode="file")}
    assert {"Security.evtx", "System.evtx", "deep.evtx"} <= names
    assert "junk.evtx" not in names  # node_modules excluded by every strategy

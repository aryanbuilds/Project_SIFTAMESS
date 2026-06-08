"""Protocol SIFT inspection + capability map (D11): multi-candidate detection, honest posture."""

from __future__ import annotations

from pathlib import Path

import pytest
from siftmesh_core import protocol_sift as ps
from siftmesh_core.evidence.path_policy import PathPolicyViolation
from siftmesh_core.run_dir import new_run_dir
from siftmesh_core.schemas.protocol_sift import ProtocolSiftCapabilityMap


def test_resolve_tool_prefers_existing_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vol = tmp_path / "vol"
    vol.write_text("", encoding="utf-8")
    monkeypatch.setattr(ps, "SIFT_TOOL_CANDIDATES", {"volatility3": (str(vol), "/nope/vol.py")})
    assert ps.resolve_tool("volatility3") == str(vol)


def test_resolve_tool_falls_back_to_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ps, "SIFT_TOOL_CANDIDATES", {"volatility3": ("/nope/vol",)})
    monkeypatch.setattr(ps, "SIFT_TOOL_WHICH", {"volatility3": "vol"})
    monkeypatch.setattr(
        ps.shutil, "which", lambda name: "/usr/local/bin/vol" if name == "vol" else None
    )
    assert ps.resolve_tool("volatility3") == "/usr/local/bin/vol"
    monkeypatch.setattr(ps.shutil, "which", lambda name: None)
    assert ps.resolve_tool("volatility3") is None  # honest absence


def test_capability_map_written_and_valid(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    path = ps.write_protocol_sift_capability_map(run.root)
    assert path == run.protocol_sift_capabilities
    assert path.is_relative_to(run.root.resolve())  # path-policed under the run dir
    cap = ProtocolSiftCapabilityMap.model_validate_json(path.read_text(encoding="utf-8"))
    assert cap.run_id == run.run_id
    assert cap.checks  # per-check pass/fail list present
    names = {c.name for c in cap.checks}
    assert "tool:dotnet" in names and any(n.startswith("skill:") for n in names)


def test_capability_map_honest_absence(tmp_path: Path) -> None:
    # An empty fake $HOME/.claude => Protocol SIFT skill layer reported absent (honest).
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    cap = ps.build_capability_map("RUN-TEST", home=fake_home)
    assert cap.protocol_sift_installed is False
    assert set(cap.skills_missing) == set(ps.PROTOCOL_SIFT_SKILLS)
    assert cap.skills_present == []


def test_capability_map_write_path_policed(tmp_path: Path) -> None:
    run = new_run_dir(base=tmp_path / "case_runs")
    # The run dir must not live inside the evidence tree (path policy guard).
    with pytest.raises(PathPolicyViolation):
        ps.write_protocol_sift_capability_map(run.root, evidence_root=run.root)

"""E3 (case brief + assumptions) and E5 (tool map) context documents."""

from __future__ import annotations

from collections.abc import Callable

from siftmesh_core.config import load_settings
from siftmesh_core.mcp_gateway.registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS
from siftmesh_core.orchestrator.planner import generate_plan
from siftmesh_core.run_dir import RunPaths

SyntheticRun = Callable[..., RunPaths]


def test_case_brief_and_assumptions_exist(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    assert run.case_brief.is_file()
    assumptions = run.assumptions.read_text(encoding="utf-8")
    assert "Timezone" in assumptions  # >=1 explicit assumption (E3 DoD)


def test_case_brief_lists_scope(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    brief = run.case_brief.read_text(encoding="utf-8")
    assert "Objective" in brief and "Constraints" in brief


def test_tool_map_only_allowlisted_no_forbidden(synthetic_run: SyntheticRun) -> None:
    run = synthetic_run()
    generate_plan(run, settings=load_settings())
    tool_map = run.tool_map.read_text(encoding="utf-8")
    # tools are always rendered as `code` tokens; no forbidden tool may appear as one
    for forbidden in FORBIDDEN_TOOLS:
        assert f"`{forbidden}`" not in tool_map
    # the families present must surface their real allowlisted tools
    for tool in ("parse_evtx_security", "extract_registry_run_keys", "build_timeline"):
        assert f"`{tool}`" in tool_map and tool in ALLOWED_TOOLS

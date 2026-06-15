"""I1 - AgentProfile schema + the packaged agent_profiles.yaml registry."""

from __future__ import annotations

import pytest
import siftmesh_core.adapters  # noqa: F401  (importing registers all adapters)
from pydantic import ValidationError
from siftmesh_core.adapters.base import _REGISTRY
from siftmesh_core.adapters.profiles import load_profiles
from siftmesh_core.schemas.agent_profile import AgentProfile

_EXPECTED = {
    "deterministic_executor",
    "claude_headless",
    "opencode_headless",
    "generic_shell",
    # Epic Q - agent-neutral headless connectors.
    "gemini_headless",
    "codex_headless",
}


def test_profile_schema_valid() -> None:
    profile = AgentProfile(profile_id="x", kind="claude", model_tier="high", cost_class="expensive")
    assert profile.output_format == "task_result_json"  # default
    assert profile.max_runtime_seconds == 300
    with pytest.raises(ValidationError):  # unknown kind rejected (Literal)
        AgentProfile(profile_id="y", kind="not_a_kind", model_tier="high", cost_class="cheap")


def test_agent_profiles_yaml_loads() -> None:
    profiles = load_profiles()
    assert set(profiles) == _EXPECTED
    assert all(isinstance(p, AgentProfile) for p in profiles.values())
    assert profiles["deterministic_executor"].kind == "deterministic"
    assert profiles["claude_headless"].cost_class == "expensive"


def test_every_profile_maps_to_a_registered_adapter() -> None:
    # the registry resolves a profile_id to a registered adapter; every profile must be registered
    assert set(load_profiles()) <= set(_REGISTRY)

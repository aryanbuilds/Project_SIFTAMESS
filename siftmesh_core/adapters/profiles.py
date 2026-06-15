"""Agent-profile registry loader (Epic I, I1).

Loads the declarative :class:`AgentProfile` set from a YAML file (the packaged default ships beside
this module; a caller may pass an override). Each entry is validated through the Pydantic schema (an
unknown ``kind`` or typo'd field fails closed at load). The ``profile_id`` keys MUST match a
registered adapter so :func:`siftmesh_core.adapters.get_adapter` can resolve them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from siftmesh_core.schemas.agent_profile import AgentProfile

DEFAULT_PROFILES_YAML = Path(__file__).parent / "agent_profiles.yaml"


def load_profiles(path: Path | str | None = None) -> dict[str, AgentProfile]:
    """Load + validate the agent profiles; return ``{profile_id: AgentProfile}``.

    Raises ``FileNotFoundError`` if the file is missing and ``pydantic.ValidationError`` /
    ``ValueError`` on a malformed entry (fail closed - never a partial/typo'd profile set).
    """
    target = Path(path) if path else DEFAULT_PROFILES_YAML
    if not target.is_file():
        raise FileNotFoundError(f"agent profiles file not found: {target}")
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    profiles = [AgentProfile.model_validate(entry) for entry in data.get("profiles", [])]
    by_id = {p.profile_id: p for p in profiles}
    if len(by_id) != len(profiles):
        raise ValueError("duplicate profile_id in agent profiles")
    return by_id


def effective_model(settings: object, profile_id: str, default: str | None) -> str | None:
    """The model for ``profile_id``: the operator's ``agent_models`` override, else the default.

    Lets the user pin a model per provider (``--model gemini=…`` / `setup` / onboarding TUI) without
    editing the packaged profile YAML; an empty/missing override falls back to the profile default.
    """
    override = (getattr(settings, "agent_models", None) or {}).get(profile_id)
    return override or default

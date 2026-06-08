"""SIFTMesh global configuration and caps (pydantic-settings 2.14.x).

Deterministic, auditable precedence (highest -> lowest):
    init args > env vars (SIFTMESH_ prefix) > siftmesh.toml > model defaults

Nested caps are overridden via env with the prefix + delimiter form, e.g.
    SIFTMESH_CAPS__MAX_ITERATIONS=7
(NOT SIFTMESH_MAX_ITERATIONS).

FAIL-CLOSED NOTE: a missing `siftmesh.toml` does NOT raise here —
TomlConfigSettingsSource silently returns {}. Config-presence enforcement must
live separately (e.g. an explicit Path("siftmesh.toml").exists() check in
`siftmesh doctor`). `extra="forbid"` makes a typo'd key fail at load.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

CONFIG_FILENAME = "siftmesh.toml"


class Caps(BaseModel):
    """Full-auto safety caps (CLAUDE.md §11)."""

    max_iterations: int = 3
    max_agent_tasks: int = 10
    max_parallel_tasks: int = 3
    max_tool_runtime_seconds: int = 300


class SiftmeshSettings(BaseSettings):
    """Top-level SIFTMesh settings with deterministic source precedence."""

    model_config = SettingsConfigDict(
        env_prefix="SIFTMESH_",
        env_nested_delimiter="__",  # SIFTMESH_CAPS__MAX_ITERATIONS=7
        toml_file=CONFIG_FILENAME,
        extra="forbid",  # fail-closed: reject typo'd/unknown keys at load
    )

    backend_mode: Literal["real", "sift_lane", "auto"] = "real"
    evidence_mode: Literal["read_only"] = "read_only"
    raw_shell: bool = False
    allow_destructive_tools: bool = False
    caps: Caps = Field(default_factory=Caps)

    # SIFT-lane host tools (Epic D deepening). Off by default; enabled for real-image
    # runs on a SANS SIFT host. Missing tools are reported by `doctor` (WARN) and fail
    # closed when actually used — never faked.
    extraction_tools_enabled: bool = False
    vol_path: str = "/opt/volatility3/bin/vol"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # First element = highest precedence. dotenv/file-secret intentionally
        # omitted (disabled); add them back if .env / Docker secrets are needed.
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
        )


def load_settings(**overrides: Any) -> SiftmeshSettings:
    """Load settings; `overrides` act as highest-precedence init args."""
    return SiftmeshSettings(**overrides)

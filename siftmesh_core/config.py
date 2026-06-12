"""SIFTMesh configuration and caps.

Source precedence: init args > env vars > project TOML > global TOML > defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

CONFIG_FILENAME = "siftmesh.toml"


def global_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "siftmesh" / CONFIG_FILENAME


class Caps(BaseModel):
    max_iterations: int = 3
    max_agent_tasks: int = 10
    max_parallel_tasks: int = 3
    max_tool_runtime_seconds: int = 300


class SiftmeshSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIFTMESH_",
        env_nested_delimiter="__",
        toml_file=CONFIG_FILENAME,
        extra="forbid",
    )

    backend_mode: Literal["real", "sift_lane", "auto"] = "real"
    evidence_mode: Literal["read_only"] = "read_only"
    raw_shell: bool = False
    allow_destructive_tools: bool = False
    caps: Caps = Field(default_factory=Caps)

    extraction_tools_enabled: bool = False
    vol_path: str = "/opt/volatility3/bin/vol"
    vol_symbol_dirs: str = Field(
        default_factory=lambda: str(Path.home() / ".cache" / "siftmesh" / "vol_symbols")
    )
    ez_tools_dir: str = "/opt/zimmermantools"
    enable_super_timeline: bool = False
    log2timeline_path: str | None = None
    psort_path: str | None = None

    executor_selection: Literal["deterministic", "live", "auto"] = "deterministic"
    default_agent_profile: str = "deterministic_executor"
    claude_cli_path: str = "claude"
    opencode_cli_path: str = "opencode"
    generic_agent_cmd: str | None = None
    agent_timeout_seconds: int = 600
    live_extraction: bool = False
    heavy_tool_timeout_seconds: int = 1800
    parallel_dispatch: bool = False

    agent_preference: list[str] = Field(
        default_factory=lambda: ["claude_headless", "opencode_headless", "deterministic_executor"]
    )
    role_profiles: dict[str, str] = Field(default_factory=dict)
    claude_permission_mode: str = "dontAsk"

    llm_critic_enabled: bool = False
    judge: str | None = None
    agent_models: dict[str, str] = Field(default_factory=dict)
    agent_aliases: dict[str, str] = Field(default_factory=dict)
    judge_api_base: str | None = None
    judge_drop_params: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
            TomlConfigSettingsSource(settings_cls, toml_file=global_config_path()),
        )


def load_settings(**overrides: Any) -> SiftmeshSettings:
    return SiftmeshSettings(**overrides)


def save_agent_selection(
    executor_selection: str,
    agent_preference: list[str],
    *,
    scope: Literal["global", "project"] = "global",
    role_profiles: dict[str, str] | None = None,
    judge: str | None = None,
    llm_critic_enabled: bool | None = None,
    agent_models: dict[str, str] | None = None,
    agent_aliases: dict[str, str] | None = None,
    judge_api_base: str | None = None,
    judge_drop_params: bool | None = None,
) -> Path:
    import tomlkit

    target = global_config_path() if scope == "global" else Path(CONFIG_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = (
        tomlkit.parse(target.read_text(encoding="utf-8"))
        if target.is_file()
        else tomlkit.document()
    )
    doc["executor_selection"] = executor_selection
    doc["agent_preference"] = list(agent_preference)
    if role_profiles is not None:
        doc["role_profiles"] = dict(role_profiles)
    if judge is not None:
        doc["judge"] = judge
    if llm_critic_enabled is not None:
        doc["llm_critic_enabled"] = llm_critic_enabled
    if agent_models is not None:
        existing = dict(doc.get("agent_models", {}))
        existing.update(agent_models)
        doc["agent_models"] = existing
    if agent_aliases is not None:
        existing_aliases = dict(doc.get("agent_aliases", {}))
        existing_aliases.update(agent_aliases)
        doc["agent_aliases"] = existing_aliases
    if judge_api_base is not None:
        doc["judge_api_base"] = judge_api_base
    if judge_drop_params is not None:
        doc["judge_drop_params"] = judge_drop_params
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target

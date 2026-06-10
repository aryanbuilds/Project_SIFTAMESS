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
    # Writable Volatility 3 symbol cache (its install dir is usually read-only, so vol
    # cannot cache downloaded PDB symbols there). None => vol uses its own default.
    vol_symbol_dirs: str | None = None
    # EZ Tools install dir for the SIFT-lane backend (D12); EvtxECmd/MFTECmd/RECmd .dlls
    # run via `dotnet <dll>`. Missing tool fails closed when sift_lane is actually used.
    ez_tools_dir: str = "/opt/zimmermantools"

    # Executor adapters (Epic F). The deterministic floor is the safe default so CI and
    # the no-keys demo never need an agent CLI/key. `executor_selection`: "deterministic"
    # = always the floor; "live" = prefer the live agent (fall closed to the floor when
    # absent); "auto" = live when available else floor.
    executor_selection: Literal["deterministic", "live", "auto"] = "deterministic"
    default_agent_profile: str = "deterministic_executor"
    claude_cli_path: str = "claude"
    opencode_cli_path: str = "opencode"
    # Fixed-argv command for the generic shell adapter (F7); None => unavailable.
    generic_agent_cmd: str | None = None
    # Whole-agent-invocation wall-clock (F7/F8); distinct from caps.max_tool_runtime_seconds. A live
    # agent investigating via multiple typed-tool calls + reasoning routinely exceeds 5 min, so the
    # default is 10 min (override per env/toml for slower models or larger artifacts).
    agent_timeout_seconds: int = 600
    # Executor tiering (scale fixes). Heavy, tool-bound tasks (disk-image extraction, memory
    # triage) add nothing under a live agent and time out its wrapper, so they run on the
    # deterministic floor even when a live agent is selected — unless `live_extraction` is set
    # (`run --all-live`, for the per-artifact emergent-correction demo). Their floor tool timeout
    # is `heavy_tool_timeout_seconds` (not the 300 s default), since a 22 GB image / 19 GB memory
    # dump legitimately takes many minutes.
    live_extraction: bool = False
    heavy_tool_timeout_seconds: int = 1800

    # Multi-agent layer (Epic I). When live is selected, profiles are tried in this order and the
    # first available() wins; the deterministic floor is always the final fall-back. role_profiles
    # optionally pins a profile per task role (overrides the chain head). claude_permission_mode is
    # the non-interactive headless permission value: "dontAsk" auto-denies any tool not explicitly
    # allowed (the sandbox; do NOT use acceptEdits/bypassPermissions for the forensic agent).
    agent_preference: list[str] = Field(
        default_factory=lambda: ["claude_headless", "opencode_headless", "deterministic_executor"]
    )
    role_profiles: dict[str, str] = Field(default_factory=dict)
    claude_permission_mode: str = "dontAsk"

    # Optional Layer-2 LLM adversarial critic (Epic G8). Off by default; the Layer-1
    # deterministic critic is always sufficient. The real pass needs the F8 agent.
    llm_critic_enabled: bool = False

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

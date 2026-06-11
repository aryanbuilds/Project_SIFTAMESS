"""SIFTMesh global configuration and caps (pydantic-settings 2.14.x).

Deterministic, auditable precedence (highest -> lowest):
    init args > env vars (SIFTMESH_ prefix) > ./siftmesh.toml (project) >
    ~/.config/siftmesh/siftmesh.toml (global) > model defaults

Nested caps are overridden via env with the prefix + delimiter form, e.g.
    SIFTMESH_CAPS__MAX_ITERATIONS=7
(NOT SIFTMESH_MAX_ITERATIONS).

`siftmesh setup` (Epic O onboarding) persists the chosen agent set: by default to the GLOBAL
file ("select once"); a PROJECT `./siftmesh.toml` overrides it for a specific case. See
``save_agent_selection`` / ``global_config_path``.

FAIL-CLOSED NOTE: a missing TOML does NOT raise here — TomlConfigSettingsSource silently
returns {}. Config-presence enforcement lives separately (e.g. `siftmesh doctor`).
`extra="forbid"` makes a typo'd key fail at load.
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
    """The user-global config file: ``${XDG_CONFIG_HOME:-~/.config}/siftmesh/siftmesh.toml``."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "siftmesh" / CONFIG_FILENAME


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
    # Writable Volatility 3 symbol cache (its install dir is usually read-only, so vol cannot
    # cache downloaded PDB symbols there). Defaults to a per-user cache dir (created on use +
    # by `doctor --setup`), so memory triage Just Works with no manual export. Override via
    # SIFTMESH_VOL_SYMBOL_DIRS / toml.
    vol_symbol_dirs: str = Field(
        default_factory=lambda: str(Path.home() / ".cache" / "siftmesh" / "vol_symbols")
    )
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
    # Deterministic parallel dispatch (Epic B5 / bd vd2t). OFF by default → strictly sequential,
    # byte-identical (golden + manual==auto unaffected). When on AND >1 task AND
    # caps.max_parallel_tasks > 1, tasks execute concurrently into per-task staging dirs and are
    # committed in contract order with renumbered ids — byte-identical to sequential (proven by
    # test_parallel_dispatch). Tasks with a derived-origin input fall back to sequential. Opt in
    # via `run --parallel`. The real win is the live-agent path (minutes-long subprocesses).
    parallel_dispatch: bool = False

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
    # Provider-flexible Tier-2 judge + merge-synthesis backend (advisory only; never promotes).
    # None => Claude CLI (back-compat). Forms: "cli:claude|gemini|codex|opencode" (vendor CLI,
    # tool-less, subscription OR API via its own auth) or "litellm:<model>" (LiteLLM SDK, API/cloud,
    # e.g. "litellm:gemini/gemini-2.5-pro", "litellm:vertex_ai/...", "litellm:openai/gpt-5.5").
    # A bare name ("gemini") => "cli:gemini". Fails SOFT: an unavailable judge is skipped.
    judge: str | None = None
    # Per-provider model override: profile_id -> model id (wins over the profile's YAML default).
    # Keys: claude_headless / gemini_headless / codex_headless / opencode_headless. Empty = the
    # profile default (gemini auto-routes). Set via `--model gemini=…` / `setup` / onboarding TUI.
    agent_models: dict[str, str] = Field(default_factory=dict)

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
        # Project (CWD) TOML overrides the user-global TOML (which `setup` writes by default).
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),  # ./siftmesh.toml (project)
            TomlConfigSettingsSource(settings_cls, toml_file=global_config_path()),  # ~/.config
        )


def load_settings(**overrides: Any) -> SiftmeshSettings:
    """Load settings; `overrides` act as highest-precedence init args."""
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
) -> Path:
    """Persist the onboarding agent choice to a TOML file; return the path written.

    Read-merge-write via tomlkit so any other keys (and comments) the operator has are preserved —
    only ``executor_selection``/``agent_preference`` (+ ``role_profiles``/``judge`` if set) are
    set. The GLOBAL file is the "select once" default; a PROJECT ``./siftmesh.toml`` overrides it
    (loader precedence above). The values are validated by re-loading SiftmeshSettings on next use.
    """
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
        # merge (don't clobber other providers' pins the operator already saved)
        existing = dict(doc.get("agent_models", {}))
        existing.update(agent_models)
        doc["agent_models"] = existing
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target

"""Epic O - global+project config persistence for the agent selection (save + loader precedence)."""

from __future__ import annotations

from pathlib import Path

from siftmesh_core.config import global_config_path, load_settings, save_agent_selection


def _isolate(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """Point HOME (→ global config) and CWD (→ project config) at fresh tmp dirs."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(cwd)
    # the loader reads SIFTMESH_* env - clear any that would shadow the toml under test
    for var in ("SIFTMESH_AGENT_PREFERENCE", "SIFTMESH_EXECUTOR_SELECTION"):
        monkeypatch.delenv(var, raising=False)
    return home, cwd


def test_save_global_then_loaded(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    target = save_agent_selection(
        "auto", ["gemini_headless", "deterministic_executor"], scope="global"
    )
    assert target == global_config_path()
    assert target.is_file()
    settings = load_settings()
    assert settings.executor_selection == "auto"
    assert settings.agent_preference == ["gemini_headless", "deterministic_executor"]


def test_project_overrides_global(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    save_agent_selection("auto", ["gemini_headless", "deterministic_executor"], scope="global")
    save_agent_selection("live", ["claude_headless", "deterministic_executor"], scope="project")
    settings = load_settings()
    # CWD project file wins over the global file
    assert settings.executor_selection == "live"
    assert settings.agent_preference == ["claude_headless", "deterministic_executor"]


def test_save_merges_preserves_other_keys(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    # a pre-existing project toml with an unrelated key must survive the merge
    Path("siftmesh.toml").write_text(
        "agent_timeout_seconds = 1200\nllm_critic_enabled = true\n", encoding="utf-8"
    )
    save_agent_selection("live", ["codex_headless", "deterministic_executor"], scope="project")
    settings = load_settings()
    assert settings.agent_preference == ["codex_headless", "deterministic_executor"]
    assert settings.agent_timeout_seconds == 1200  # preserved
    assert settings.llm_critic_enabled is True  # preserved


def test_default_when_no_config(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    settings = load_settings()
    assert settings.executor_selection == "deterministic"  # model default
    assert settings.agent_preference[0] == "claude_headless"


def test_agent_aliases_merge_and_load(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    save_agent_selection(
        "auto",
        ["claude_headless", "deterministic_executor"],
        scope="global",
        agent_aliases={"claude_headless": "Ada"},
    )
    # a second save for a different alias must not clobber the first (merge)
    save_agent_selection(
        "auto",
        ["claude_headless", "deterministic_executor"],
        scope="global",
        agent_aliases={"gemini_headless": "Gem"},
    )
    settings = load_settings()
    assert settings.agent_aliases == {"claude_headless": "Ada", "gemini_headless": "Gem"}


def test_judge_litellm_extras_persist(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    save_agent_selection(
        "deterministic",
        ["deterministic_executor"],
        scope="global",
        judge="litellm:openai/glm-4.6",
        judge_api_base="https://api.opencode.ai/zen/v1",
        judge_drop_params=True,
    )
    settings = load_settings()
    assert settings.judge == "litellm:openai/glm-4.6"
    assert settings.judge_api_base == "https://api.opencode.ai/zen/v1"
    assert settings.judge_drop_params is True
    # defaults when never set
    save_agent_selection("deterministic", ["deterministic_executor"], scope="project")
    assert load_settings().judge_drop_params is True  # global still set; project didn't touch it

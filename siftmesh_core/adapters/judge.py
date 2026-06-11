"""Provider-flexible advisory reasoning call (the Tier-2 judge + merge synthesis).

`invoke_judge_text(prompt, settings)` is a single TOOL-LESS reasoning call dispatched by
``settings.judge``:
- ``None`` / ``"claude"`` / ``"cli:claude"`` → ``claude_adapter.invoke_claude_text`` (back-compat).
- ``"cli:<agent>"`` (claude|gemini|codex|opencode) → the vendor CLI in tool-less mode (NO
  ``--mcp-config``), from its headless recipe. Uses the agent's OWN auth → subscription OR API.
- ``"litellm:<model>"`` (e.g. ``gemini/gemini-2.5-pro``, ``vertex_ai/…``, ``openai/…``,
  ``anthropic/…``, ``moonshot/…``, ``minimax/…``) → the LiteLLM SDK (API-key/cloud providers).

FAIL-SOFT everywhere: the Tier-2 judge is OPTIONAL + advisory, so any failure (missing CLI / key /
``litellm`` extra, timeout, bad output) returns ``None`` — never raises, never fabricates. Caller
logs ``tier2_judge_skipped`` and continues on Tier-1 (the deterministic critic stays the sole
promoter). Fail-*closed* is reserved for the safety gates (path policy, forbidden tools, backends).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess

from siftmesh_core.adapters.claude_adapter import claude_available, invoke_claude_text
from siftmesh_core.adapters.headless import extract_agent_text
from siftmesh_core.adapters.profiles import load_profiles
from siftmesh_core.adapters.sandbox import minimal_child_env

# Friendly judge-agent name → its headless profile id (the tool-less CLI judge reuses the recipe).
_CLI_PROFILE = {
    "claude": "claude_headless",
    "gemini": "gemini_headless",
    "codex": "codex_headless",
    "opencode": "opencode_headless",
}


def parse_judge(judge: str | None) -> tuple[str, str]:
    """Parse ``settings.judge`` into ``(backend, target)``.

    ``None`` → ``("cli", "claude")`` (back-compat); a bare name (``"gemini"``) → ``("cli", name)``;
    ``"cli:<agent>"`` / ``"litellm:<model>"`` split on the first colon.
    """
    if not judge:
        return ("cli", "claude")
    if ":" in judge:
        backend, target = judge.split(":", 1)
        return (backend.strip(), target.strip())
    return ("cli", judge.strip())


def judge_ready(settings: object) -> tuple[bool, str]:
    """``(ready, label)`` for the configured judge — for doctor/agents display (no LLM call)."""
    backend, target = parse_judge(getattr(settings, "judge", None))
    if backend == "litellm":
        if importlib.util.find_spec("litellm") is None:
            return (False, f"litellm:{target} (install the `llm` extra)")
        return (True, f"litellm:{target}")
    if backend == "cli":
        if target == "claude":
            return (bool(claude_available(settings)), "cli:claude")
        prof_id = _CLI_PROFILE.get(target)
        if prof_id is None:
            return (False, f"unknown judge agent '{target}'")
        prof = load_profiles().get(prof_id)
        cli = prof.launch_argv[0] if (prof and prof.launch_argv) else None
        return (bool(cli and shutil.which(cli)), f"cli:{target}")
    return (False, f"unknown judge backend '{backend}'")


def invoke_judge_text(prompt: str, settings: object, *, timeout: int | None = None) -> str | None:
    """Tool-less reasoning text from the configured judge backend, or ``None`` (fail-soft)."""
    backend, target = parse_judge(getattr(settings, "judge", None))
    try:
        if backend == "litellm":
            return _litellm_text(target, prompt, settings=settings, timeout=timeout)
        if backend == "cli":
            if target == "claude":
                return invoke_claude_text(prompt, settings, timeout=timeout)
            return _cli_text(target, prompt, settings, timeout=timeout)
    except Exception:  # any judge error is advisory — never propagate
        return None
    return None


def _cli_text(agent: str, prompt: str, settings: object, *, timeout: int | None) -> str | None:
    """Run a vendor CLI in tool-less mode (no MCP) from its headless recipe; return its text."""
    prof = load_profiles().get(_CLI_PROFILE.get(agent, ""))
    if prof is None or not prof.launch_argv:
        return None
    if shutil.which(prof.launch_argv[0]) is None:
        return None
    argv = [*prof.launch_argv, prompt]
    if prof.model and prof.model_flag:
        argv += [prof.model_flag, prof.model]
    argv += [*prof.extra_argv, *prof.native_tool_argv]  # tool-less: deny flags ok, NO --mcp-config
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout or getattr(settings, "agent_timeout_seconds", 600),
            shell=False,
            check=False,
            env=minimal_child_env(keep=[*prof.auth_env, *prof.env_passthrough]),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    text = extract_agent_text(proc.stdout, prof.output_format).strip()
    return text or None


def _litellm_text(model: str, prompt: str, *, settings: object, timeout: int | None) -> str | None:
    """Route a tool-less call through the LiteLLM SDK (API-key/cloud providers); None if absent."""
    try:
        import litellm
    except ImportError:
        return None
    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout or getattr(settings, "agent_timeout_seconds", 600),
        )
        content = resp.choices[0].message.content
    except Exception:
        return None
    return content.strip() if isinstance(content, str) and content.strip() else None

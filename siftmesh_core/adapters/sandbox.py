"""Cross-cutting agent-subprocess safety primitives (Epic Q corrections).

Every live agent subprocess (claude/opencode/headless) must run with three containment measures so a
prompt-injected or misbehaving agent cannot touch evidence, escape the run dir, or exfiltrate the
operator's credentials:

- **cwd pinning** — launch the agent in a clean, run-scoped scratch dir, never the operator's CWD
  (which may sit next to ``evidence/`` and from which these CLIs auto-load TRUSTED instruction files
  like ``GEMINI.md`` / ``AGENTS.md`` / ``CLAUDE.md`` — a prompt-injection channel that bypasses the
  spotlighting design entirely).
- **env minimization** — hand the child only an allowlisted base env plus the *one* agent's own
  declared credentials, never the full orchestrator environment (which holds every other provider's
  API keys and cloud creds).

These are defence-in-depth: the typed-tool boundary + critic remain the primary governance.
"""

from __future__ import annotations

import os
from pathlib import Path

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.run_dir import RunPaths

# Base env always handed to an agent subprocess (no secrets here). HOME lets the CLI find its own
# config/credential store (~/.gemini, ~/.codex, ~/.claude); the rest are locale/term/tmp basics.
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "LANG",
    "TMPDIR",
    "TZ",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
)


def minimal_child_env(*, keep: tuple[str, ...] | list[str] = ()) -> dict[str, str]:
    """An allowlisted child environment: base vars + locale (LC_*) + only the named ``keep`` vars.

    ``keep`` is the agent profile's own ``auth_env`` + ``env_passthrough`` — so a gemini subprocess
    sees GEMINI_API_KEY but never ANTHROPIC_API_KEY / OPENAI_API_KEY / cloud creds.
    """
    env = {k: os.environ[k] for k in (*_ENV_ALLOWLIST, *keep) if k in os.environ}
    env.update({k: v for k, v in os.environ.items() if k.startswith("LC_")})
    return env


def scratch_cwd(run: RunPaths, task_id: str) -> str:
    """Create + return a clean per-task scratch dir UNDER the run (the agent subprocess's cwd).

    Path-policed (never escapes the run dir); created fresh by us, so it holds no evidence and no
    attacker-planted CWD instruction file. Bounds any agent 'workspace' read/write to the run dir.
    """
    target = safe_write_path(run.root, Path("scratch") / task_id)
    target.mkdir(parents=True, exist_ok=True)
    return str(target)

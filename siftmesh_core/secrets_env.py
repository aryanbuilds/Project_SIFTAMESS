"""Provider-credential env file (``~/.config/siftmesh/.env``, 600-perm) loaded into ``os.environ``.

Agent CLIs (claude/codex/gemini/opencode) authenticate via their OWN login + credential files; this
module exists for the **advisory Tier-2 LiteLLM judge** and any provider API key the operator enters
in the TUI. Keys live in a 600-perm dotfile (**never** in ``siftmesh.toml``, which may be committed)
and are loaded into ``os.environ`` on startup so:

- the in-process LiteLLM judge (``adapters/judge._litellm_text``) reads them, and
- child agents inherit them via the engine's existing ``minimal_child_env(keep=auth_env)``.

This is orthogonal to pydantic-settings' (intentionally disabled) dotenv source: that source is for
``SIFTMESH_*`` settings keys; this holds PROVIDER credentials. **Never log a value.**
"""

from __future__ import annotations

import os
from pathlib import Path

# Provider credential env vars the TUI knows how to write. The loader still loads any var present in
# the file (forward-compat), but the key-entry UI maps providers to exactly these.
KNOWN_SECRET_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENCODE_API_KEY",
)


def secrets_env_path() -> Path:
    """The provider-credential env file: ``${XDG_CONFIG_HOME:-~/.config}/siftmesh/.env``."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "siftmesh" / ".env"


def _parse(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines (``#`` comments + blanks ignored; surrounding quotes stripped)."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def read_secrets() -> dict[str, str]:
    """Return the env file as a dict (``{}`` if absent/unreadable). Never raises."""
    path = secrets_env_path()
    if not path.is_file():
        return {}
    try:
        return _parse(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def save_secret(var: str, value: str) -> Path:
    """Write/update ``VAR=value`` in the 600-perm env file (read-merge-write). Returns the path.

    Created with mode 0o600 from the start (no world-readable window) and re-``chmod``'d on every
    write so a pre-existing looser file is tightened. Never logs the value.
    """
    var = var.strip()
    if not var or "=" in var or "\n" in var:
        raise ValueError(f"invalid env var name: {var!r}")
    value = value.strip()
    path = secrets_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_secrets()
    data[var] = value
    body = "".join(f"{k}={data[k]}\n" for k in sorted(data))  # sorted = deterministic
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
    finally:
        os.close(fd)
    path.chmod(0o600)  # tighten perms even if the file pre-existed
    return path


def load_secrets_into_env(*, override: bool = False) -> list[str]:
    """Load the env file into ``os.environ``; return the var names set. Never raises, never logs.

    By default a real shell export wins (``override=False`` skips vars already in the environment),
    so an interactive ``export GEMINI_API_KEY=…`` is not silently shadowed by a stale saved key.
    """
    set_vars: list[str] = []
    for key, value in read_secrets().items():
        if not value:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            set_vars.append(key)
    return set_vars

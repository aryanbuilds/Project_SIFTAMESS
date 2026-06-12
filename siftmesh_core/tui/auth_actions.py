"""Auth helpers for the onboarding + judge tabs (Textual-free core; the screen runs them threaded).

Two jobs:
- ``auth_command(profile_id)`` — the exact vendor login argv to run interactively (the screen wraps
  it in ``App.suspend()`` so the real TTY drives the browser/paste flow), or ``None`` for an agent
  with no interactive login (gemini → API-key only since consumer OAuth ended 2026).
- ``save_provider_key`` / ``validate_provider_key`` — persist a LiteLLM provider key to the 600-perm
  env file (``secrets_env``) only after it validates (free ``get_valid_models`` endpoint, then a
  minimal ``check_valid_key`` call). Never logs the key. A rejected key is NOT persisted; if LiteLLM
  is absent the key is saved unvalidated (honest message).

Pure logic only — the caller is responsible for running ``save_provider_key`` (network) and the
``subprocess.run(auth_command(...))`` in a worker thread, never on the UI thread.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Interactive vendor login per profile. None ⇒ no interactive login (API key only).
_AUTH_CMD: dict[str, list[str] | None] = {
    "claude_headless": ["claude", "setup-token"],
    "opencode_headless": ["opencode", "auth", "login"],
    "codex_headless": ["codex", "login"],
    "gemini_headless": None,  # consumer OAuth removed 2026 → GEMINI_API_KEY only
}


def auth_command(profile_id: str) -> list[str] | None:
    """Interactive vendor-login argv for a profile, or ``None`` (API-key-only / unknown)."""
    return _AUTH_CMD.get(profile_id)


@dataclass(frozen=True)
class ProviderSpec:
    """How LiteLLM reaches a provider: the env var to set, its provider id, and a model prefix."""

    env: str
    llm_provider: str
    prefix: str
    default_model: str | None = None
    needs_api_base: bool = False


# LiteLLM provider credential map for the Tier-2 judge tab (grounded in the LiteLLM docs research).
_PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec("GEMINI_API_KEY", "gemini", "gemini/", "gemini/gemini-2.5-pro"),
    "openai": ProviderSpec("OPENAI_API_KEY", "openai", "openai/", "openai/gpt-4o-mini"),
    "anthropic": ProviderSpec(
        "ANTHROPIC_API_KEY", "anthropic", "anthropic/", "anthropic/claude-3-5-haiku-20241022"
    ),
    # opencode-go / zen: OpenAI-compatible gateway → openai/ prefix + an api_base ending in /v1.
    "zen": ProviderSpec("OPENAI_API_KEY", "openai", "openai/", None, needs_api_base=True),
}


def provider_env_var(provider: str) -> str | None:
    """The env var LiteLLM reads for ``provider`` (key-input label), or ``None`` if unknown."""
    spec = _PROVIDERS.get(provider)
    return spec.env if spec else None


def known_providers() -> tuple[str, ...]:
    """Provider ids the judge tab can offer an API-key input for."""
    return tuple(_PROVIDERS)


def validate_provider_key(
    provider: str, key: str, *, model: str | None = None, api_base: str | None = None
) -> tuple[bool | None, str]:
    """Validate a provider key. ``(True, msg)`` valid · ``(False, msg)`` rejected · ``(None, msg)``
    could-not-validate (LiteLLM absent). Cheap: free model-list endpoint first, then a minimal call.
    Never logs the key. Caller MUST run this in a worker (it makes a network call).
    """
    spec = _PROVIDERS.get(provider)
    if spec is None:
        return (False, f"unknown provider '{provider}'")
    if not key.strip():
        return (False, "empty key")
    try:
        import litellm
    except ImportError:
        return (None, "saved — install the `llm` extra (`uv sync --extra llm`) to validate")
    # Primary: the free /models endpoint (lists models, no completion cost).
    try:
        models = litellm.get_valid_models(
            check_provider_endpoint=True,
            custom_llm_provider=spec.llm_provider,
            api_key=key,
            api_base=api_base,
        )
        if models:
            return (True, f"valid — {len(models)} models available")
    except Exception:
        pass
    # Fallback: a minimal completion (max_tokens small) — costs ~nothing but proves the key.
    full = model or spec.default_model
    if full and "/" not in full:
        full = spec.prefix + full
    if not full:
        return (None, "saved — provide a model to validate this gateway key")
    try:
        if litellm.check_valid_key(model=full, api_key=key):
            return (True, "valid (verified via a minimal call)")
        return (False, "key rejected by the provider")
    except Exception as exc:
        return (False, f"could not validate: {type(exc).__name__}")


def save_provider_key(
    provider: str, key: str, *, model: str | None = None, api_base: str | None = None
) -> tuple[bool, str]:
    """Validate then persist a provider key to ``~/.config/siftmesh/.env`` (600) + ``os.environ``.

    A rejected key is NOT persisted. An unvalidatable key (LiteLLM absent) IS persisted with an
    honest message. Returns ``(saved, message)``. Run in a worker (validation is a network call).
    """
    spec = _PROVIDERS.get(provider)
    if spec is None:
        return (False, f"unknown provider '{provider}'")
    key = key.strip()
    if not key:
        return (False, "empty key")
    valid, msg = validate_provider_key(provider, key, model=model, api_base=api_base)
    if valid is False:
        return (False, msg)  # don't persist a rejected key
    from siftmesh_core.secrets_env import save_secret

    save_secret(spec.env, key)
    os.environ[spec.env] = key
    return (True, msg)

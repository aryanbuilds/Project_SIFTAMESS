"""Executor adapters (Epic F).

Importing this package registers every concrete adapter in the registry so
``get_adapter(profile_id)`` can resolve them (and fall closed to the deterministic
floor when a live adapter's CLI/key is absent).
"""

from __future__ import annotations

from siftmesh_core.adapters import claude_adapter as _claude  # noqa: F401

# Import concretes for their @register side effects (order: floor first).
from siftmesh_core.adapters import deterministic_executor as _deterministic  # noqa: F401
from siftmesh_core.adapters import generic_shell_adapter as _generic_shell  # noqa: F401
from siftmesh_core.adapters import opencode_adapter as _opencode  # noqa: F401
from siftmesh_core.adapters.base import (
    DEFAULT_PROFILE,
    AdapterContext,
    ExecutorAdapter,
    ResultRef,
    get_adapter,
    register,
    resolve_profile,
)

__all__ = [
    "DEFAULT_PROFILE",
    "AdapterContext",
    "ExecutorAdapter",
    "ResultRef",
    "get_adapter",
    "register",
    "resolve_profile",
]

"""Typed forensic tools (D4-D9).

Each tool is a thin, typed service function that runs its real backend through
:func:`siftmesh_core.mcp_gateway.audit_exec.run_tool` and returns a ``ToolResult``
subclass. Import from submodules directly.
"""

from __future__ import annotations

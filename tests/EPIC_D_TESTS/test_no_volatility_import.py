"""License guard: Volatility 3 (VSL) must NEVER be imported into this Apache-2.0 project.

It is invoked only as an external fixed-argv subprocess. This walks the whole package and
fails if any module contains an ``import volatility``/``from volatility ...`` statement.
"""

from __future__ import annotations

import re
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent.parent / "siftmesh_core"
_IMPORT = re.compile(r"^\s*(?:import|from)\s+volatility", re.MULTILINE)


def test_no_volatility_import_anywhere() -> None:
    offenders: list[str] = []
    for py in _PKG.rglob("*.py"):
        if _IMPORT.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py.relative_to(_PKG)))
    assert not offenders, f"Volatility3 (VSL) imported — must be subprocess-only: {offenders}"

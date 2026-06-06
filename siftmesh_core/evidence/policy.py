"""Evidence-handling policy doc generator (B6).

Renders ``context/evidence_policy.md`` from an in-package Jinja2 template so each
run carries an auditable statement of read-only posture, the large-data
strategy, hashing standard, prompt-injection stance, and the standards SIFTMesh
aligns to (ISO 27037 / SWGDE / NIST SP 800-86). Stated non-goal: not
court-admissible. The template loads via ``PackageLoader`` so editable installs
(``uv run``) work; wheel data-file inclusion is an Epic-M packaging concern.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from siftmesh_core import __version__
from siftmesh_core.evidence.path_policy import safe_write_path

_env = Environment(
    loader=PackageLoader("siftmesh_core.reports", "templates"),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


def render_evidence_policy(
    *,
    case_id: str,
    run_id: str,
    evidence_root: str,
    file_count: int,
) -> str:
    """Render the evidence-policy markdown for a case (no I/O)."""
    template = _env.get_template("evidence_policy.md.j2")
    return template.render(
        case_id=case_id,
        run_id=run_id,
        evidence_root=evidence_root,
        file_count=file_count,
        tool_version=__version__,
    )


def write_evidence_policy(
    run_root: Path | str,
    *,
    case_id: str,
    run_id: str,
    evidence_root: Path | str,
    file_count: int,
) -> Path:
    """Render + write ``context/evidence_policy.md`` via the path policy."""
    text = render_evidence_policy(
        case_id=case_id,
        run_id=run_id,
        evidence_root=str(evidence_root),
        file_count=file_count,
    )
    target = safe_write_path(
        run_root, Path("context") / "evidence_policy.md", evidence_root=evidence_root
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target

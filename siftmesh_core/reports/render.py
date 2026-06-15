"""Determinism harness (J2) - pinned Jinja2 env + header/body split + shared write helpers.

Reports are **byte-deterministic functions of the ledgers**: the report *body* must be identical
across two renders of the same run-dir (the golden-tested "replayable audit"). Two mechanisms:

* **A pinned Jinja2 env** (``\n`` newlines, trimmed blocks, ``StrictUndefined``, HTML-only
  autoescape, Decimal-quantized float filter). No ``now()`` global, so a generation timestamp cannot
  leak into a body.
* **A header/body split via a sentinel line** (``REPORT_HEADER_SENTINEL``). ``compose_report(...)``
  = a small non-deterministic header (generated-utc, host, version, run_dir, load-errors) + the
  sentinel + the deterministic body. ``split_body()`` returns everything after the sentinel, so
  golden tests + the demo golden (K6) diff only the body, never the header.
"""

from __future__ import annotations

import platform
import socket
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from siftmesh_core.evidence.path_policy import safe_write_path
from siftmesh_core.run_dir import RunPaths

REPORT_HEADER_SENTINEL = "<!-- SIFTMESH-REPORT-BODY-BELOW -->"


def fmt_float(value: float | int | None) -> str:
    """Fixed 3-dp string, Decimal-quantized so it is byte-stable (no float repr drift)."""
    if value is None:
        return "n/a"
    return str(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN))


def fmt_pct(value: float | int | None) -> str:
    """A 0..1 ratio as a 1-dp percent (e.g. 0.917 -> '91.7%'); byte-stable."""
    if value is None:
        return "n/a"
    pct = Decimal(str(value)) * Decimal(100)
    return f"{pct.quantize(Decimal('0.1'), rounding=ROUND_HALF_EVEN)}%"


def make_report_env() -> Environment:
    """The single pinned Jinja2 environment for every report template (deterministic by config)."""
    env = Environment(
        loader=PackageLoader("siftmesh_core.reports", "templates"),
        autoescape=select_autoescape(["html", "htm", "xml"]),  # markdown is NOT escaped; HTML is
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        newline_sequence="\n",
        undefined=StrictUndefined,  # a missing var fails loudly, never renders ''
        auto_reload=False,
    )
    env.filters["fmt_float"] = fmt_float
    env.filters["fmt_pct"] = fmt_pct
    # NB: deliberately NO now()/today() global - a timestamp must never reach a body.
    return env


def render_body_only(
    template_name: str, body_ctx: dict[str, object], env: Environment | None = None
) -> str:
    """Render a template's body (no header). Used directly by golden byte-stability tests."""
    env = env or make_report_env()
    return env.get_template(template_name).render(**body_ctx)


def now_utc_iso() -> str:
    """Generation timestamp for the EXCLUDED header only (never used in a body)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_header_lines(
    *, run_id: str, run_root: Path, load_errors: tuple[str, ...] = (), strict: bool = True
) -> list[str]:
    """The non-deterministic header (excluded from golden diffs) as HTML/markdown comments."""
    lines = [
        f"<!-- generated_utc: {now_utc_iso()} -->",
        f"<!-- host: {socket.gethostname()} -->",
        f"<!-- python: {platform.python_version()} -->",
        f"<!-- run_id: {run_id} -->",
        f"<!-- run_dir: {run_root} -->",
        f"<!-- load_mode: {'strict' if strict else 'tolerant'} -->",
    ]
    lines += [f"<!-- load_error: {e} -->" for e in load_errors]
    return lines


def compose_report(
    *,
    run_id: str,
    run_root: Path,
    body: str,
    load_errors: tuple[str, ...] = (),
    strict: bool = True,
) -> str:
    """Header block + sentinel + deterministic body → the full report text written to disk."""
    header = "\n".join(
        build_header_lines(run_id=run_id, run_root=run_root, load_errors=load_errors, strict=strict)
    )
    body = body if body.endswith("\n") else body + "\n"
    return f"{header}\n{REPORT_HEADER_SENTINEL}\n{body}"


def split_body(text: str) -> str:
    """Return everything after the sentinel line (the deterministic body); '' if no sentinel."""
    marker = f"{REPORT_HEADER_SENTINEL}\n"
    idx = text.find(marker)
    return text[idx + len(marker) :] if idx >= 0 else text


def write_report(
    run: RunPaths, filename: str, text: str, *, evidence_root: Path | str | None = None
) -> Path:
    """Write a composed report under ``reports/`` via the path policy (run-dir only)."""
    target = safe_write_path(run.root, Path("reports") / filename, evidence_root=evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if "\r" in text:  # determinism guard: bodies are '\n'-only
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    target.write_text(text, encoding="utf-8")
    return target


class MarkdownBuilder:
    """Tiny deterministic markdown line-builder for the code-built reports (J4/J5/J6).

    Avoids threading computed numbers through Jinja (a determinism surface) while sharing the
    ``fmt_float`` formatting. Produces ``\\n``-joined text with a single trailing newline.
    """

    def __init__(self) -> None:
        self._lines: list[str] = []

    def h1(self, text: str) -> MarkdownBuilder:
        return self.line(f"# {text}").blank()

    def h2(self, text: str) -> MarkdownBuilder:
        return self.blank().line(f"## {text}").blank()

    def line(self, text: str = "") -> MarkdownBuilder:
        self._lines.append(text)
        return self

    def blank(self) -> MarkdownBuilder:
        if self._lines and self._lines[-1] != "":
            self._lines.append("")
        return self

    def bullet(self, text: str) -> MarkdownBuilder:
        return self.line(f"- {text}")

    def table(self, headers: list[str], rows: list[list[str]]) -> MarkdownBuilder:
        self.line("| " + " | ".join(headers) + " |")
        self.line("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            self.line("| " + " | ".join(row) + " |")
        return self

    def build(self) -> str:
        text = "\n".join(self._lines).rstrip("\n")
        return text + "\n"

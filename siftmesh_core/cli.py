"""SIFTMesh CLI entry point (Typer 0.26.x).

`app` is the console-script target referenced by `[project.scripts]`:
    siftmesh = "siftmesh_core.cli:app"
Typer instances are directly callable, so no `main()` wrapper is required.

These commands are Epic-A stubs that establish the CLI surface (CLI = source of
truth). Real behaviour is wired in later epics.
"""

from __future__ import annotations

from typing import Annotated

import typer

from siftmesh_core import __version__
from siftmesh_core.doctor import run_doctor
from siftmesh_core.protocol_sift import PROTOCOL_SIFT_SKILLS, detect_protocol_sift

# Root app: no args -> show help (Click "no command" exits with code 2).
app = typer.Typer(
    no_args_is_help=True,
    help="SIFTMesh: CLI-first, evidence-safe DFIR investigation controller.",
)

# Debug sub-typers (command groups).
tasks_app = typer.Typer(no_args_is_help=True, help="Task inspection commands.")
claims_app = typer.Typer(no_args_is_help=True, help="Claim ledger inspection commands.")
audit_app = typer.Typer(no_args_is_help=True, help="Audit log inspection commands.")
app.add_typer(tasks_app, name="tasks")
app.add_typer(claims_app, name="claims")
app.add_typer(audit_app, name="audit")

# Protocol SIFT inspection (env-only). Protocol SIFT is a ~/.claude config/skill
# layer, NOT an MCP server (PLAN/09) — SIFTMesh inspects and governs it.
protocol_sift_app = typer.Typer(
    no_args_is_help=True, help="Inspect & govern the Protocol SIFT (~/.claude) layer."
)
skills_app = typer.Typer(no_args_is_help=True, help="Protocol SIFT skill inspection.")
protocol_sift_app.add_typer(skills_app, name="skills")
app.add_typer(protocol_sift_app, name="protocol-sift")


def _version_callback(value: bool) -> None:
    # Eager: fires during arg parsing, before subcommand dispatch and before the
    # callback body. typer.Exit() defaults to code 0.
    if value:
        print(f"siftmesh {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """App-level options. `siftmesh --version` works with no subcommand."""


@app.command("init-case")
def init_case(
    case_dir: str,
    evidence: Annotated[str, typer.Option(help="Path to read-only evidence.")],
) -> None:
    """Initialize a case directory and read-only evidence vault."""
    print(f"init-case {case_dir} --evidence {evidence}")


@app.command()
def plan(run_dir: str) -> None:
    """Generate the investigation plan for a run."""
    print(f"plan {run_dir}")


@app.command()
def dispatch(run_dir: str) -> None:
    """Dispatch tasks to agents."""
    print(f"dispatch {run_dir}")


@app.command()
def collect(run_dir: str) -> None:
    """Collect agent/tool results into the run."""
    print(f"collect {run_dir}")


@app.command()
def critique(run_dir: str) -> None:
    """Run the critic over collected claims."""
    print(f"critique {run_dir}")


@app.command()
def report(run_dir: str) -> None:
    """Render the final evidence-backed report."""
    print(f"report {run_dir}")


@app.command()
def replay(run_dir: str) -> None:
    """Replay the audit trail for a run."""
    print(f"replay {run_dir}")


@app.command()
def run(
    case_dir: str,
    evidence: Annotated[str, typer.Option(help="Path to read-only evidence.")],
    mode: Annotated[
        str, typer.Option(help="manual | review-only | auto-human-loop | auto")
    ] = "manual",
) -> None:
    """High-level orchestration from init through report."""
    print(f"run {case_dir} --evidence {evidence} --mode {mode}")


@app.command()
def resume(run_id: str) -> None:
    """Resume an interrupted run."""
    print(f"resume {run_id}")


@app.command()
def status(run_id: str) -> None:
    """Show status for a run."""
    print(f"status {run_id}")


@app.command()
def doctor(
    protocol_sift: Annotated[
        bool,
        typer.Option("--protocol-sift", help="Also detect the ~/.claude Protocol SIFT layer."),
    ] = False,
) -> None:
    """Verify host + tool backends (fails closed on missing deps)."""
    raise typer.Exit(code=run_doctor(protocol_sift=protocol_sift))


@app.command()
def retry(task_id: str) -> None:
    """Retry a task -> `siftmesh retry TASK-003`."""
    print(f"retry {task_id}")


@app.command()
def approve(
    run_id: str,
    gate: Annotated[str, typer.Option(help="plan | dispatch | retry | report")],
) -> None:
    """Approve a blocked gate -> `siftmesh approve RUN-001 --gate plan`."""
    print(f"approve {run_id} --gate {gate}")


@app.command()
def reject(
    run_id: str,
    gate: Annotated[str, typer.Option(help="plan | dispatch | retry | report")],
) -> None:
    """Reject a blocked gate -> `siftmesh reject RUN-001 --gate retry`."""
    print(f"reject {run_id} --gate {gate}")


@tasks_app.command("list")
def tasks_list(run_id: str) -> None:
    """List tasks for a run -> `siftmesh tasks list RUN-001`."""
    print(f"tasks list {run_id}")


@tasks_app.command("show")
def tasks_show(run_id: str, task_id: str) -> None:
    """Show a task -> `siftmesh tasks show RUN-001 TASK-001`."""
    print(f"tasks show {run_id} {task_id}")


@claims_app.command("list")
def claims_list(run_id: str) -> None:
    """List claims for a run -> `siftmesh claims list RUN-001`."""
    print(f"claims list {run_id}")


@claims_app.command("show")
def claims_show(claim_id: str) -> None:
    """Show a single claim -> `siftmesh claims show CLAIM-003`."""
    print(f"claims show {claim_id}")


@audit_app.command("tail")
def audit_tail(run_id: str) -> None:
    """Tail the audit log for a run -> `siftmesh audit tail RUN-001`."""
    print(f"audit tail {run_id}")


@protocol_sift_app.command("inspect")
def protocol_sift_inspect() -> None:
    """Inspect the ~/.claude Protocol SIFT layer (env-only; PLAN/09)."""
    status = detect_protocol_sift()
    typer.echo(f"Protocol SIFT installed : {status.protocol_sift_installed}")
    typer.echo(f"Claude Code installed   : {status.claude_code_installed}")
    typer.echo(f"settings.json present   : {status.settings_present}")
    typer.echo(f"case template present   : {status.case_template_present}")
    typer.echo(f"skills present          : {', '.join(status.skills_present) or 'none'}")
    typer.echo(f"SIFT tools present      : {', '.join(status.tools_present) or 'none'}")


@skills_app.command("list")
def protocol_sift_skills_list() -> None:
    """List Protocol SIFT skills and whether each is present."""
    status = detect_protocol_sift()
    for skill in PROTOCOL_SIFT_SKILLS:
        mark = "x" if skill in status.skills_present else " "
        typer.echo(f"  [{mark}] {skill}")


if __name__ == "__main__":
    app()

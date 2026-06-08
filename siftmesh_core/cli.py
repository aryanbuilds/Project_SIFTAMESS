"""SIFTMesh CLI entry point (Typer 0.26.x).

`app` is the console-script target referenced by `[project.scripts]`:
    siftmesh = "siftmesh_core.cli:app"
Typer instances are directly callable, so no `main()` wrapper is required.

`init-case` is real Epic B evidence-vault behavior. The remaining investigation
commands keep the frozen CLI surface until their epics wire the real workflows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from siftmesh_core import __version__
from siftmesh_core.doctor import run_doctor
from siftmesh_core.evidence.path_policy import PathPolicyViolation
from siftmesh_core.evidence.vault import EvidenceModifiedError
from siftmesh_core.evidence.vault import init_case as vault_init_case
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
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
    run_name: Annotated[str | None, typer.Option(help="Override the generated RUN-* id.")] = None,
    verify_after: Annotated[
        bool,
        typer.Option(
            "--verify-after",
            help="Re-hash originals at end of run (off by default; costly for huge data).",
        ),
    ] = False,
) -> None:
    """Hash + seal evidence into a new run dir (manifest, custody, policy)."""
    try:
        run = vault_init_case(
            case_dir, evidence, run_name=run_name, verify_after=verify_after, show_progress=True
        )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        EvidenceModifiedError,
    ) as exc:
        typer.echo(f"init-case failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"init-case complete: {run.root}")
    typer.echo(f"  run id   : {run.run_id}")
    typer.echo(f"  manifest : {run.evidence_manifest}")
    typer.echo(f"  custody  : {run.custody_log}")


@app.command()
def plan(
    run_dir: str,
    review_only: Annotated[
        bool,
        typer.Option("--review-only", help="Emit recommendations only; no dispatch."),
    ] = False,
) -> None:
    """Generate the deterministic investigation plan + task contracts for a run."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.orchestrator.planner import generate_plan
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        if not run.evidence_manifest.is_file():
            raise FileNotFoundError(f"no evidence manifest at {run.evidence_manifest}")
        result = generate_plan(run, settings=load_settings(), review_only=review_only)
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
    ) as exc:
        typer.echo(f"plan failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"plan complete: {result.run.root}")
    typer.echo(f"  context files : {len(result.context_files)}")
    typer.echo(f"  task contracts: {len(result.task_files)}")
    typer.echo(f"  plan          : {result.run.investigation_plan}")
    if result.review_only:
        typer.echo("  mode          : review-only (recommendations only, no dispatch)")
    elif not result.task_files:
        typer.echo("  note          : nothing to plan (manifest has no actionable artifacts)")


@app.command()
def dispatch(
    run_dir: str,
    task: Annotated[str | None, typer.Option(help="Dispatch only this TASK-ID.")] = None,
    agent_profile: Annotated[
        str | None, typer.Option("--agent-profile", help="Override the contract's agent profile.")
    ] = None,
    evidence: Annotated[
        str | None, typer.Option(help="Evidence root (else recovered from readonly_mounts.json).")
    ] = None,
) -> None:
    """Execute the run's task contracts via their adapters; write results + audit."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
    from siftmesh_core.orchestrator.scheduler import CapError, PolicyError, dispatch_run
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        refs = dispatch_run(
            run,
            settings=load_settings(),
            evidence_override=evidence,
            task_id=task,
            agent_profile=agent_profile,
        )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
        BackendUnavailableError,
        PolicyError,
        CapError,
    ) as exc:
        typer.echo(f"dispatch failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"dispatch complete: {len(refs)} task(s)")
    for ref in refs:
        typer.echo(f"  {ref.task_id}: {ref.status} -> {ref.result_path}")


@app.command()
def collect(
    run_dir: str,
    task: Annotated[str | None, typer.Option(help="Collect only this TASK-ID.")] = None,
) -> None:
    """Validate task result envelopes; report missing/malformed without crashing."""
    from pydantic import ValidationError

    from siftmesh_core.orchestrator.scheduler import collect_run
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        report = collect_run(RunPaths(root=root), task_id=task)
    except (FileNotFoundError, NotADirectoryError, PathPolicyViolation, ValidationError) as exc:
        typer.echo(f"collect failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for row in report.rows:
        typer.echo(f"  {row.task_id}: {row.status} ({len(row.claim_ids)} claim(s))")
    if report.missing:
        typer.echo(f"  missing: {', '.join(report.missing)}", err=True)
    if report.malformed:
        typer.echo(f"  malformed: {', '.join(report.malformed)}", err=True)


@app.command()
def critique(
    run_dir: str,
    evidence: Annotated[
        str | None, typer.Option(help="Evidence root (else recovered from readonly_mounts.json).")
    ] = None,
    followups: Annotated[
        bool,
        typer.Option(
            "--followups/--no-followups",
            help="Generate follow-up tasks for unexamined manifest artifacts (G9).",
        ),
    ] = True,
) -> None:
    """Validate collected claims; emit one critic verdict per task; write ledgers."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.ledgers.followups import read_followups
    from siftmesh_core.ledgers.jsonl_ledger import LedgerCorruptionError
    from siftmesh_core.orchestrator.critic import critique_run
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        verdicts = critique_run(
            run, settings=load_settings(), evidence_root=evidence, generate_followups=followups
        )
        followup_count = len(read_followups(run.root))
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
        LedgerCorruptionError,
    ) as exc:
        typer.echo(f"critique failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"critique complete: {len(verdicts)} verdict(s)")
    for v in verdicts:
        typer.echo(f"  {v.task_id}: {v.verdict} ({len(v.affected_claim_ids)} claim(s))")
    if followup_count:
        typer.echo(f"  follow-ups : {followup_count} gap(s) raised (audit/followups.jsonl)")


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


@app.command("mcp-serve")
def mcp_serve() -> None:
    """Launch the typed forensic MCP gateway over stdio (the 10 allowlisted tools)."""
    from siftmesh_core.mcp_gateway.server import run_server

    run_server()


@app.command("extract-artifacts")
def extract_artifacts(
    run_dir: str,
    evidence: Annotated[str, typer.Option(help="Evidence root (the originals dir).")],
    image: Annotated[
        str, typer.Option(help="Disk image artifact, evidence-relative (e.g. rocba-cdrive.e01).")
    ],
    keys: Annotated[
        list[str] | None,
        typer.Option(help="Artifact keys to extract (repeatable); default = all curated."),
    ] = None,
) -> None:
    """Extract Windows artifacts from a disk image into the run dir (Sleuthkit; audited)."""
    from siftmesh_core.mcp_gateway.tools.image_tools import extract_artifacts_from_image

    try:
        result = extract_artifacts_from_image(
            run_dir, image_artifact=image, evidence_root=evidence, keys=keys
        )
    except (FileNotFoundError, ValueError, PathPolicyViolation, BackendUnavailableError) as exc:
        typer.echo(f"extract-artifacts failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"extract-artifacts: status={result.status} extracted={result.extracted_count} "
        f"failed={result.failed_count} (tool_call {result.tool_call_id}, "
        f"offset {result.partition_offset})"
    )


@app.command("analyze-memory")
def analyze_memory_cmd(
    run_dir: str,
    evidence: Annotated[str, typer.Option(help="Root dir containing the memory image.")],
    memory: Annotated[str, typer.Option(help="Memory image, relative to --evidence.")],
    plugins: Annotated[
        list[str] | None, typer.Option(help="vol plugins (repeatable); default = triage set.")
    ] = None,
    symbol_dirs: Annotated[
        str | None, typer.Option(help="Writable Volatility 3 symbol cache dir.")
    ] = None,
) -> None:
    """Triage a memory image with Volatility 3 (subprocess; audited)."""
    from siftmesh_core.mcp_gateway.tools.memory_tools import analyze_memory

    try:
        result = analyze_memory(
            run_dir,
            memory_artifact=memory,
            evidence_root=evidence,
            plugins=plugins,
            symbol_dirs=symbol_dirs,
        )
    except (FileNotFoundError, ValueError, PathPolicyViolation, BackendUnavailableError) as exc:
        typer.echo(f"analyze-memory failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"analyze-memory: status={result.status} procs={result.process_count} "
        f"suspicious={len(result.suspicious)} (tool_call {result.tool_call_id})"
    )


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
def retry(run_dir: str, task_id: str) -> None:
    """Re-critique one task; if DECIDE says retry, tighten its contract + re-dispatch."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.orchestrator.critic import critique_run, write_retry
    from siftmesh_core.orchestrator.decide import decide
    from siftmesh_core.orchestrator.scheduler import dispatch_run
    from siftmesh_core.run_dir import RunPaths
    from siftmesh_core.schemas.task import TaskContract
    from siftmesh_core.schemas.task_result import TaskResult
    from siftmesh_core.schemas.yaml_io import read_yaml_model

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        settings = load_settings()
        result_path = run.result_path(task_id)
        if not result_path.is_file():
            raise FileNotFoundError(f"no result for {task_id} at {result_path}")
        result = TaskResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        contract = read_yaml_model(TaskContract, run.tasks / f"{task_id}.yaml")
        verdicts = {
            v.task_id: v for v in critique_run(run, settings=settings, generate_followups=False)
        }
        verdict = verdicts.get(task_id)
        if verdict is None:
            raise FileNotFoundError(f"no critic verdict for {task_id}")
        decision = decide(
            verdict.verdict,
            attempt=result.attempt,
            max_attempts=contract.retry_policy.max_attempts,
            max_iterations=settings.caps.max_iterations,
        )
        if decision.action != "retry":
            typer.echo(f"retry refused for {task_id}: decide={decision.action} — {decision.reason}")
            raise typer.Exit(code=1)
        write_retry(run, contract, from_attempt=result.attempt, cause=verdict.verdict)
        refs = dispatch_run(
            run,
            settings=settings,
            task_id=task_id,
            attempt=result.attempt + 1,
            critic_feedback=tuple(verdict.reasons),
        )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
    ) as exc:
        typer.echo(f"retry failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"retry complete: {task_id} attempt {result.attempt + 1} -> {refs[0].status}")


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
def protocol_sift_inspect(
    run_dir: Annotated[
        str | None,
        typer.Option(
            "--run-dir", help="Also write the validated capability map under this run dir."
        ),
    ] = None,
) -> None:
    """Inspect the ~/.claude Protocol SIFT layer (env-only; PLAN/09).

    With ``--run-dir``, also write ``context/protocol_sift_capabilities.json`` (D11).
    """
    status = detect_protocol_sift()
    typer.echo(f"Protocol SIFT installed : {status.protocol_sift_installed}")
    typer.echo(f"Claude Code installed   : {status.claude_code_installed}")
    typer.echo(f"settings.json present   : {status.settings_present}")
    typer.echo(f"case template present   : {status.case_template_present}")
    typer.echo(f"skills present          : {', '.join(status.skills_present) or 'none'}")
    typer.echo(f"SIFT tools present      : {', '.join(status.tools_present) or 'none'}")
    typer.echo(f"SIFT tools absent       : {', '.join(status.tools_absent) or 'none'}")
    if run_dir is not None:
        from siftmesh_core.protocol_sift import write_protocol_sift_capability_map

        try:
            path = write_protocol_sift_capability_map(run_dir)
        except (FileNotFoundError, PathPolicyViolation) as exc:
            typer.echo(f"capability map write failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"capability map written  : {path}")


@skills_app.command("list")
def protocol_sift_skills_list() -> None:
    """List Protocol SIFT skills and whether each is present."""
    status = detect_protocol_sift()
    for skill in PROTOCOL_SIFT_SKILLS:
        mark = "x" if skill in status.skills_present else " "
        typer.echo(f"  [{mark}] {skill}")


if __name__ == "__main__":
    app()

"""SIFTMesh CLI entry point (Typer 0.26.x).

`app` is the console-script target referenced by `[project.scripts]`:
    siftmesh = "siftmesh_core.cli:app"
Typer instances are directly callable, so no `main()` wrapper is required.

`init-case` is real Epic B evidence-vault behavior. The remaining investigation
commands keep the frozen CLI surface until their epics wire the real workflows.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer

from siftmesh_core import __version__
from siftmesh_core.doctor import run_doctor
from siftmesh_core.evidence.path_policy import PathPolicyViolation
from siftmesh_core.evidence.vault import EvidenceModifiedError
from siftmesh_core.evidence.vault import init_case as vault_init_case
from siftmesh_core.mcp_gateway.backends import BackendUnavailableError
from siftmesh_core.protocol_sift import PROTOCOL_SIFT_SKILLS, detect_protocol_sift

if TYPE_CHECKING:
    from siftmesh_core.run_dir import RunPaths
    from siftmesh_core.schemas.run import GateStatus, RunMode, RunState

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
def report(
    run_dir: str,
    tolerant: Annotated[
        bool, typer.Option("--tolerant", help="Tolerate a truncated trailing ledger line.")
    ] = False,
    expected: Annotated[
        str | None, typer.Option("--expected", help="expected_findings.md → accuracy diff mode.")
    ] = None,
) -> None:
    """Render the deterministic evidence-backed reports + replay.html for a run."""
    from pathlib import Path

    from pydantic import ValidationError

    from siftmesh_core.evidence.path_policy import PathPolicyViolation
    from siftmesh_core.ledgers.jsonl_ledger import LedgerCorruptionError
    from siftmesh_core.reports import ReportLoadError, generate_all_reports
    from siftmesh_core.run_dir import RunPaths

    root = Path(run_dir)
    if not root.is_dir():
        typer.echo(f"report failed: not a run directory: {run_dir}", err=True)
        raise typer.Exit(code=1)
    try:
        run = RunPaths(root=root)
        paths = generate_all_reports(run, strict=not tolerant, expected_findings=expected)
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
        LedgerCorruptionError,
        ReportLoadError,
    ) as exc:
        typer.echo(f"report failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"report: {len(paths)} artifact(s) written")
    for p in paths:
        typer.echo(f"  {p}")


@app.command()
def replay(
    run_dir: str,
    html: Annotated[bool, typer.Option("--html", help="Also write reports/replay.html.")] = False,
    tolerant: Annotated[
        bool, typer.Option("--tolerant", help="Tolerate a truncated trailing ledger line.")
    ] = False,
) -> None:
    """Replay the audit trail (chronological events) as a deterministic text timeline."""
    from pathlib import Path

    from pydantic import ValidationError

    from siftmesh_core.evidence.path_policy import PathPolicyViolation
    from siftmesh_core.ledgers.jsonl_ledger import LedgerCorruptionError
    from siftmesh_core.reports import (
        ReportLoadError,
        generate_replay_html,
        load_report_view,
        render_text_replay,
    )
    from siftmesh_core.run_dir import RunPaths

    root = Path(run_dir)
    if not root.is_dir():
        typer.echo(f"replay failed: not a run directory: {run_dir}", err=True)
        raise typer.Exit(code=1)
    run = RunPaths(root=root)
    try:
        view = load_report_view(run, strict=not tolerant)
        typer.echo(render_text_replay(view), nl=False)
        if html:
            path = generate_replay_html(run, view=view)
            typer.echo(f"replay.html: {path}")
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        ValidationError,
        LedgerCorruptionError,
        ReportLoadError,
    ) as exc:
        typer.echo(f"replay failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


_RUN_MODES = ("manual", "review_only", "auto_human_loop", "auto")


def _resolve_mode(
    mode: str, *, review_only: bool, auto_human_loop: bool, auto: bool
) -> RunMode | None:
    """Resolve the engine mode from the CLAUDE §4 flags (flags win over --mode)."""
    if auto:
        return "auto"
    if auto_human_loop:
        return "auto_human_loop"
    if review_only:
        return "review_only"
    norm = mode.replace("-", "_")
    return cast("RunMode", norm) if norm in _RUN_MODES else None


_AGENT_ALIASES = {
    "claude": "claude_headless",
    "opencode": "opencode_headless",
    "deterministic": "deterministic_executor",
    "floor": "deterministic_executor",
}


def _agent_overrides(agent: str | None) -> dict[str, object]:
    """Translate a friendly --agent choice into settings overrides (opt into the live chain).

    ``claude``/``opencode`` put that agent first in the preference chain (the other stays a
    fallback, floor last) and flip executor_selection to ``auto``. ``deterministic`` pins the floor.
    """
    if not agent:
        return {}
    profile = _AGENT_ALIASES.get(agent, agent)  # passthrough if already a full profile_id
    if profile == "deterministic_executor":
        return {"executor_selection": "deterministic"}
    others = [p for p in ("claude_headless", "opencode_headless") if p != profile]
    return {
        "executor_selection": "auto",
        "agent_preference": [profile, *others, "deterministic_executor"],
    }


def _echo_run_state(run_paths: RunPaths, state: RunState) -> None:
    typer.echo(f"run: {run_paths.root}")
    typer.echo(f"  run id : {run_paths.run_id}")
    typer.echo(
        f"  state  : {state.state} "
        f"(mode={state.mode}, iteration={state.iteration}/{state.max_iterations})"
    )
    if state.state == "done":
        typer.echo("  status : complete")
        typer.echo("  report : reports/ written (auto modes) — or run `siftmesh report <run>`")
    elif state.terminal:
        typer.echo(f"  status : halted ({state.blocked_gate or 'rejected'})")
    elif state.blocked_gate:
        typer.echo(
            f"  gate   : awaiting approval -> "
            f"siftmesh approve {run_paths.root} --gate {state.blocked_gate}"
        )
    else:
        typer.echo(f"  status : paused -> siftmesh resume {run_paths.root}")


@app.command()
def run(
    case_dir: str,
    evidence: Annotated[str, typer.Option(help="Path to read-only evidence.")],
    mode: Annotated[
        str, typer.Option(help="manual | review-only | auto-human-loop | auto")
    ] = "manual",
    review_only: Annotated[
        bool, typer.Option("--review-only", help="Plan + recommendations only; no dispatch.")
    ] = False,
    auto_human_loop: Annotated[
        bool, typer.Option("--auto-human-loop", help="Run until a meaningful approval gate.")
    ] = False,
    auto: Annotated[
        bool, typer.Option("--auto", help="Run to completion; enforce caps; no gates.")
    ] = False,
    max_iterations: Annotated[
        int | None, typer.Option("--max-iterations", help="Override the self-correction cap.")
    ] = None,
    max_agent_tasks: Annotated[
        int | None,
        typer.Option(
            "--max-agent-tasks",
            help="Raise the dispatchable-task cap (real disk images yield 200+ derived tasks).",
        ),
    ] = None,
    agent: Annotated[
        str | None,
        typer.Option("--agent", help="Opt into a live agent: claude | opencode | deterministic."),
    ] = None,
) -> None:
    """Init → plan → dispatch → collect → critique → decide → report, via one engine."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.orchestrator.run_state_store import write_run_state
    from siftmesh_core.orchestrator.scheduler import CapError, PolicyError
    from siftmesh_core.orchestrator.state_machine import IllegalTransitionError
    from siftmesh_core.orchestrator.workflow_runner import run_engine
    from siftmesh_core.schemas.run import RunState

    resolved = _resolve_mode(
        mode, review_only=review_only, auto_human_loop=auto_human_loop, auto=auto
    )
    if resolved is None:
        typer.echo(f"run failed: unknown mode {mode!r} (use {', '.join(_RUN_MODES)})", err=True)
        raise typer.Exit(code=1)
    settings = load_settings(**_agent_overrides(agent))
    if max_agent_tasks is not None:
        # Caps stay enforced (CLAUDE §11) — the operator just sets the ceiling explicitly.
        settings = settings.model_copy(
            update={"caps": settings.caps.model_copy(update={"max_agent_tasks": max_agent_tasks})}
        )
    try:
        run_paths = vault_init_case(case_dir, evidence, show_progress=True)
        state = RunState(
            run_id=run_paths.run_id,
            mode=resolved,
            max_iterations=max_iterations or settings.caps.max_iterations,
        )
        write_run_state(run_paths, state)
        state = run_engine(
            run_paths,
            settings=settings,
            evidence_root=evidence,
            single_step=(resolved == "manual"),
        )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        EvidenceModifiedError,
        BackendUnavailableError,
        ValidationError,
        PolicyError,
        CapError,
        IllegalTransitionError,
    ) as exc:
        typer.echo(f"run failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _echo_run_state(run_paths, state)


@app.command()
def resume(run_dir: str) -> None:
    """Resume an interrupted run from its persisted RunState."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.orchestrator.run_state_store import read_run_state
    from siftmesh_core.orchestrator.scheduler import CapError, PolicyError
    from siftmesh_core.orchestrator.state_machine import IllegalTransitionError
    from siftmesh_core.orchestrator.workflow_runner import run_engine
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run_paths = RunPaths(root=root)
        state = read_run_state(run_paths)
        state = run_engine(
            run_paths, settings=load_settings(), single_step=(state.mode == "manual")
        )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        BackendUnavailableError,
        ValidationError,
        PolicyError,
        CapError,
        IllegalTransitionError,
    ) as exc:
        typer.echo(f"resume failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _echo_run_state(run_paths, state)


@app.command()
def status(run_dir: str) -> None:
    """Show a run's state-machine status (state, mode, gates, caps, per-task attempts)."""
    from pydantic import ValidationError

    from siftmesh_core.orchestrator.run_state_store import read_run_state
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        state = read_run_state(RunPaths(root=root))
    except (FileNotFoundError, NotADirectoryError, ValidationError) as exc:
        typer.echo(f"status failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"status: {root}")
    typer.echo(f"  state     : {state.state}{' (terminal)' if state.terminal else ''}")
    typer.echo(f"  mode      : {state.mode}")
    typer.echo(f"  iteration : {state.iteration}/{state.max_iterations}")
    typer.echo(f"  agent tasks completed: {state.agent_tasks_completed}")
    if state.blocked_gate:
        typer.echo(f"  blocked on gate: {state.blocked_gate}")
    if state.gates:
        typer.echo(f"  gates     : {', '.join(f'{g}={s}' for g, s in state.gates.items())}")
    for task_id, per_task in sorted(state.per_task.items()):
        typer.echo(
            f"  {task_id}: attempt {per_task.attempt}/{per_task.max_attempts} ({per_task.status})"
        )


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
def decompress(
    run_dir: str,
    archive: Annotated[
        str,
        typer.Option(help="Compressed memory capture, evidence-relative (e.g. Rocba-Memory.zip)."),
    ],
    evidence: Annotated[
        str | None, typer.Option(help="Evidence root (else recovered from readonly_mounts.json).")
    ] = None,
) -> None:
    """Decompress a memory archive (zip/7z) into evidence/extracted/ (derived; audited)."""
    from siftmesh_core.evidence.decompress import decompress_archive
    from siftmesh_core.orchestrator.scheduler import recover_evidence_root
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        evidence_root: Path = Path(evidence) if evidence else recover_evidence_root(run)
        outcome = decompress_archive(run, archive=archive, evidence_root=evidence_root)
    except (
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
        PathPolicyViolation,
        BackendUnavailableError,
        RuntimeError,
    ) as exc:
        typer.echo(f"decompress failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"decompress complete: {outcome.derived_path}")
    typer.echo(f"  format : {outcome.image_format}")
    typer.echo(f"  size   : {outcome.size_bytes} bytes")
    typer.echo(f"  sha256 : {outcome.sha256}")
    typer.echo(f"  derived: {outcome.decomp_id} (custody: {run.custody_log})")
    typer.echo(
        f"  next   : siftmesh analyze-memory {run.root} "
        f"--evidence {run.root} --memory {outcome.derived_path}"
    )


@app.command("ingest-derived")
def ingest_derived_cmd(
    run_dir: str,
    evidence: Annotated[
        str | None, typer.Option(help="Evidence root (else recovered from readonly_mounts.json).")
    ] = None,
) -> None:
    """Make extracted/decompressed derived artifacts plannable — one derived task each (hth.2)."""
    from pydantic import ValidationError

    from siftmesh_core.orchestrator.critic import ingest_derived
    from siftmesh_core.run_dir import RunPaths

    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run = RunPaths(root=root)
        created = ingest_derived(run, evidence_root=evidence)
    except (FileNotFoundError, NotADirectoryError, PathPolicyViolation, ValidationError) as exc:
        typer.echo(f"ingest-derived failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"ingest-derived: {len(created)} derived task(s) created")
    for path in created:
        typer.echo(f"  {path.stem}")
    if created:
        typer.echo(f"  next: siftmesh dispatch {run.root}")


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


def _resolve_gate(run_dir: str, gate: str, *, approve: bool) -> None:
    """Record an approve/reject gate decision; on approve, resume the engine."""
    from pydantic import ValidationError

    from siftmesh_core.config import load_settings
    from siftmesh_core.orchestrator.human_gate import GATES, set_gate
    from siftmesh_core.orchestrator.scheduler import CapError, PolicyError
    from siftmesh_core.orchestrator.state_machine import IllegalTransitionError
    from siftmesh_core.orchestrator.workflow_runner import run_engine
    from siftmesh_core.run_dir import RunPaths

    verb = "approve" if approve else "reject"
    matched = next((g for g in GATES if g == gate), None)
    if matched is None:
        typer.echo(f"{verb} failed: unknown gate {gate!r} (use {', '.join(GATES)})", err=True)
        raise typer.Exit(code=1)
    try:
        root = Path(run_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"run directory does not exist: {root}")
        run_paths = RunPaths(root=root)
        status: GateStatus = "approved" if approve else "rejected"
        state = set_gate(run_paths, matched, status)
        if approve:
            state = run_engine(
                run_paths, settings=load_settings(), single_step=(state.mode == "manual")
            )
    except (
        FileNotFoundError,
        NotADirectoryError,
        PathPolicyViolation,
        BackendUnavailableError,
        ValidationError,
        PolicyError,
        CapError,
        IllegalTransitionError,
    ) as exc:
        typer.echo(f"{verb} failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{verb}d gate {gate}")
    _echo_run_state(run_paths, state)


@app.command()
def approve(
    run_dir: str,
    gate: Annotated[str, typer.Option(help="plan | dispatch | retry | report")],
) -> None:
    """Approve a blocked gate and resume the engine."""
    _resolve_gate(run_dir, gate, approve=True)


@app.command()
def reject(
    run_dir: str,
    gate: Annotated[str, typer.Option(help="plan | dispatch | retry | report")],
) -> None:
    """Reject a blocked gate; the run halts cleanly on its next entry."""
    _resolve_gate(run_dir, gate, approve=False)


def _open_run(run_dir: str) -> RunPaths:
    """Resolve an existing run dir for the read-only inspection commands (exit 1 if absent)."""
    from siftmesh_core.run_dir import RunPaths

    root = Path(run_dir)
    if not root.is_dir():
        typer.echo(f"run directory does not exist: {root}", err=True)
        raise typer.Exit(code=1)
    return RunPaths(root=root)


def _printable(text: str, *, limit: int = 80) -> str:
    """One sanitized line of hostile-evidence-derived text (control chars stripped)."""
    flat = " ".join(text.split())
    safe = "".join(ch if ch.isprintable() else "?" for ch in flat)
    return safe if len(safe) <= limit else safe[: limit - 3] + "..."


@tasks_app.command("list")
def tasks_list(run_dir: str) -> None:
    """List a run's task contracts with their result status (read-only)."""
    from pydantic import ValidationError

    from siftmesh_core.schemas.task import TaskContract
    from siftmesh_core.schemas.task_result import TaskResult
    from siftmesh_core.schemas.yaml_io import read_yaml_model

    run = _open_run(run_dir)
    paths = sorted(run.tasks.glob("TASK-*.yaml"))
    if not paths:
        typer.echo("no tasks yet (run `siftmesh plan` first)")
        return
    for path in paths:
        try:
            contract = read_yaml_model(TaskContract, path)
        except (ValidationError, OSError):
            typer.echo(f"  {path.stem}  [invalid contract]")
            continue
        result_path = run.result_path(contract.task_id)
        status = "pending"
        if result_path.is_file():
            try:
                status = TaskResult.model_validate_json(
                    result_path.read_text(encoding="utf-8")
                ).status
            except ValidationError:
                status = "malformed-result"
        typer.echo(
            f"  {contract.task_id}  role={_printable(contract.role, limit=32)}  "
            f"profile={contract.assigned_agent_profile}  status={status}"
        )
    typer.echo(f"{len(paths)} task(s)")


@tasks_app.command("show")
def tasks_show(run_dir: str, task_id: str) -> None:
    """Show one task contract (validated, then echoed)."""
    from pydantic import ValidationError

    from siftmesh_core.schemas.task import TaskContract
    from siftmesh_core.schemas.yaml_io import read_yaml_model

    run = _open_run(run_dir)
    path = run.tasks / f"{task_id}.yaml"
    if not path.is_file():
        typer.echo(f"no such task: {task_id} ({path})", err=True)
        raise typer.Exit(code=1)
    try:
        read_yaml_model(TaskContract, path)  # prove it is a valid contract before echoing
    except ValidationError as exc:
        typer.echo(f"contract fails schema validation: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    raw = path.read_text(encoding="utf-8")
    typer.echo("".join(ch if ch.isprintable() or ch == "\n" else "?" for ch in raw))


@claims_app.command("list")
def claims_list(run_dir: str) -> None:
    """List the promoted findings ledger + the unsupported count (read-only)."""
    from siftmesh_core.ledgers.claim_ledger import read_claims, read_unsupported_claims

    run = _open_run(run_dir)
    claims = read_claims(run.root)
    for c in claims:
        artifact = _printable(c.source_artifact or "-", limit=40)
        typer.echo(
            f"  {c.claim_id}  [{c.status}]  conf={c.confidence:.2f}  "
            f"{artifact}  {_printable(c.claim, limit=60)}"
        )
    unsupported = read_unsupported_claims(run.root)
    typer.echo(
        f"{len(claims)} claim(s) in the findings ledger; "
        f"{len(unsupported)} unsupported (appendix-only, never facts)"
    )


@claims_app.command("show")
def claims_show(run_dir: str, claim_id: str) -> None:
    """Show one claim (findings ledger first, then the unsupported ledger)."""
    from siftmesh_core.ledgers.claim_ledger import read_claims, read_unsupported_claims

    run = _open_run(run_dir)
    for claim in read_claims(run.root):
        if claim.claim_id == claim_id:
            typer.echo(claim.model_dump_json(indent=2))
            return
    for claim in read_unsupported_claims(run.root):
        if claim.claim_id == claim_id:
            typer.echo(claim.model_dump_json(indent=2))
            typer.echo("status: UNSUPPORTED — rejected by the critic; never a report fact")
            return
    typer.echo(f"no such claim: {claim_id}", err=True)
    raise typer.Exit(code=1)


_AUDIT_LEDGERS = ("events", "tool-calls", "agent-calls", "retries", "token-budget")


@audit_app.command("tail")
def audit_tail(
    run_dir: str,
    lines: Annotated[int, typer.Option("--lines", "-n", help="How many trailing lines.")] = 20,
    ledger: Annotated[
        str,
        typer.Option(help="events | tool-calls | agent-calls | retries | token-budget"),
    ] = "events",
) -> None:
    """Tail an audit ledger (raw JSONL lines, newest last; read-only)."""
    run = _open_run(run_dir)
    targets = {
        "events": run.orchestration_events,
        "tool-calls": run.tool_calls,
        "agent-calls": run.agent_calls,
        "retries": run.retries,
        "token-budget": run.token_budget,
    }
    if ledger not in targets:
        choices = ", ".join(_AUDIT_LEDGERS)
        typer.echo(f"unknown ledger {ledger!r}; choose one of {choices}", err=True)
        raise typer.Exit(code=1)
    path = targets[ledger]
    if not path.is_file():
        typer.echo(f"no {ledger} recorded yet ({path})")
        return
    recorded = path.read_text(encoding="utf-8").splitlines()
    for line in recorded[-max(lines, 0) :]:
        typer.echo(line)
    typer.echo(f"-- {min(max(lines, 0), len(recorded))} of {len(recorded)} {ledger} line(s)")


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

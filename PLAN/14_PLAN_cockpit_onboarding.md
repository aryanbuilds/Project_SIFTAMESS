# PLAN 14 — Cockpit (Textual TUI) + unified setup/onboarding (Epic O)

_Status: **SHIPPED** 2026-06-11. Maintainer-greenlit the TUI now (CLI is mature); supersedes the
"Ratatui, last" framing in CLAUDE.md §13/§16 for the TUI layer._

## Goal

Collapse the human surface to **setup → run → tui**: a one-command onboarding (install + probe agents
+ pick a multi-agent set + remember it) and a live cockpit that shows a run as it happens — vitals,
pipeline, per-task status, timers, audit ticker, and a file-navigation tree. The deterministic CLI
commands stay for scripting; the cockpit is an additive, read-only layer.

## ADR — Textual, not Ratatui

CLAUDE.md §13 pencilled in "Rust/Ratatui … later" for the TUI. We chose **Textual** (Python, MIT):
it reuses our existing readers (`load_report_view`, `read_run_state`) with zero Rust toolchain, and
the cockpit is a thin renderer over data we already write. A run executes synchronously but is
**file-observable** (atomic `run_state.json` + append-only JSONL at every transition), so the app runs
the engine in a `@work(thread=True)` worker and a `set_interval` poll renders from the files — no
engine change, no shared mutable state. `textual` is an OPTIONAL extra (base install stays lean; the
CLI lazy-imports it with an install hint).

## Decisions (this session)
- **Command merge = additive.** Add `setup` + `tui`; every frozen CLI command keeps working. The
  cockpit subsumes status/tasks/claims/audit/agents as panels for humans.
- **Config persistence = global + project override.** `setup` writes
  `~/.config/siftmesh/siftmesh.toml` by default; a project `./siftmesh.toml` overrides it. Loader
  precedence: init > env > CWD toml > global toml > defaults (added a second TOML source + a tomlkit
  read-merge-write `save_agent_selection`).
- **TUI = full.** Home/run-picker, live cockpit (attach), onboarding screen, and a launcher that
  starts a new run in a worker thread.

## What shipped

- **Data layer** `tui/snapshot.py` (Textual-free, tested): `build_snapshot(run) -> CockpitSnapshot`
  reuses `read_run_state` (optional) + `load_report_view` + task contracts; timers from `updated_utc`
  (stage) and first/last event (total, frozen when terminal); pipeline completion from
  `state_machine.TRANSITIONS`; per-stage durations from `transition` events. Safe on a not-yet-started
  / run_state-less dir.
- **Cockpit** `tui/cockpit.py` (four zones + nav tree, 1 s poll); `tui/widgets.py` (pure Rich-markup
  renderers; every status doubled glyph+word for no-colour/colour-blind safety); `tui/cockpit.tcss`
  (teal vitals / green ribbon / amber ticker; `HORIZONTAL_BREAKPOINTS` collapses the right column when
  narrow). Gate keys `a`/`r` call the governed `human_gate.set_gate` + resume.
- **Onboarding** `tui/setup_screen.py` (probe → `SelectionList` multi-pick → persist) and headless
  `setup --no-tui/--yes`. **Launcher** `tui/launcher_screen.py` + `tui/runner.py` (mirrors `cli.run`
  init+drive). **Home** `tui/app.py`.
- **Config** `config.py`: `global_config_path()`, the global TOML source, `save_agent_selection`.
- **CLI** `cli.py`: `setup`, `tui`; `doctor` gains a `tui:` textual check. **pyproject**: `tui` extra
  (`textual>=8,<9`) + `tomlkit` base dep.
- **Tests** `tests/EPIC_O_TESTS/`: snapshot vs the golden run (+ a synthetic run_state for the live
  path) and timer-freeze; config persistence + precedence + merge; `setup`/`tui` CLI (headless persist
  + lazy-textual fallback); a Textual `App.run_test()` pilot (via `asyncio.run`, `importorskip`'d) for
  cockpit/home/onboarding mount. No real engine, no live agent, no SANS evidence (§2B).

## Constraints honoured
Deterministic governance untouched (read-only cockpit; launching reuses the governed engine; no new
write paths, evidence access, MCP tools, or raw shell; agent subprocesses keep the Epic-Q cwd/env
sandbox). All frozen commands intact. CI not a concern. Textual 8.2.7 (MIT) — re-confirm API on major
bumps (`@work`, `HORIZONTAL_BREAKPOINTS`, `SelectionList`).

## Verify
`uv run pytest -q` (incl. EPIC_O; ruff/format/mypy clean) · `uv run siftmesh setup --no-tui --yes`
writes the global config · `uv run siftmesh tui case_runs/RUN-GOLDEN` renders the four zones · a real
evidence run from the TUI is maintainer-gated (§2B).

#!/usr/bin/env bash
# SIFTMesh demo — zero-keys, deterministic floor (tier T0). Pass --agent claude (etc.) to go live.
#
#   bash examples/demo_case/run_demo.sh                # deterministic floor (no keys)
#   bash examples/demo_case/run_demo.sh --agent claude # live, self-correcting agent (needs auth)
#
# Reaches `state: done` and writes a full run dir under examples/demo_case/case_runs/ (git-ignored).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CASE="$REPO_ROOT/examples/demo_case"

cd "$REPO_ROOT"
uv run siftmesh run "$CASE" --evidence "$CASE/evidence" --auto "$@"

RUN="$(ls -dt "$CASE"/case_runs/RUN-* | head -1)"
echo
echo "Run directory: $RUN"
echo "  claims : $RUN/claims/claim_ledger.jsonl"
echo "  tools  : $RUN/audit/tool_calls.jsonl"
echo "  critic : $RUN/audit/critic_verdicts.jsonl"
echo "  report : $RUN/reports/final_report.md"
echo
echo "Replay the audit timeline:  uv run siftmesh replay \"$RUN\""
echo "Watch it in the cockpit:    uv run siftmesh tui \"$RUN\""

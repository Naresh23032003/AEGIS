#!/usr/bin/env bash
# Autonomous phase loop. Each iteration launches a FRESH headless Claude Code
# session (Sonnet) that executes exactly one phase, then a mechanical gate
# checks the result before the next phase starts.
#
# Prereqs: Docker Desktop running, claude CLI installed and logged in,
# .env populated (GROQ_API_KEY needed from phase 2 for live runs).
#
# Run from repo root:  ./scripts/autobuild.sh
# Stops on: gate failure, two failed attempts at one phase, or phase-6 done.
#
# Note: sessions run with --dangerously-skip-permissions so the loop never
# blocks on a prompt. Only run this on a machine and repo you trust it with.

set -euo pipefail
cd "$(dirname "$0")/.."

next_phase() {
  local last
  last=$(git tag -l 'phase-*' | sed 's/phase-//' | sort -n | tail -1)
  if [ -z "$last" ]; then echo 0; else echo $((last + 1)); fi
}

attempts=0
current=-1

while true; do
  N=$(next_phase)

  if [ "$N" -gt 6 ]; then
    echo "All phases tagged. Stop here and request the final review."
    exit 0
  fi

  if [ "$N" -eq "$current" ]; then
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 2 ]; then
      echo "Phase $N failed twice. Human needed. See docs/reports/ and git log."
      exit 1
    fi
    PROMPT="Phase $N was attempted but not completed (no phase-$N tag). Read CLAUDE.md, then plan/phases/phase-$N.md, inspect the current state of the repo and any partial work, fix what is broken, and finish phase $N: all acceptance criteria passing, docs/reports/PHASE_${N}_REPORT.md written with pasted output, committed on branch phase-$N, tag phase-$N created. Do not start any other phase."
  else
    current=$N
    attempts=0
    PROMPT="Read CLAUDE.md, then plan/phases/phase-$N.md, and execute phase $N completely: build, test against the acceptance criteria it references, write docs/reports/PHASE_${N}_REPORT.md with pasted real output, commit conventionally on branch phase-$N, and create git tag phase-$N only when acceptance passes. Do not read other plan files beyond what the brief lists. Do not start any other phase."
  fi

  echo "=== Phase $N (attempt $((attempts + 1))) ==="
  claude -p "$PROMPT" --model sonnet --dangerously-skip-permissions || true

  if ./scripts/gate.sh "$N"; then
    echo "=== Phase $N gate passed ==="
  else
    echo "=== Phase $N gate failed, will retry once with a fix prompt ==="
  fi
done

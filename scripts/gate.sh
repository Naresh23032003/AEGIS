#!/usr/bin/env bash
# Mechanical gate between phases. Not a substitute for the human-model review
# in plan/07; this only catches the failures a script can catch.
# Usage: ./scripts/gate.sh <phase-number>

set -uo pipefail
cd "$(dirname "$0")/.."
N="${1:?phase number required}"
fail=0

say() { echo "gate: $*"; }

# 1. Tag exists
if ! git tag -l "phase-$N" | grep -q .; then
  say "FAIL: tag phase-$N missing"; fail=1
fi

# 2. Phase report exists and is non-trivial
report="docs/reports/PHASE_${N}_REPORT.md"
if [ ! -s "$report" ] || [ "$(wc -l < "$report")" -lt 15 ]; then
  say "FAIL: $report missing or too thin"; fail=1
fi

# 3. Writing rules
# git grep only searches tracked files, so gitignored build output
# (.venv, node_modules, generated/) never enters this check on its own.
# plan/ and PLAN.md are the pre-existing spec, not this repo's own
# writing, and are excluded deliberately.
if git grep -In $'\xe2\x80\x94' -- . ':!plan' ':!PLAN.md' ':!scripts/gate.sh' -q 2>/dev/null; then
  say "FAIL: em dash found"; fail=1
fi

# 4. Security invariants (cheap greps, deep review happens later)
if git grep -n "shell=True" -- apps/ -q 2>/dev/null; then
  say "FAIL: shell=True present"; fail=1
fi

# 5. Lint and unit tests
if ! make lint test > /tmp/gate_lint_test.log 2>&1; then
  say "FAIL: make lint test (see /tmp/gate_lint_test.log)"; fail=1
fi

# 6. Fixture e2e from phase 2 onward
if [ "$N" -ge 2 ]; then
  if ! MOCK_LLM=1 make e2e > /tmp/gate_e2e.log 2>&1; then
    say "FAIL: make e2e (see /tmp/gate_e2e.log)"; fail=1
  fi
fi

if [ "$fail" -eq 0 ]; then
  say "phase $N clean"
fi
exit "$fail"

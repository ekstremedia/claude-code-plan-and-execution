#!/usr/bin/env bash
#
# Example test wrapper. Copy to bin/test-<lang> in your project and adapt.
#
# The point is not convenience. It is that every agent prompt can then say
#
#     bin/test-php tests/Feature/Billing.php
#
# instead of carrying a 200-character environment-pinned command that has to be
# repeated in every worker agent, gets mistyped, and drifts when the test setup
# changes. Four properties matter:
#
#   1. An explicit target is required. Refusing an empty argument is what stops
#      an agent from accidentally running the full suite.
#   2. The environment is pinned here, once, instead of in every prompt.
#   3. The real exit code is preserved. Agents branch on it.
#   4. Full output goes to a log; only a short summary reaches stdout on
#      success, and only the relevant excerpt on failure. Test logs are the
#      single largest source of wasted context in an agent run.

set -uo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $(basename "$0") <test-path> [more paths...]" >&2
  echo "refusing to run without an explicit target" >&2
  exit 2
fi

LOG="$(mktemp -t test-run.XXXXXX.log)"

# --- adapt this line, and only this line, to your project ----------------------
# Docker example:
#   docker compose exec -T \
#     -e APP_ENV=testing -e DB_CONNECTION=sqlite -e DB_DATABASE=:memory: \
#     app php artisan test "$@" >"$LOG" 2>&1
# Node example:
#   npx vitest run "$@" >"$LOG" 2>&1
"${TEST_CMD:-echo}" "$@" >"$LOG" 2>&1
# ------------------------------------------------------------------------------

status=$?

if [[ $status -eq 0 ]]; then
  # One line on success. Adjust the grep to match your runner's summary line.
  summary="$(grep -E '([0-9]+ (passed|tests?))' "$LOG" | tail -1)"
  echo "PASS  ${summary:-completed}  ($*)"
  echo "log: $LOG"
else
  echo "FAIL  exit $status  ($*)"
  echo "--- relevant output ---"
  # Show failures and errors, not the whole run.
  grep -nE '(FAIL|FAILED|Error|Exception|✕|✗|assert)' "$LOG" | head -40
  echo "--- full log: $LOG ---"
fi

exit $status

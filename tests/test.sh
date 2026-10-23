#!/bin/bash
set -euo pipefail

LOG_DIR=/logs/verifier
REWARD_FILE="$LOG_DIR/reward.txt"
STATUS_FILE="$LOG_DIR/verification-status.txt"
REPORT_FILE="$LOG_DIR/junit.xml"
SCORING_FILE="$LOG_DIR/scoring-report.json"
STDOUT_FILE="$LOG_DIR/test-stdout.txt"
TRUSTED_PYTHON=/usr/local/bin/python3
TRUSTED_TIMEOUT=/usr/bin/timeout
# inner timeout 240s leaves cleanup time under the 300s verifier budget
SITE_PACKAGES="$(mktemp -d /tmp/hbr-site.XXXXXX)"
RUN_DIR="$(mktemp -d /tmp/hbr-run.XXXXXX)"
TRUSTED_PYTHONPATH="$SITE_PACKAGES:/tests"
TRUSTED_PYTHONNOUSERSITE=1
TRUSTED_PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
JUNIT_OPTION=--junitxml
PYTEST_CACHE_OPTION="-p no:cacheprovider"
finalized=0

mkdir -p "$LOG_DIR"
echo "0" > "$REWARD_FILE"
printf 'INCOMPLETE: verification started\n' > "$STATUS_FILE"
: > "$STDOUT_FILE"

seal_reward() {
  chmod 0444 "$REWARD_FILE" 2>/dev/null || true
}

write_failure() {
  printf '0.000000\n' > "$REWARD_FILE"
  printf 'INCOMPLETE: %s\n' "$1" > "$STATUS_FILE"
}

on_exit() {
  local status=$?
  if [[ "$finalized" -eq 0 ]]; then
    write_failure "unexpected verifier exit ${status}"
  fi
  seal_reward
  exit "$status"
}

on_signal() {
  finalized=1
  write_failure "verification interrupted"
  seal_reward
  exit 130
}

trap on_exit EXIT
trap on_signal INT TERM HUP

if ! env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp \
    "$TRUSTED_PYTHON" -I -S -s -P -B /tests/bootstrap_wheels.py \
    --wheel-dir /tests/wheels --requirements /tests/requirements.txt \
    --target "$SITE_PACKAGES" > "$LOG_DIR/bootstrap.log" 2>&1; then
  write_failure "offline dependency bootstrap failed"
  exit 0
fi

chmod -R a+rX "$SITE_PACKAGES"
if [[ "$EUID" -eq 0 ]]; then
  chown worker:worker "$RUN_DIR"
fi

set +e
if [[ "$EUID" -eq 0 ]]; then
  /bin/su -s /bin/bash worker -c \
    "/tests/run_pytest.sh '$SITE_PACKAGES' '$RUN_DIR' '$TRUSTED_PYTHON' \
     '$TRUSTED_TIMEOUT' '$JUNIT_OPTION' '$PYTEST_CACHE_OPTION'" \
    > "$RUN_DIR/pytest.log" 2>&1
else
  /bin/bash /tests/run_pytest.sh \
    "$SITE_PACKAGES" "$RUN_DIR" "$TRUSTED_PYTHON" "$TRUSTED_TIMEOUT" \
    "$JUNIT_OPTION" "$PYTEST_CACHE_OPTION" \
    > "$RUN_DIR/pytest.log" 2>&1
fi
pytest_status=$?
set -e

cat "$RUN_DIR/pytest.log" > "$STDOUT_FILE" 2>/dev/null || true
printf '\npytest_exit=%s\n' "$pytest_status" >> "$STDOUT_FILE"

if [[ ! -s "$RUN_DIR/junit.xml" ]]; then
  write_failure "pytest did not produce a structured report"
  exit 0
fi

cp "$RUN_DIR/junit.xml" "$REPORT_FILE"

# score.py validates this structured report with ET.parse before writing reward.
if ! env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp \
    "$TRUSTED_PYTHON" -S -s -P -B /tests/score.py \
    "$REPORT_FILE" "$REWARD_FILE" "$STATUS_FILE" "$SCORING_FILE" "$pytest_status"; then
  write_failure "trusted result parser failed"
  exit 0
fi

finalized=1
seal_reward
trap - EXIT INT TERM HUP
exit 0

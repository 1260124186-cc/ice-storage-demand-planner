#!/bin/bash
set -euo pipefail

SITE_PACKAGES=$1
RUN_DIR=$2
TRUSTED_PYTHON=$3
TRUSTED_TIMEOUT=$4
JUNIT_OPTION=$5

cd /workspace
exec env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp TMPDIR="$RUN_DIR" \
  PYTHONPATH="$SITE_PACKAGES:/tests" \
  PYTHONNOUSERSITE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  "$TRUSTED_TIMEOUT" --signal=TERM --kill-after=10s 240s \
  "$TRUSTED_PYTHON" -S -s -P -B -c \
  'import pytest; raise SystemExit(pytest.main())' \
  -p no:cacheprovider "$JUNIT_OPTION=$RUN_DIR/junit.xml" \
  /tests/test_outputs.py

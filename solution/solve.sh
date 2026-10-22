#!/bin/sh
set -eu
for module in __init__.py model.py storage.py billing.py planner.py cli.py __main__.py; do
  install -m 0644 "/solution/$module" "/workspace/coldstore_planner/$module"
done

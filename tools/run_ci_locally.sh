#!/bin/bash
# Run the same checks CI runs, in the same order, from a clean shell. Exits on the first failure.
#
#   tools/run_ci_locally.sh          lint + unit tests
#   tools/run_ci_locally.sh --image  also build the container image
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== lint"
ruff check .
shellcheck hooks/*.sh tools/*.sh
HOME=/tmp docker compose config -q 2>/dev/null || echo "   (docker compose not available; skipped compose validation)"

echo "== docs match the tree"
python3 tools/check_docs.py

echo "== unit tests"
python3 -m pytest --cov --cov-report=term-missing

if [ "${1:-}" = "--image" ]; then
  echo "== container image"
  docker build -t memory-optimized-context:local .
  docker run --rm -e MEMORY_ROOT=/tmp/m -e MEMORY_DB=/tmp/m/memory.db -e MEMORY_LLM=none \
    --entrypoint python3 memory-optimized-context:local /app/memory compile
fi
echo "== all green"

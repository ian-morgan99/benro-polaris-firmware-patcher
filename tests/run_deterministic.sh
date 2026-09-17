#!/usr/bin/env bash
# Deterministic regression harness for container/test_*.sh
# Usage: ./tests/run_deterministic.sh [test_name]
set -euo pipefail
TEST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TEST_DIR/container"
echo "=== Deterministic test harness ==="
for t in test_*.sh; do
    echo "--- $t ---"
    bash -c "set -euo pipefail; ./$t" || echo "FAIL: $t"
done
echo "=== Done ==="

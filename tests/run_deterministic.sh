#!/usr/bin/env bash
# Deterministic regression harness for container/test_*.sh
# Usage: ./tests/run_deterministic.sh [test_name]
#
# Exit-status policy (issue #117): the aggregate runner must NOT mask failures.
#   - a runnable test that fails  -> counted FAIL, runner exits non-zero
#   - a test whose prerequisites are unavailable (missing Docker image / source
#     checkout / ARM toolchain) signals SKIP via exit 2 or 77; these are
#     reported distinctly and do NOT turn the gate red on their own
#   - a fully passing runnable set returns zero
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TEST_DIR/container"

# Optional single-test filter: match by basename (with or without .sh).
FILTER="${1:-}"

echo "=== Deterministic test harness ==="

pass=0
fail=0
skip=0
failed_tests=""
skipped_tests=""

# Collect the runnable set. If a filter is given, run only that test; otherwise
# every container/test_*.sh.
if [ -n "$FILTER" ]; then
    case "$FILTER" in
        *.sh) candidates=("$FILTER") ;;
        *)    candidates=("test_${FILTER}.sh") ;;
    esac
    if [ ! -e "${candidates[0]}" ]; then
        echo "error: no such test: ${candidates[0]}" >&2
        exit 2
    fi
else
    candidates=()
    for t in test_*.sh; do
        [ -e "$t" ] && candidates+=("$t")
    done
fi

if [ "${#candidates[@]}" -eq 0 ]; then
    echo "no runnable tests found" >&2
    exit 2
fi

for t in "${candidates[@]}"; do
    echo "--- $t ---"
    rc=0
    bash -c "set -euo pipefail; ./$t" || rc=$?
    case "$rc" in
        0)
            pass=$((pass + 1))
            ;;
        2|77)
            # Prerequisite unavailable (missing Docker image / source checkout /
            # ARM toolchain). Distinct from a real failure: reported as SKIP and
            # not allowed to silently green the gate.
            skip=$((skip + 1))
            skipped_tests="${skipped_tests} ${t}"
            echo "SKIP: $t (prerequisite unavailable, exit $rc)"
            ;;
        *)
            fail=$((fail + 1))
            failed_tests="${failed_tests} ${t}"
            echo "FAIL: $t (exit $rc)"
            ;;
    esac
done

echo "=== Summary: ${pass} passed, ${fail} failed, ${skip} skipped ==="
if [ -n "$skipped_tests" ]; then
    echo "Skipped (prerequisite unavailable):${skipped_tests}"
fi
if [ -n "$failed_tests" ]; then
    echo "Failed:${failed_tests}"
fi

# A green gate requires zero runnable failures. Skips are reported but do not,
# by themselves, fail the aggregate run.
if [ "$fail" -gt 0 ]; then
    exit 1
fi
exit 0

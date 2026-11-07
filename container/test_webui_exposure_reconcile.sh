#!/bin/sh
# WebUI exposure-write reconciliation regression test.
#
# Drives container/astro/webui/app.js under a DOM stub and feeds it the reply
# shapes the head really produces, including 'ret:-2110' -- the code the camera
# returns when it is not idle and DROPS a write after the HTTP request has
# already been answered ok:true. Measured on a K-1 II: 62% of exposure writes
# come back that way, so silently reporting success is the failure this guards.
#
# Needs node only; no network, no rig. Skips (exit 2) if node is absent, per the
# exit-status policy in tests/run_deterministic.sh.
set -eu
here="$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
    echo "[webui-exposure] SKIP: node not available"
    exit 2
fi

# Syntax-check the shipped page first: a stray brace in app.js would otherwise
# surface here as an opaque runtime TypeError under the DOM stub.
node --check "$here/astro/webui/app.js"

exec node "$here/test_webui_exposure_reconcile.js"

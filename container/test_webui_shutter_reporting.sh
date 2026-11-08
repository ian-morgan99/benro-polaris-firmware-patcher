#!/bin/sh
# WebUI shutter-release reporting regression test (issue #279).
#
# The shutter button painted "shot" as soon as its POST resolved. That POST only
# queues the command; the head answers asynchronously on opcode 264 with a capture
# lifecycle state. On a K-1 II the camera refused the capture with state:-110 and
# PHOTO_RECORD Fail while the screen said "shot" -- so the user pressed the shutter,
# saw success, and got no file. Same false-success class as the exposure writes in
# #276, which is guarded by test_webui_exposure_reconcile.sh.
#
# Also guards the iOS hold-to-fire hardening: Safari raises the long-press callout
# inside the 450 ms hold window, which fires pointercancel and aborts the press, so
# without -webkit-touch-callout:none a deliberate hold silently does nothing on
# iPhone/iPad.
#
# Needs node only; no network, no rig. Skips (exit 2) if node is absent, per the
# exit-status policy in tests/run_deterministic.sh.
set -eu
here="$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
    echo "[webui-shutter] SKIP: node not available"
    exit 2
fi

# Syntax-check the shipped page first: a stray brace in app.js would otherwise
# surface here as an opaque runtime TypeError under the DOM stub.
node --check "$here/astro/webui/app.js"

exec node "$here/test_webui_shutter_reporting.js"

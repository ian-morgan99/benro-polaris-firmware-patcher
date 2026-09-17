# Issue #82 Layer C: K-3 III Polaris runtime test

Date: 2026-09-15
Camera: Pentax K-3 Mark III, USB `25fb:0189`
Polaris: `FwVer:4.0.0.32;date:2025.05.09;`
Runtime: `polestar_app` PID 248, `pgphoto.stage2ondisk` PID 249
Evidence directory: `/tmp/pentax82-layer-c-20260915/`

## Attachment verification

The first check after the physical move initially found no camera. A later check found
`Bus 001 Device 009: ID 25fb:0189`; the camera had then enumerated correctly. The
K-1 II was left disconnected.

## Tests and results

| Test | Result | Evidence |
|---|---|---|
| Camera info `1&286&4&#` | PASS | `9090.txt`; K-3 III, state 1, storage 2 |
| Live-view get/set (`292`, `291`) | PASS | `9090.txt`; `292@state:1`, `291@state:1;ret:0` |
| HTTP preview stream | PASS | `http-preview.txt`, `stream.bin`; 400172 bytes, multipart JPEG, `Content-Length: 68022`, JPEG SOI `ff d8` |
| Capture while preview active | FAIL/diagnostic | `capture-9090.txt`, `post-markers.txt`; state 4 then state -108 for `SP_0023.jpg`, while preview frames continued |
| Preview-off capture control | PASS | `capture-preview-off.txt`, `post-control.txt`; state 1 -> 4 -> 2 -> 3 -> 5, `captureImage ret 0`, `SP_0024.jpg` |
| Two back-to-back preview-off captures | PASS | `back-to-back.txt`; `SP_0025.jpg` and `SP_0026.jpg`, both terminal state 0 on wire and states 2/3/5 in Clog |
| Runtime health after stress | PASS | USB remained `25fb:0189`; pgphoto stayed PID 249; 8080 and 9090 remained listening |

## Actionable result

The first controlled failure occurred with preview active: capture reached state 4 and
then returned state -108, while preview continued. The immediate preview-off control
completed normally, and two consecutive captures then completed normally. This is
consistent with a preview/capture interaction or timing boundary, but does not by
itself prove root cause. The next adversarial test should repeat the capture with
preview enabled at controlled offsets and capture the exact first abnormal event.

No reboot, USB reconnect, camera power-cycle, file deletion, or direct runtime mutation
was performed.

## Command injection during capture

While a preview-on capture was active, a simultaneous camera-info request
(`1&286&4&#`) was issued. The command returned a valid K-3 III state response,
and the capture completed with `ret 0`, file `SP_0030.jpg`, and terminal state
`5`. USB, pgphoto, 8080, and 9090 remained healthy. The local command socket
timed out after receiving the asynchronous response; this was client socket
closure behavior, not a camera/runtime failure.

This single injection does not prove all concurrent commands are safe, but it
does not reproduce a failure for camera-info during the tested capture phase.

## Focus dispatch

Both `1&311&1&mode:1;adj:-1;#` and `adj:1` returned `311@ret:0`. Clog recorded
the Pentax manual-focus drive response `0x2001`, dispatch values `focus:2` and
`focus:-2`, and successful `updateCameraManualFocus` / `setFocusChange` returns.
The runtime and preview remained healthy. Physical lens movement was not
independently observed in this run, so this is a dispatch-level PASS only, not
a physical focus qualification.

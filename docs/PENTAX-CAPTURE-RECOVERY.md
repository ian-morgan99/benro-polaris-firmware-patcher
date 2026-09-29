# Polaris Pentax capture recovery by first failing boundary

This is the cross-layer operator map for a Polaris `state:-1005` / libgphoto2
`-110` result. The status code alone is not enough to choose a recovery. Preserve
the camera power/USB session and capture the request-generation logs before
any process restart, USB reset, power cycle, or second shutter.

| First observed boundary | Owning layer / diagnosis | Safe recovery | Do not |
|---|---|---|---|
| No Stage-2 `capture-enter` for the request | pgphoto request dispatch, operation-owner gate, or earlier application path; the camlib was not entered. | Inspect pgphoto client/generation, session state and request mapping. Rebind only after proving no exposure/output owner is live. | Change Pentax conditions rules, or retry the shutter blindly. |
| Stage-2 enter/return exists, no Pentax `camlib-enter` | Generic libgphoto2 routing, wrong camlib/model path, or session-layer failure. Compare loaded modules and exact GP return. | Restore the exact matched core/port/camlib stack or valid session; rerun only after the camera state and output ownership are known. | Assume Pentax returned PTP DeviceBusy. |
| Pentax reports admission reason `conditions-unreadable` | PTP session/readiness query cannot be trusted. | Keep camera connected; recover a readable session; require a complete strict conditions probe before a later independent capture request. | Treat Polaris `state=1` as sufficient or use a sleep-and-shoot workaround. |
| Pentax reports `unsafe-activity` or `capture-active` (+104/+32) | Camera work may still be active. | Let that operation finish and obtain a fresh strict-safe probe. | Start another shutter, clear the guard, or weaken predicates without direct evidence. |
| Pentax reports `pending-candidate` (+36) | A prior image has no proven request-generation owner. | Preserve it; recover/transfer through a generation-aware owner path. Until that path exists, leave capture blocked. | Delete it or misattribute it to the next request. |
| Stage-2 enter + Pentax `initiate-return` is PTP DeviceBusy/non-OK | Camera rejected the request or the response leaves state uncertain. | libgphoto2 now arms `recovery_required`; do not replay. A later request needs a fresh positive strict probe. | Automatic retries or claims that no exposure occurred based only on the response. |
| InitiateCapture succeeded, but candidate/transfer/publication is missing | Post-initiation camera, transfer, pgphoto lifetime or publication failure. | Preserve logs and the camera-side candidate; keep next shutter blocked; recover only with verified ownership. | Restarting into a new capture generation or deleting candidate data. |
| USB disconnect/reset or pgphoto PID changes | Transport/session generation changed. | Record kernel USB events, PID/generation, Clog/Mlog and candidate state; rebind only after preservation and fresh camera init. | Call it a completed capture or immediately send another shutter. |

## Current code mitigation

libgphoto2 `f05f65826` makes the Pentax strict +32/+36/+104 admission sample
unconditional before every `InitiateCapture`, emits reason/action diagnostics
to stderr, and arms recovery after any failed InitiateCapture. It is embedded
in candidate `o-v13t-strict-admission-20260929`, not the currently installed
o-v13s FwPkt. The Stage-2 wrapper defaults `STAGE2_CAPTURE_TRACE=1`; a live
failure must be followed by immediate preservation of complete Clog/Mlog and
capture-boundary stderr before reconnect can rotate the logs.

Candidate validation: libgphoto2 fresh deterministic regression 13/13;
patcher offline 14 container + 24 Python; package gate 4/4; harness 62/62; and
the final appfs payload's `ptp2.so`, both libgphoto2 cores and pgphoto matched
the generated bundle by SHA-256. Candidate is not installed and no new live
shutter was sent. The iPolar adapter compile-check remains untested here because
the libuvc headers are unavailable.

## Recovery limitation

No source/API in the current pgphoto package safely publishes an orphaned
candidate as a separate recovered output with its own generation. The camera
image may still be recoverable, but until the owner-level publication contract
exists, fail-closed preservation is safer than automatic retry/delete. The
library-side decision table is in
[`libgphoto2 docs/pentax/CAPTURE-RECOVERY.md`](https://github.com/ian-morgan99/libgphoto2/blob/f05f65826/docs/pentax/CAPTURE-RECOVERY.md).

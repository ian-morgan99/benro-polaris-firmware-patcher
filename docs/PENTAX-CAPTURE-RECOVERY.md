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
| Identity goes to `none` with **no** driver error (`0x2001` right up to the drop) | Kernel removes the device mid-teardown while a goto slew is running; the removal uevent stream stops early and the body never re-enumerates. Not a libgphoto2 failure (issue #347). | Power-cycle the **camera body**, not the mount. See "A host reboot does not recover the camera" below. | Reboot Polaris and conclude the link is dead; gate recovery on a driver error, because there is none. |

## A host reboot does not recover the camera (issue #347)

When the body drops off USB permanently, **restarting Polaris does not help** —
and it looks like it should, because the mount comes back completely healthy.
Observed 2026-11-16 on a K-3 III (`25fb:0189`, serial `8093033`):

- The kernel removes the device first. `Mlog` shows `NetlinkUeventTask` emitting
  `remove@/…/xhci_0/usb1/1-1/1-1.2` and only *then* does the app broadcast
  `code[274],val[state:0;]`, followed ~1 s later by
  `manufacturer:none;model:none`. The `state:0` broadcast is a **consequence** of
  removal, not a cause — an earlier version of this note claimed Live View was
  being stopped and had the causality backwards.
- A healthy teardown emits the full uevent set (six lines: interfaces then the
  device). The fatal removal emitted only **two** and stopped, so the teardown
  path itself appears to have been interrupted.
- Motor activity predicts recovery, not the drop: the one removal with zero motor
  events in a ±20 s window re-enumerated 12 minutes later; both removals that
  never returned had hundreds of motor events in that window, and in session 31
  the kernel removed the camera **6 ms** after `GotoAuTask: SP_GOTO_STA_WAIT_RESULT`.
- There is **no driver-side error to gate on**: zero `0x02ff`, zero I/O errors,
  zero `-1` in the whole session. All 137 frames succeeded on first attempt, and
  the last `Pentax preview stage get-frame` returned `0x2001` normally (73,189
  bytes, 1 attempt, 16 ms) shortly before the bus went silent.
- After a reboot, the next two sessions contain no `25fb` at all, and that
  boot's `dmesg` has no `usb 1-1.2` lines — versus the previous boot, which
  showed the body enumerating properly before dying on a
  `reset high-speed USB device`.
- The hub itself is fine: unbind/rebind of `1-1` logs `hub 1-1:1.0: 4 ports
  detected`, with nothing attached to any port. Rebinding the xHCI controller
  (`100e0000.xhci_0`) restores the hub cleanly and still does not bring the
  camera back.

A USB device wedged internally generally needs its own power cycle, and a host
reboot never gives it one. **Power-cycle the body** (battery out, or off and
back on). Do not conclude the link is dead from a rebooted mount with an empty
bus.

Two related traps in the same incident:

- **`usbmode` is persisted to flash.** The USB compatibility toggle (`code:813`,
  logged as `setting usbmode to N`) writes through `SP_SaveUserParamToFlash`, so
  it survives a reboot and can independently suppress enumeration. In this
  capture it was set to `0` eight minutes *after* the camera was already gone,
  so it cannot have caused the drop — but "camera absent after reboot" may be
  **two stacked faults**. Set `usbmode` back to `1` *and* power-cycle the body.
  The live value is not readable from `mtd2` (`userParam` yields only a factory
  placeholder block), `authorized_default` is empty, and debugfs is not mounted.
- **`usb_disconnect` is not a Clog event.** It appears zero times in both affected
  sessions; it is a kernel `dmesg` line. Grepping Clog for it finds nothing and
  can wrongly suggest no detach was recorded. The Clog-side markers are the
  identity broadcast going to `none` and the supervisor's `stable identity
  change: … -> none`.

The supervisor now logs one `camera_absent: <identity> has not re-enumerated for
N polls …` line per episode (patcher `052125d`), so the outage is visible instead
of the supervisor polling an empty bus silently. That reports the fault; it does
not recover it — recovery remains open under issue #146.

## Current code mitigation

libgphoto2 `f05f65826` makes the Pentax strict +32/+36/+104 admission sample
unconditional before every `InitiateCapture`, emits reason/action diagnostics
to stderr, and arms recovery after any failed InitiateCapture. It is embedded
in candidate `o-v13t-strict-admission-20260929`, not the currently installed
o-v13s FwPkt. The Stage-2 capture trace adds an outer call boundary and is now
explicitly opt-in; normal builds default to direct-to-core capture dispatch.
Pentax's own lower-layer markers remain available without that wrapper. A live
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

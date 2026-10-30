# K-1 II lag: v90 investigation and isolated follow-up

This branch starts at patcher `f344e41261a886f8f6107b9467095bc90b3835a1`,
the v90 source; its current work is not merged, packaged or deployed. The
consumer-discovered delays have not been reproduced at a directly connected
PC's clean libgphoto2 boundary, so no library protocol change is justified by
this investigation.

## What is established

The v89 startup sometimes exceeded the old 20-second wait. The v90 restart
helper permits 90 seconds; that addresses an early timeout, but does not prove
the camera became fast or that setting writes succeeded. The v90 helper checked
the process once, then could report success if *any* 8080 listener appeared
after the process exited. The local partial fix checks the process identity
again on each pass. A simulated late process exit with a later unrelated
listener makes the unmodified v90 script return success; the changed script
rejects it. A simulated 24-second start passes the changed test, while the
original hard-coded 20-second helper fails the same slow-start case. Hung
startup still fails within a short configured test bound.

This is **not a complete readiness guarantee**: the helper does not verify
that the listener belongs to pgphoto, distinguish same-name PID reuse, verify
restart-lock ownership throughout the wait, or establish camera readiness.
The check and the listener observation are not atomic. None of these tests
exercises a physical device; do not deploy based on them alone.
The host test uses uniquely named fake wrappers, checks their command lines
before signalling, waits for their bounded children and fails if cleanup cannot
complete. There remain small signal-startup and check-to-signal races; do not
represent this as an atomic process-identity mechanism.

In the pinned libgphoto2 source, the K-1 II capability entry does not enable
the `supports_pc_live_view` gate used by `_get_Pentax_AutofocusDrive`, while
K-3 III does. This is evidence of the *current code gate*, not proof the
physical K-1 II lacks autofocus or live view. In exact v90 pgphoto, a failed
single-widget lookup triggers a full configuration-tree lookup. Existing logs
do not time those calls separately or show that they cause the reported write
latency. Do not bypass a widget or permanently cache its absence without
proving the relevant state transitions and model identity.

## Unreleased opt-in timing prototype

`STAGE2_CONFIG_TIMING=1` at pgphoto process start enables timing of the core
single-widget reads, single-widget writes and full-tree reads crossing the
Stage-2 slots. Logs contain PID, thread ID, operation, widget name, raw core
return code and monotonic start/end timestamps; they contain no widget values.
The record is of the **core** return before the existing empty-widget guard,
not necessarily the final result seen by pgphoto. The existing guard emits its
own diagnostic if it rejects a result. Calls internal to the library, the busy
status owner, PTP operations and actual camera setting readback are outside
this probe's visibility.

By default the full-tree slot stays direct to core, and the single-widget
wrappers perform only an extra environment check; the timing calls and logs are
disabled. The new tree wrapper is installed only when the flag is already set
at startup. Changing the flag during a process lifetime is not a supported
control: it would yield inconsistent coverage. Host-only tests check call
counts, arguments, selected errno behavior, disabled/enabled slot selection,
clock failures, and the distinction between raw success and guard rejection.
The existing guard, write/settle and synthetic fallback tests also passed.

This is a prototype, **not safe for live use yet**. When enabled it adds
synchronous stderr logging for all camera vendors; logging can delay a write,
fill storage, or fail on a closed pipe. The tests do not yet cover those
logging failures, concurrent calls, actual ARM linkage, slot installation in
the shipped executable, or on-device timing overhead. The ARM cross-compiler
gate was skipped in this environment. A qualified diagnostic must first have
a bounded and safe output plan, target-architecture checks, and independent
review; it must be packaged and deployed only through the documented firmware
ZIP process, never by replacing a device binary over SSH.

## Release block and next evidence

This source baseline also inherits the unresolved v90 shared Bulb cancellation
and deferred timed-capture hazards in issue #251. The branch adds an explicit
failing release-gate test until a provenance-bound fix and lifecycle regression
replace it. This blocks the standard pre-release gate in this checkout; it is
not a universal installer or a provenance-bound check in other checkouts. The
timing work does not fix lag or clear that gate.

When a safe diagnostic candidate is available and the camera is recoverable,
measure individual lookup and write calls in a single owned session, correlate
the log's PID/thread/time with the client request and mode, and preserve
original camera values. Test one advertised write at a time, verify the changed
value using the source-defined conditions, restore the exact original value,
and independently verify restoration. Compare K-1 II with K-3 III and preserve
other vendors' paths. Only then select and test a targeted change. A suspected
library defect additionally requires the repository's clean direct-PC
reproducer before changing libgphoto2.

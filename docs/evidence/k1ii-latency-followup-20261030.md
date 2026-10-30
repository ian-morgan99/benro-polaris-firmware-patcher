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
after the process exited. The local fix checks process identity on each pass
and matches the IPv4/IPv6 LISTEN socket's inode to a descriptor held by that
pgphoto PID. It records the process start time at the initial identity check
and checks it again before accepting readiness. A simulated late exit with an unrelated
listener makes the unmodified v90 script return success; the changed script
rejects it. A simulated 24-second start passes the changed test, while the
original hard-coded 20-second helper fails the same slow-start case. Hung
startup still fails within a short configured test bound.

This is **not a complete camera-readiness guarantee**: the helper does not
verify restart-lock ownership throughout the wait or establish that the
camera accepts controls. The proc reads are not atomic; the process can exit
after a successful check, and start-time tracking begins at the initial
post-launch check. None of these tests
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

`STAGE2_CONFIG_TIMING=1` **and** `STAGE2_CONFIG_TIMING_PORT=<1024..65535>` at
pgphoto process start enable timing of the core
single-widget reads, single-widget writes and full-tree reads crossing the
Stage-2 slots. UDP records contain sequence, PID, thread ID, operation, widget name, raw core
return code and monotonic start/end timestamps; they contain no widget values.
The record is of the **core** return before the existing empty-widget guard,
not necessarily the final result seen by pgphoto. The existing guard emits its
own diagnostic if it rejects a result. Calls internal to the library, the busy
status owner, PTP operations and actual camera setting readback are outside
this probe's visibility.

By default the full-tree slot stays direct to core and no timing socket is
created. Single-widget wrappers check the disabled descriptor without clock or
output calls. Environment configuration is read only during startup. A socket
creation failure leaves timing disabled. The optional socket uses nonblocking
UDP to `127.0.0.1` only, with close-on-exec set. Each record uses a 256-byte
stack buffer; widget names are capped at 64 bytes. The process attempts at most
128 records across all threads, including failed sends. Each send has
`MSG_DONTWAIT | MSG_NOSIGNAL`; failures are dropped without retry. An absent or
slow receiver cannot cause diagnostic disk writes or waiting for delivery.
After the limit is reached, timing clocks and sends stop. Records are lossy;
sequence gaps do not imply missing camera calls. There is no synchronous
stderr write in the timing path; existing control-guard diagnostics remain.

Host tests cover disabled/invalid configuration, socket creation failure,
call counts, arguments, results and errno, real loopback records, missing
receiver, long names, clock failure, and injected EAGAIN/ENOBUFS/EPIPE/EINTR/
ECONNREFUSED sends. Eight concurrent callers verify the shared 128-attempt cap.
Raw core success followed by guard rejection remains distinguishable.

This remains unreleased and unqualified on hardware. Host compilation and the
ARM loader compile/link check do not establish shipped-runtime compatibility,
slot installation or on-device overhead. A future candidate still needs
independent review and the documented firmware ZIP process. No firmware build,
deployment, camera operation, subagent or paid service was used in this follow-up.

## Scoped regression results (2026-10-30 follow-up)

- `test_stage2_config_timing.sh`: PASS.
- `test_stage2_empty_choice_guard.sh`: PASS.
- `test_stage2_settle_config_gate.sh`: PASS, including writes during preview settling.
- `test_stage2_shutter_fallback.sh`: PASS.
- `test_restart_gphoto_launch_lock.sh`: PASS with the socket-ownership fixture.
- `test_restart_gphoto_readiness.sh`: PASS for slow/hung startup, exit, changed
  start time, IPv4/IPv6 ownership, unrelated/non-listening/wrong-port sockets,
  and missing process identity.
- `test_stage2_loader_compile.sh`: PASS using the installed
  `arm-linux-gnueabi-gcc` 13.3.0; produced an ARM EABI5 shared object. Nothing installed.

Impact: this is shared patcher/loader code, not a Pentax-only path. No generic
PTP2 code, opcode, property, model gate or camera state transition changes.
All vendors can use the optional timing; the host tests check preservation of
the wrapped API contract. Readiness now requires the actual daemon's listener
for every camera model. No physical/non-Pentax qualification was performed.
The full release gate was not run or claimed green in this scoped follow-up.

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

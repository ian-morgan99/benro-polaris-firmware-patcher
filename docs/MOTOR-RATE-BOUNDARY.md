# Polaris motor-rate boundary

Status: host-only preparation; no firmware patch, live command, or hardware
qualification.

The exact `.73` `polestar_app` disassembly gives one useful static fact: the
existing `SP_GimbalSetAxsi` helper constructs a seven-byte frame beginning
`AC 4A`, followed by an axis byte and a little-endian IEEE-754 float. The
helper is not directly called by the observed app dispatcher. The following
remain unknown and must be established from the gimbal MCU source/firmware or
a controlled protocol capture:

- dispatcher route and exact MCU command identity;
- axis numbering, sign, units, and conversion to motor steps/deg/s;
- whether zero rate holds torque or releases it;
- STOP priority, acknowledgement/reply, watchdog and disconnect behaviour;
- forwarding through the 403/413 gimbal path and supported firmware IDs.

The companion research record identifies the MCU image used by the current
`.73` package as `polaris413_2.0.0.22.bin` (SHA-256
`34d3f4186185c541adb9c8e57b3e2ec13e402dfb4bb3e9b2262cbf03f1a5c112`) and
reports a `J`/`0x4A` handler at `0x800501c`. A new fail-closed static check of
that exact image confirms the local float sequence: the handler reads the
axis-selected input at packet-state offset `0x0e`, multiplies it by a
per-axis state value at `0x21c`, then by the literal `0.0002770000137`, and
divides by `1000.0`. The per-axis records have a `0x64`-byte stride. This is
stronger than the earlier approximate note, but it still does not assign
degrees/second units: the timer cadence, scale origin, state ownership and
physical conversion remain open. State `3` also forwards the input as message
`0x25`, so the complete 403/413/astro routing still needs qualification.

`tools/polaris_gimbal_rate_static.py` reproduces these checks against the
exact hash and emits a JSON evidence record. It remains analysis-only: no
binary is written and no rate frame is sent.

## Static `.73` discovery: the existing jog path

Read-only disassembly of the exact `.73` application adds a separate, more
concrete fact. `SP_MsgGimbalCmdFromAppProc` dispatches application codes
`513`--`549`; the currently observed jump-table default slots are 515, 516,
518, 523, 527 and 528. These are candidates for investigation only, not an
approved new command ID. The existing fast jog controls are dispatched as
follows:

| app control | axis passed to `SP_GimbalUartAdjSpeed` | MCU frame |
|---:|---:|---|
| 513 (`HADJ`) | 2 | `AC 41 <axis> <signed little-endian int16 speed>` |
| 514 (`VADJ`) | 1 | same five-byte shape |
| 521 (`RADJ`) | 3 | same five-byte shape |

`SP_GimbalUartAdjSpeed` writes the `AC 41` prefix, axis byte and signed
16-bit speed, then queues a five-byte message. The observed application
contract clips fast-jog magnitudes to roughly 100--2500 and repeats them while
the hold is leased; zero is used as the fast-jog stop. `polaris-jog.c` already
implements the app-control side with a server-owned 400 ms lease and 50 ms
repeat cadence.

This is useful for controlled jog/deadman experiments, but it is not the
requested independent tracking-rate primitive. It does not establish physical
units, the sign convention after the M1/M2/M3 mapping, steady-rate accuracy,
MCU acknowledgement, or the behaviour of a stopped/disconnected link. The
`AC 4A` float helper remains unapproved for live use because the application
dispatcher has no direct caller for it. `tools/polaris_rate_protocol.py` can
now parse and fault-test both shapes, but still opens no socket and is not
bundled.

`tools/polaris_rate_protocol.py` is deliberately only a host-side parser and
safety simulator. It exercises the known frame shape, rejects malformed or
non-finite values, enforces a caller-supplied maximum rate and acceleration,
and forces all simulated axes to zero on watchdog expiry or link disconnect.
It opens no socket and is not copied into the Polaris runtime bundle.

## Independent host-side reference: the shared SLOW ladder

The public MIT project [ogecko/alpaca-benro-polaris](https://github.com/ogecko/alpaca-benro-polaris/tree/2295f6e9835370e9f3e44d5aad4ddcc730e40ba9)
provides an independent host-side design and published hardware measurements
for the existing app controls. Its `SpeedCoordinator` treats 532/533/534 as
a shared-level SLOW ladder, mixes adjacent rates by time-sharing, keeps a
holding axis away from state 0, and refreshes 513/514/521 FAST commands every
50 ms. The recorded SLOW values are approximately:

| level | state 1 (deg/s) | state 2 (deg/s) |
|---:|---:|---:|
| 1 | 0.0059 | 0.0119 |
| 2 | 0.0179 | 0.0295 |
| 3 | 0.0474 | 0.0593 |
| 4 | 0.0896 | 0.1193 |
| 5 | 0.2088 | 0.2402 |

This is useful corroboration and a design reference, not evidence that this
head has the same calibration. In particular, sidereal tracking is about
`0.004178 deg/s`, below the reference level-1 state-1 rate. A controller must
therefore mix opposite state-1 directions for a low positive/negative rate or
an engaged zero-rate hold; it must never use state 0 as the low-rate substitute.
The 50 ms FAST refresh and donor calibration are also not a substitute for
proving this firmware's watchdog and physical units.

`container/astro/polaris-rate-plan.c` is the first native-C implementation of
that *planning* idea. It is deliberately pure: it emits no frame and is not
linked into `polaris-httpd`. It validates finite rates, chooses one common
SLOW level, returns adjacent points plus a duty cycle, rejects rates above the
reference SLOW envelope, and distinguishes an engaged zero-rate hold from a
stop. `test_rate_plan.c` exercises the planner offline. The remaining runtime
work is a clock-driven dwell/PWM scheduler, exact target-head calibration, and
the stop/watchdog/link-loss contract. None of that is authorised to command a
motor yet.

No donor source was copied. If any donor code is later reused, retain its MIT
notice and the immutable source revision in the corresponding provenance.

The next safe gate is to replace the unknowns with an exact MCU-backed
contract, then run the same fault cases against a protocol simulator: bad
length/prefix/axis, NaN/Inf, over-rate, acceleration step, stale update,
disconnect, STOP ordering, and malformed acknowledgements. Only after that
may a dry-run device wrapper be considered. The frame watcher continues to
log rotation and drift but sends no rate command.

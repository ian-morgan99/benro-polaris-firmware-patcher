# Issue #3: independent per-axis rate control

Status: design and qualification contract only. **UNQUALIFIED; no firmware
patch or live command is authorised.** This document is the reviewed gate for
the implementation tracked in patcher issue [#240](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/240).

## Purpose

The Astro plate-solve loop needs a way to compensate measured drift without
turning every correction into a large pointing slew. The desired primitive is
an independently commanded, signed, bounded rate for each physical gimbal
axis, with an explicit stop and a fail-closed watchdog.

This is deliberately separate from the existing 513/514/521 fast-jog
controls. Those controls are a hold-to-move user-interface path. Static
analysis shows that they become `AC 41` signed-int16 jog messages, but that
does not prove that they can hold a calibrated sidereal or drift-compensation
rate.

## Candidate contract

The `.73` application contains an `SP_GimbalSetAxsi` helper that constructs:

```text
AC 4A <axis:u8> <rate:little-endian IEEE-754 float>
```

The helper's route, receiver, units, axis mapping and response semantics are
not all established at the application boundary. The matching `.73`
`polaris413_2.0.0.22.bin` MCU payload is present and its historical analysis
identifies the `J` handler at `0x800501c`, but the application dispatcher has
no direct call to this helper. The shape and MCU lead are therefore not yet an
approved end-to-end wire contract. The implementation must not send it until
every unknown below has been resolved against the exact application and gimbal
binaries.

The `.73` dispatcher covers codes 513--549. Read-only jump-table inspection
currently shows default paths at 515, 516, 518, 523, 527 and 528. Those slots
must be checked against every other parser/reply table before one can be
considered for a new command; no command ID is selected by this specification.

Required semantics, once proven:

- axis identity and sign are explicit and stable after M3 rotation;
- rate units and conversion to motor steps are known;
- finite values only, with a firmware and host maximum;
- acceleration/rate changes are bounded;
- zero means a documented safe stop that preserves the required load-holding
  behaviour;
- stop has priority over a queued rate;
- stale commands, link loss and process exit stop all axes;
- acknowledgements or a positive state readback distinguish accepted commands
  from merely queued bytes;
- the command is mode-gated, lease-bound and unavailable to normal K-3 III
  capture operation.

## Measurement envelope (not a public command limit)

The physical test must characterize more than the nominal Astro range. The
following values are acceptance-test points, not permission to expose an
unbounded rate to the plate-solve loop:

| Test | Requested rate | Required observation |
|---|---:|---|
| simultaneous tracking case | M1 `-0.006`, M2 `0`, M3 `+0.2081` deg/s | independent measured rates; stationary axes remain within 1 arcsec |
| slow single-axis limit | M1 `+/-0.0001` deg/s, then lower if stable | measured rate and M2/M3 within 1 arcsec |
| fast single-axis characterization | M1 `+/-9.0` deg/s, or the measured safe limit | no cross-axis movement beyond 10 arcsec, with an immediate tested stop |

The fast point is a bench characterization gate only. It must not be used by
the Astro controller until motor load, acceleration, end-stop and stop-time
limits are measured. The product-facing envelope remains unset until the MCU
units and the physical matrix are known. A result that passes position deltas
but cannot prove acknowledgement, zero-rate hold and disconnect behaviour is
not a pass.

The current MCU research reports a historical step relationship of roughly
`rate * 960 * 0.000277 / 1000` per tick for the `J` path. This is a reverse-
engineered implementation lead, not a calibrated degrees/second contract;
the conversion must be measured on the target build before it is exposed as a
public rate value.

## Evidence gates

1. Pin the exact app and gimbal payload hashes and prove the symbol/disassembly
   facts for each supported firmware ID.
2. Identify the dispatcher route and the receiving MCU parser, including packet
   checksum/length, reply, units, sign, tick cadence and stop semantics.
3. Implement a host protocol parser and fault-injection simulator. It must
   reject bad prefix/length/axis, NaN/Inf, over-rate, over-acceleration, stale
   updates and malformed acknowledgements, and must force zero on watchdog and
   disconnect.
4. Run a no-camera bench qualification with the exact firmware, a physical
   stop/reconnect test and a measured rate/axis-sign matrix.
5. Run Astro-only drift correction with a hard disable switch, bounded commands,
   logged telemetry and a recovery test. Prove that normal K-3 III capture
   remains byte-for-byte source-compatible and behaviourally unchanged.

Until all five gates pass, the plate solver may report drift and use bounded
   positional correction where already qualified, but it must not adjust motor
rate.

## Native-C host route assessed against an independent reference

The public MIT project [ogecko/alpaca-benro-polaris](https://github.com/ogecko/alpaca-benro-polaris/tree/2295f6e9835370e9f3e44d5aad4ddcc730e40ba9)
at commit `2295f6e9835370e9f3e44d5aad4ddcc730e40ba9` provides a useful
independent design reference for the already observed 532/533/534 SLOW and
513/514/521 FAST paths. It reports a shared SLOW level, per-axis direction and
state, time-sharing between adjacent rungs, no state-0 use while holding, and
50 ms FAST refresh. Its reported SLOW table puts sidereal speed below the
lowest single SLOW rung, so a low-rate controller must time-share opposite
state-1 directions rather than pretending that a level is a continuous rate.

The patcher now contains `container/astro/polaris-rate-plan.c`, a pure native-C
planner based on that *reference* table. It has no socket or motor side effect,
selects a common level for all active SLOW axes, returns the two points and
duty needed for each requested average, and represents zero-rate hold without
state 0. `test_rate_plan.c` is an offline C test. A companion pure scheduler
(`polaris-rate-scheduler.c`) enforces a 75 ms minimum dwell and produces
logical SLOW transitions or an explicit logical STOP; it deliberately does not
serialize frames. `test_rate_scheduler.c` is an offline C test. This is a
controlled design step, not an implementation of issue #240's unrouted `AC
4A` helper and not a hardware qualification. `polaris-rate-wire.c` now formats
the known 532/533/534 SLOW application controls without calling
`polaris-link`, and `polaris-rate-fake-head.c` tests canonical payloads,
explicit STOP ordering, stale timestamps and the host-side lease timeout.
These are host-only seams; neither is linked into `polaris-httpd`, so normal
K-3 III capture and the current Astro mode are unchanged.

Before this planner can be wired to Astro drift correction, the remaining gates
are:

1. remeasure the SLOW table on the exact target firmware, axis, load and
   battery conditions;
2. implement and test a clock-driven dwell/PWM scheduler that never changes a
   SLOW point before the target MCU's measured minimum dwell;
3. replace the host fake-head assumptions with the target MCU's proven stop,
   link-loss, process-exit and reconnect behavior, then repeat the tests on
   supervised hardware;
4. decide whether the J/`AC 4A` route is preferable after its units,
   dispatcher, acknowledgement, zero-hold and watchdog semantics are proven;
5. only then expose a feature-gated controller to the Astro plate-solve loop.

The donor measurements and algorithm are evidence to reproduce, not target
hardware facts. No donor source was copied; any future reuse must preserve its
MIT notice and immutable revision.

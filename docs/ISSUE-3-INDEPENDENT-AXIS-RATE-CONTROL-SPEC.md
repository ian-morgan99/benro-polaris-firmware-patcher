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

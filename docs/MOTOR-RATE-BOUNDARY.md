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

## Static `.73` discovery: the existing jog path

Read-only disassembly of the exact `.73` application adds a separate, more
concrete fact. `SP_MsgGimbalCmdFromAppProc` dispatches the existing fast jog
controls as follows:

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
`AC 4A` float helper remains unapproved for live use because its dispatcher
route is still unknown. `tools/polaris_rate_protocol.py` can now parse and
fault-test both shapes, but still opens no socket and is not bundled.

`tools/polaris_rate_protocol.py` is deliberately only a host-side parser and
safety simulator. It exercises the known frame shape, rejects malformed or
non-finite values, enforces a caller-supplied maximum rate and acceleration,
and forces all simulated axes to zero on watchdog expiry or link disconnect.
It opens no socket and is not copied into the Polaris runtime bundle.

The next safe gate is to replace the unknowns with an exact MCU-backed
contract, then run the same fault cases against a protocol simulator: bad
length/prefix/axis, NaN/Inf, over-rate, acceleration step, stale update,
disconnect, STOP ordering, and malformed acknowledgements. Only after that
may a dry-run device wrapper be considered. The frame watcher continues to
log rotation and drift but sends no rate command.

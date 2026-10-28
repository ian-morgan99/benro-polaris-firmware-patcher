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

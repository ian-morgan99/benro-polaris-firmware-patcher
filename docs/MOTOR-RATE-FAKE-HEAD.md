# Motor-rate fake-head test

Status: host-only safety model; not a firmware emulator and not hardware
qualification.

`container/astro/polaris-rate-fake-head.c` is the next test seam after the
dry-run formatter. It accepts only the known 532/533/534 SLOW payloads,
validates the opcode, subsystem type, canonical argument string, direction,
rung and state, and records whether each logical axis is active. It rejects an
unknown opcode, malformed payload, wrong subsystem, stale timestamp, repeated
STOP, or STOP for an inactive axis.

The fake head also models the host-side 400 ms lease that a future live rate
controller must enforce. `polaris_rate_fake_head_tick()` stops stale active
axes. This must not be read as proof that the real MCU has the same watchdog:
the target's acknowledgement, disconnect, timeout and physical stop behaviour
remain unknown and must be tested separately.

The test composes the native planner, scheduler, wire formatter and fake head:

```sh
cc -O2 -std=gnu11 -Wall -Wextra -Werror \
  container/astro/polaris-rate-plan.c \
  container/astro/polaris-rate-scheduler.c \
  container/astro/polaris-rate-wire.c \
  container/astro/polaris-rate-fake-head.c \
  container/astro/test_rate_fake_head.c \
  -o /tmp/polaris_test_rate_fake_head -lm
/tmp/polaris_test_rate_fake_head
```

This still has no `polaris-link` call and is not compiled into the Astro
runtime. The next live-enablement gate remains an exact target-firmware
contract, target-head calibration, and physical no-camera stop/reconnect/rate
qualification. The normal K-3 III capture path is untouched.

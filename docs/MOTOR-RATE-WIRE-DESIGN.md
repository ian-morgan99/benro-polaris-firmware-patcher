# Motor-rate wire seam

Status: host-only dry-run preparation. It is not linked into `polaris-httpd`,
does not call `polaris-link`, and cannot command a Polaris head.

`container/astro/polaris-rate-wire.c` translates a logical scheduler command
into the already observed application SLOW controls:

| logical axis | application opcode | payload |
|---|---:|---|
| pan / M1 | 532 | `key:<0|1>;state:<0|1|2>;level:<1..5>;` |
| tilt / M2 | 533 | same |
| rotation / M3 | 534 | same |

SLOW commands retain state 1 or 2. A logical STOP uses the retained active
point's key and level and emits state 0. A missing/invalid point, unknown axis,
invalid command kind, or state 0 used as a SLOW run point is rejected. This is a
fail-closed formatter, not evidence that the target MCU's units, direction,
acknowledgement, watchdog, or physical stop behaviour are correct.

`container/astro/test_rate_wire.c` exercises the three-axis scheduler output,
opcode mapping, payload shape, STOP conversion, and rejection paths. It runs
entirely on the host:

```sh
cc -O2 -std=gnu11 -Wall -Wextra -Werror \
  container/astro/polaris-rate-plan.c \
  container/astro/polaris-rate-scheduler.c \
  container/astro/polaris-rate-wire.c \
  container/astro/test_rate_wire.c \
  -o /tmp/polaris_test_rate_wire -lm
/tmp/polaris_test_rate_wire
```

This seam intentionally does not implement the unresolved `AC 4A` float path.
Before any live connection, the remaining gates are an exact target-firmware
contract, a fake-head/fault simulator, explicit disconnect and STOP ordering
tests, target-head SLOW calibration, and no-camera physical stop/reconnect/rate
qualification. The normal K-3 III capture path and current Astro tracking API
remain unchanged.

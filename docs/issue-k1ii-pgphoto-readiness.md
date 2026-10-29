# K-1 II pgphoto readiness and slow-control investigation

Issue: [benro-polaris-firmware-patcher #253](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/253)

## Finding

On 2026-10-29, the attached K-1 Mark II was enumerated as `25fb:0183` and
the Polaris was running v89:

```text
FwVer:6.0.0.54.89
libgphoto2=63a894b0821a510fc40244c5cc4ef84a5220a91c
patcher=613b9d140299add55caee24c0a3ece4e46fa0a42
USB identity=1-1.2|25fb:0183|1:5
```

Control requests were slow because the pgphoto service was not staying ready,
not because the logs identified a slow K-1 II value-setting opcode. The logs
showed:

```text
[restart_gphoto] pgphoto running (PID ...)
[restart_gphoto] FAIL: pgphoto stayed alive but port 8080 did not become ready
[camera-usb] quarantined identity ... stable ... but bounded rebind failed
```

The process continued through K-1 II vendor enable, `gp_camera_init`, and the
large configuration enumeration for roughly 40 seconds. The old restart
helper stopped waiting after 20 seconds, falsely classified this progressing
initialisation as a failed rebind, and allowed the supervisor/watchdog retry
cycle to interrupt it. During the observation there was no TCP/8080 listener.

The v87 and v89 packaged `camera_usb_supervisor.sh` files are identical. This
is therefore a Polaris restart/readiness defect. It is not, from this evidence,
a reason to change the Pentax libgphoto2 setting handlers.

## Fix

`container/ondisk/restart_gphoto.sh` now waits up to 90 seconds by default for
the actual 8080 listener. The wait remains fail-closed and event-driven:

- it returns immediately when the listener appears;
- it fails if pgphoto exits or the bounded window expires;
- the window can be overridden with `OPENPOLARIS_PGPHOTO_START_WAIT_MAX` for
  deterministic tests or a future measured deployment configuration.

The change avoids an arbitrary post-start sleep. It gives the K-1 II's measured
initialisation time enough room to complete while retaining a hard upper bound.

## Regression coverage

`container/test_restart_gphoto_readiness.sh` proves both sides of the contract:

1. a simulated slow init publishes 8080 after three seconds and succeeds;
2. a simulated hung init never publishes 8080 and fails within the configured
   five-second test bound.

The existing launch-lock, supervisor debounce, quarantine, and restart-budget
tests remain required. Hardware qualification must still confirm K-1 II and
K-3 III startup, one stable pgphoto session, control setting latency, preview,
and ordinary capture after a clean candidate deployment.

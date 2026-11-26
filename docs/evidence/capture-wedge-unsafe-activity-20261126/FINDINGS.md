# Capture wedge after a failed bulb: our own admission gate blocks every later capture, with no clearing path

Measured 2026-11-26 on the K-1 II rig (v118, `o-v18a`), camera enumerated at boot as `1-1.2`, `25fb:0183`.

## What happened, in order

1. **Timed bulb failed** (`264 state:1;bulb:10;c:-1;`). Clog:
   ```text
   ---bulb11 10000--- /app/sd/normal/SP_0047.jpg
   capture bulb Image ret 0
   captureBulbImage ret -110  p:   ;
   ```
   The exposure was issued, retrieval failed, and `SP_0047.jpg` never appeared (`ls /app/sd/normal` still ended at SP_0046).

2. **Every subsequent capture was then refused**, including a plain non-bulb capture, which returned `state:-1005` in 0.2 s:
   ```text
   [pentax] capture=3 boundary=camlib-enter transfer=0 recovery=1 output_pending=1
   [pentax-recovery] capture=3 path=recovery-probe reason=unsafe-activity ptp=0x2001 size=576
       field32=0x00000001 field36=0x00000001 field104=0x0000000e unsafe
   Camera recovery probe refused capture (PTP 0x2001, size 576, fields +32=0x00000001
       +36=0x00000001 +104=0x0000000e, unsafe-mask=0x00109a03).
   ERROR: Could not capture image.
   ```

3. **The supervisor reported the rig healthy throughout.** `[camera-usb] supervisor ready; identity=1-1.2|25fb:0183|1:3`, and `probe-config-gate.py` returned *"every parameter code answered with a real value list"* with **0 refusals** — while capture was completely dead. This is exactly issue **#182**: the health model is USB-identity-only, so a capture-wedged daemon is invisible.

## Why the existing release path cannot clear it

`pentax_admission_apply_output_obligation()` (camlibs/ptp2/library.c:6775) releases a latched
`capture_output_pending` only when the camera positively reports idle:

```c
if (camera_reason != PENTAX_ADMISSION_BLOCK_NONE ||
    !params->pentax.capture_output_pending)
        return camera_reason;          /* <-- bails out here */
```

Here `camera_reason` is `PENTAX_ADMISSION_BLOCK_UNSAFE_ACTIVITY`, not `NONE`, so the function returns
before ever reaching `pentax_output_obligation_releasable()`. The fail-closed branch is then taken and
the refusal repeats forever. The comment above that function describes the intent precisely — *"one
timed-out capture cannot lock every later shutter for the life of the process"* — and this is that
failure mode arriving by a different route: the camera reports unsafe activity rather than an idle body,
so the release condition can never be satisfied.

`pentax_admission_is_admissible()` (pentax-utils.c:319) has the same shape:
`return reason == PENTAX_ADMISSION_BLOCK_NONE && !capture_output_pending;`

## Recovery: reboot works, killing pgphoto does not

- **Reboot cleared it.** After a clean boot: `state:1` -> `state:4` at 9.2 s and `SP_0047.jpg` (326,039 B)
  landed. Held bulb then succeeded twice: `['1','4','0']` and `['1','4','0']`.
- **Killing pgphoto did not restore service.** `kill <pgphoto>` produced a new PID (1057 -> 31422) with
  `gp_camera_init ret 0`, but capture then returned `state:-1` in 0.0 s and **no capture lines reached
  pgphoto at all** — the failure came from polestar_app, because the app<->pgphoto IPC link was broken by
  the manual kill. So the obvious operator remedy makes things worse; only a reboot recovers.

## Held bulb vs timed bulb on a clean boot

| request | result |
|---|---|
| plain capture `state:1;c:-1;` | `1 -> 4`, file written |
| held bulb `state:1;bulb:0;c:-1;` | `1 -> 4 -> 0`, twice |
| timed bulb `state:1;bulb:10;c:-1;` | `1 -> -6` at 6.05 s, no file |

The `-6` has an explicit cause in Clog:
```text
Pentax Bulb action requires a readable B, lens-B or Astro exposure mode.
Failed to set new configuration value 1 for configuration entry bulb.
----CAPTURE bulb start  -6
```
`print_widget` showed `exposure-mode=Manual; exposure-mode-raw=8`. The guard at library.c:7168 accepts only
B, lens-B or Astro. **Held bulb succeeds from Manual while timed bulb is refused from Manual** — that
asymmetry is the bug's user-visible shape. There is no protocol command to set exposure mode (canary-probe.py
exposes 260 EV and 261 shutter only), so this cannot be verified remotely: the dial must physically be on B.

## Corrections to earlier claims made today

- "Both bulb paths fail on v118" was **wrong**. Both failures were observed while the rig was already
  wedged by the first failed timed bulb, so they measured the wedge, not bulb itself. On a clean boot held
  bulb passes; only timed bulb fails, and with a different code (`-6`, not `-1005`).
- My rig presence check `lsusb | grep -c pentax` was **wrong**. This busybox `lsusb` prints only
  `Bus NNN Device NNN: ID vendor:product` with no product string, so it returns 0 even when the camera is
  present. The correct check is `lsusb | grep -c 25fb`, or sysfs
  `/sys/bus/usb/devices/*/idProduct`. Every "camera absent" reading taken with the pentax grep was invalid;
  the camera had in fact enumerated at boot (`authorized=1`).
- `scripts/bulb-timed.py` does not exist. The real scripts are `repro-app-bulb-request.py` (the app's exact
  timed request) and `probe-b-list-and-held-bulb.py` (held bulb).

## What is needed

The gate is correct to be fail-closed — a double publication is worse than a refusal. But a state that can
never satisfy the release condition, with no operator-recoverable exit short of reboot, is a dead end. The
gap is a bounded path out: after N consecutive refusals on the same latched obligation, either re-query the
camera for whether it still owes an output and clear on any explicit idle/unsafe-clear reading, or surface a
diagnostic that names the wedge and the required action instead of returning a bare `-1005`.

# shutter-2026-09-16 — log capture analysis

Date: 2026-09-16
Camera intent: Pentax shutter test (directory name `shutter-2026-09-16`)
Files captured: `Clog.txt`, `Clog-0102.txt`, `Mlog.txt`

## Verdict

**This capture is NOT a shutter/capture result.** The camera stack never
reached PTP. Both Clogs contain **only** repeated `[stage2] init` loader
banners with zero PTP/camera traffic — the documented "pgphoto restart loop,
camera not on USB bus" signature (see `.github/skills/polaris-debugging/SKILL.md`
§7: *"a fitted-but-off or loose K-1 II produces a pgphoto restart loop
(repeated `[stage2] init` blocks in Clog) with no PTP traffic at all."*).

## What the logs show

### Clog.txt — 84 repeated `[stage2] init` blocks, zero PTP traffic

Every block is the identical loader-init sequence:

```text
[stage2] mmap slot page @0x30000000 ok (fresh RW anon page, 4096 B)
[stage2] init: stubbed 64 slots (fail-closed baseline; slot base 0x30000000)
[stage2] on-disk loader: CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34 IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2
[stage2] dlopen core via abs /app/lib/stage2/libgphoto2.so.6
[stage2] dlopen core ok
[stage2] dlopen port via abs /app/lib/stage2/libgphoto2_port.so.12
[stage2] dlopen port ok
[stage2] preview-backoff: gp_camera_capture_preview slot -> shim (real core fn cached for pass-through)
[stage2] storage: gp_camera_init slot -> shim (real core fn cached for pass-through)
[stage2] capturetarget: gp_camera_set_config slot -> shim (real core fn cached for pass-through)
[stage2] capturetarget: gp_camera_set_single_config slot -> shim (real core fn cached for pass-through)
[stage2] resolved 64/64
[stage2] slots filled 64/64
```

- **84** `slots filled 64/64` blocks in `Clog.txt` (one per pgphoto launch).
- **Zero** PTP/camera lines: no `state:`, no `captureImage`, no `usb`/`25fb`,
  no `get_single_config`, no `preview-backoff: N consecutive failures`, no
  FATAL / `ret -` / `state:-`.

### Clog-0102.txt — same signature, 86 blocks

Identical loader-init sequence; **86** `slots filled 64/64` blocks. Same zero
PTP/camera traffic. This is the rotated/numbered Clog (the `restart_gphoto`
append target rotates to numbered files). Both files independently show the
restart loop.

### Mlog.txt — app-side keepalive churn, no camera activity

```text
[00:12:04:899] SOCKET_ACCEPT(201) [id=28 192.168.0.4:42628] from [1] s_u32ClientNum[2]
[00:12:04:899] SP_sendMsg success; key[1004],type[5],code[1034],val[1]
[00:12:04:899] EventMsgProc[2679]:SP_EVENT_APP_CONNECT
[00:12:04:899] SOCKET_OPEN(201) [id=28] start
[00:12:04:899] ERROR msg_rcv_from_app_process[65]: rcv msg from App[28]:type:0;code:266;val:
[00:12:04:899] SOCKET_CLOSE(201) [id=28] s_u32ClientNum[1]
[00:12:04:899] ERROR SP_ClientCtxDel[392]:SP_ClientCtxDel:not find this is id[28]
[00:12:11:001] GimbalUartRxMsgProcTask[398]:Tempa509ca361f0000285a ;
[00:12:11:001] SP_SendMsgToApp success;type[2],code[525],val[Tempa509ca361f0000285a ;]
[00:12:35:911] SOCKET_ACCEPT(201) [id=29 192.168.0.4:51094] from [1] s_u32ClientNum[2]
... (repeat of the same connect → code:266 → close → SP_ClientCtxDel-not-find cycle, id=29)
```

- Two app connect cycles ~31 s apart (`id=28` at 00:12:04, `id=29` at
  00:12:35). Each is the keepalive ping `code:266` (the `1&266&0&#` keepalive)
  followed by an immediate `SOCKET_CLOSE` and `SP_ClientCtxDel not find this
  is id` — app-side connect/close churn, **not** camera activity.
- `code:525` / `Tempa509ca361f0000285a` = gimbal temperature push to the app
  (normal telemetry).
- No `SP_SET_SHUTTER`, no `shutterString`, no capture state machine, no
  camera-init lines in Mlog.

## Interpretation

| Claim | Status |
|---|---|
| A shutter/capture was dispatched and completed | **NOT PROVEN** — no `state:`/`captureImage`/`SP_SET_SHUTTER` anywhere |
| pgphoto is in a restart loop | **YES** — 84 (Clog.txt) + 86 (Clog-0102.txt) repeated `[stage2] init` blocks, each ending `slots filled 64/64`, with no PTP traffic between them |
| Camera was on the USB bus and reached PTP | **NO** — zero `usb`/`25fb`/`get_single_config`/`state:` lines; matches the documented "camera not on USB bus / fitted-but-off or loose" restart-loop signature |
| App keepalive was active | **YES** — `code:266` ping + connect/close churn in Mlog (two cycles ~31 s apart) |

This is the **pgphoto restart loop with no camera on the USB bus**, not a
shutter result. The loader itself is healthy (every block reaches
`slots filled 64/64`, `dlopen core ok`, `dlopen port ok`) — the failure is
that pgphoto never gets past init to PTP because the camera is not
enumerated on the USB bus (fitted-but-off, loose cable, or camera powered
off).

## What this does NOT prove

- ❌ That a shutter was set or a capture ran. No `SP_SET_SHUTTER`, no
  `shutterString`, no `state:` machine, no `captureImage`.
- ❌ That the camera is healthy or unhealthy at PTP — it never reached PTP.
- ❌ That the restart loop is a loader bug — every block completes
  `slots filled 64/64`; the loop is the watchdog relaunching pgphoto because
  it exits at init (no camera to attach).

## Next boundary (do not skip)

1. **Confirm the camera is on the USB bus before any shutter test:**
   `lsusb | grep 25fb` must show the Pentax (`25fb:0189` K-3 III /
   `25fb:0183` K-1 II). Empty = "no camera" — check power + cable seat first.
2. **Prove it is the gimbal** before trusting any log: `nmcli … | grep
   48:E7:DA` + `ip route get 192.168.0.1` → wifi dev + `cat /app/FwVer`.
3. **Only after `lsusb` shows the camera**, re-run the shutter test and
   capture Clog/Mlog. A valid shutter result needs a `state:` machine
   (e.g. `1 -> 4 -> 2 -> 3 -> 5`) or an explicit `SP_SET_SHUTTER` /
   `shutterString` line, not just loader banners.
4. **Verify the backoff engaged** before trusting preview: grep Clog for
   `[stage2] preview-backoff: N consecutive failures (last ret=...)`. The
   init-time `slot -> shim` line only means the wrapper is installed, NOT
   that it fired.

## Cross-references

- `.github/skills/polaris-debugging/SKILL.md` §7 (K-1 II deployment hazards;
  restart-loop signature), Quick reference (`lsusb | grep 25fb`, prove-gimbal,
  preview-backoff verification).
- `docs/evidence/pentax82-layer-c-2026-09-15.md` — the last capture that DID
  reach PTP (camera info / live-view / capture states), for contrast.
- `STATE.md` § Live device + § Session log; `docs/RUN-JOURNAL.md`.

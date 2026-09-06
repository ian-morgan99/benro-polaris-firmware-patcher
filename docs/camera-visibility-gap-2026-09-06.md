# Gap — camera visibility after SD-card firmware install (2026-09-06)

> **Status:** OPEN (workaround found, root cause of the PTP config loop not yet closed).
> **Severity:** MEDIUM — camera is intermittently invisible to the app; capture fails with `-1002`.
> **Device:** Benro Polaris gimbal @ `root@192.168.0.1`, Pentax K-1 Mark II (USB PTP, `25fb:0183`).
> **Related:** [STATE.md](../STATE.md), [silent-fwpkt-reject-postmortem.md](silent-fwpkt-reject-postmortem.md).

## What happened (timeline, 2026-09-06)

1. **~15:32** — SD card (`/dev/sdb1`, FAT32, mounted rw on the PC) prepared:
   `OmsPkt.zip` removed, `FwPkt.zip` replaced with the latest build
   (md5 `e6fe0c9cfac5c08fedc72ebb40b474e6`), and pre-extracted to
   `/app/sd/FwPkt/{camera,gimbal}/` per Path A (autonomous boot install).
2. **~15:37** — card inserted, gimbal booted. Firmware install **succeeded**:
   - `/app/sd/FwPkt/` consumed and removed by the device.
   - `/app/bin/` timestamps = Sep 5 19:28–19:29 (matches the new `appfs.ubifs`).
   - Note: `/app/FwVer` still reads `4.0.0.32;date:2025.05.09` — that file lives
     in a partition this package does not touch, so it is **stale metadata**,
     not the running version. Gimbal MCU reports `FwVer 2.0.0.22` (matches the
     `polaris403/413_2.0.0.22.bin` in the package).
   - Leftover: the old `FwPkt.zip` remains on the card (device only removes the
     extracted dir, not the zip).
3. **~15:46:21** — first camera probe after boot: `state:-53`
   (`manufacturer:none;model:none`). The `checkGphotoTask` watchdog logged
   `pgphoto is exit, reboot it`. This is a **boot race**: gphoto2 probed before
   PTP was ready.
4. **~15:47:07** — recovery: `state:1`,
   `manufacturer:ricoh imaging company, ltd.;model:pentax k-1 mark ii;storage:2;photoFormat:2`,
   `camera_connected_to_app connected:1`. Camera visible for ~20 s.
5. **~15:49:28** — user switched the camera's memory card (to card 1).
   `SP_MakeNormalPhoto: SP_PHOTO_STA_RECODING, camera disconnect` →
   app reports `state:-1002`, then "no camera detected".
6. **~15:49–15:53** — gphoto process (PID 427, `/app/lib/stage2/pgphoto.stage2ondisk`)
   stuck in a repeating `gp_camera_get_single_config ... failed: -2` loop
   (~every 5 s). PTP link is alive (USB device `1-1.2` still enumerated,
   `authorized=1`) but config queries fail, and **no fresh code-286 state
   report reaches the app**, so the app keeps showing "no camera".
7. **~15:53** — user switched camera format to JPG; no change in the loop.

## Bugs found while debugging

### Bug 1 (HIGH) — `restart_gphoto` kills the wrong path

`/app/restart_gphoto`:

```sh
pkill /app/bin/pgphoto
nohup /app/bin/pgphoto >> /app/Clog.txt &
```

But the running process is `/app/lib/stage2/pgphoto.stage2ondisk` (the stage-2
on-disk loader), so `pkill /app/bin/pgphoto` matches nothing. The old instance
survives, keeps port 8080, and the new instance dies with
`bind(8080) failed: Address already in use`. **The restart script is a no-op
for the kill step.** Workaround used: `kill <pid>` directly, then run the
script (or start the process manually).

### Bug 2 (MEDIUM) — stale PTP session after camera-side card switch

After killing the stuck instance and restarting, gphoto logs:

```
Pentax session already open from a previous connection; observing camera state.
Pentax init stage vendor enable succeeded; function flags 0x00000003.
```

then falls back into the `get_single_config failed: -2` loop. The Pentax holds
a PTP session from the previous connection (the card switch dropped the camera
mid-session), and the new gphoto instance only *observes* it instead of taking
ownership — so config reads fail. **Open question:** does a full camera power
cycle (or USB re-plug) clear the stale session? Not yet tested.

### Bug 3 (LOW) — `get_single_config failed: -2` even on a healthy connection

The `-2` failures also appear right after successful init (15:47, when the
camera was visible). Some config widgets (capturetarget, shutter, fNum, ev,
autofocusdrive) fail with `-2` while others succeed. Non-fatal for
connectivity, but `SP_SET_FNUM FAIL`, `fNumString index error`, and
`ev index error` follow from it.

### Bug 4 (LOW) — double gphoto instances at boot

At boot, two `pgphoto.stage2ondisk` processes ran simultaneously (PIDs 250 and
427); the second failed to bind 8080. Related to Bug 1: nothing prevents a
second instance from starting while the first holds the port.

## Diagnostic commands that worked

```bash
# camera state reports (code 286 = camera info, 282 = format)
ssh root@192.168.0.1 'grep -a "code\[286\]" /app/Mlog.txt | tail'

# USB enumeration of the Pentax (25fb:0183)
ssh root@192.168.0.1 'cat /sys/bus/usb/devices/1-1.2/idVendor /sys/bus/usb/devices/1-1.2/idProduct'

# gphoto process + port 8080 holder
ssh root@192.168.0.1 'ps | grep pgphoto; netstat -tlnp | grep 8080'

# camera-side log (gphoto stdout)
ssh root@192.168.0.1 'tail /app/Clog.txt'

# force a real restart (workaround for Bug 1)
ssh root@192.168.0.1 'kill $(pgrep -f pgphoto.stage2ondisk); sh /app/restart_gphoto'
```

## Resolution (same session, ~16:10)

A **full gimbal reboot** (`ssh root@192.168.0.1 reboot`) cleared the stale PTP
session — no need to power-cycle the Pentax itself:

- 16:10:19 — first probe after boot: `state:-53` (the usual boot race, ~45 s).
- 16:11:15 — recovered: `manufacturer:ricoh imaging company, ltd.;model:pentax
  k-1 mark ii;state:1;storage:2;photoFormat:2` (JPG mode confirmed).

So the stale-session state (Bug 2) is cleared by a device reboot, not just a
gphoto restart. **Workaround for the field:** when the app shows "no camera"
after a camera-side card switch, reboot the Polaris.

## Next steps

- [x] Clear the stale PTP session — done via gimbal reboot (see above).
- [ ] Verify capture works end-to-end in JPG mode (take a test photo).
- [ ] Patch `/app/restart_gphoto` to `pkill -f pgphoto` (or kill by PID) so
      the kill step actually matches the stage-2 process name.
- [ ] Decide whether the `-2` config failures (Bug 3) are a gphoto2 2.5.34 vs
      Pentax K-1 Mark II quirk or a regression from the new appfs build —
      compare against stock-firmware behavior.
- [ ] Remove the leftover `FwPkt.zip` from the SD card (device never deletes it).

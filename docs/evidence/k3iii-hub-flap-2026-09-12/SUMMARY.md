# K-3 III "major regression" — VIA hub USB flap, 2026-09-12

## Status: DIAGNOSED (hardware/power), software candidate o-v9i built

Operator report: major regression on the K-3 III attached to Polaris
(192.168.0.1), running **o-v9h** (libgphoto2 `90736a1ac`, build_id
6.0.0.54.1).

## What was observed (live, 2026-09-12 17:35–18:20 UTC)

- The **VIA Labs USB2.0 hub (2109:2211) at `usb 1-1.2`** — the hub the
  K-3 III sits behind — was enumerating and disconnecting every ~2 s,
  continuously since boot (94+ disconnects in 34 min; still flapping
  after a clean reboot: 39→41 re-enumerations in 5 s).
- The K-3 III **never enumerated** behind the flapping hub this session
  (`dmesg` shows no `25fb` device at all), so pgphoto had no camera to
  talk to and was in a restart loop:
  `[restart_gphoto] FAIL: pgphoto exited immediately (PID …)`.
- Clog: `[stage2] another pgphoto launch is already in progress (PID 252);
  refusing duplicate` — the polestar_app watchdog kept trying.
- Disabling USB autosuspend (`power/control=on` on all devices) did not
  stop the flap; unbind/rebind of `1-1.2` did not either.
- The hub's own descriptor advertises **bMaxPower = 100 mA** (self-powered
  flag aside, the downstream port budget is tiny). The K-3 III draws more
  than the K-1 II did in the same rig; v9d/v9f K-3 III sessions showed
  **zero** `usb_disconnect` events, so this is a new physical condition.

## Interpretation

This is a **power-delivery / cable problem at the hub**, not a firmware
regression: nothing in o-v9h touches USB power management, and the flap is
visible in kernel `dmesg` before any pgphoto activity. The K-3 III's
higher current draw (or a marginal cable/hub port) trips the hub into a
re-enumeration loop.

## Software state

- o-v9h itself is unchanged from what was built; the regression symptom is
  upstream of libgphoto2 (the camera never reaches PTP).
- New candidate **o-v9i-capturetarget-controls** (libgphoto2 `15b8f6d89`,
  build_id 6.0.0.55.1) adds the generic Pentax `capturetarget` /
  `shutterspeed` / `iso` controls (issue #59) on top of v9h's source.
  Full libgphoto2 test suite 10/10 CI PASS.

## Next actions

1. Physical: reseat the K-3 III USB cable; try a different hub port or a
   powered hub; verify the K-3 III is in PTP (not MSC) mode and fully
   awake before expecting enumeration.
2. Once the hub is stable, confirm `25fb:0189` enumerates and pgphoto
   reports camera state 1.
3. Install o-v9i via the sanctioned SD-card/cold-boot flow; verify
   `build_id=6.0.0.55.1` in `/app/openpolaris-libgphoto2-provenance.txt`.
4. Re-run the K-1 II + K-3 III A/B/C matrix (focus, shutter, RAW+ dual
   format, config reads) against the v9f baseline.

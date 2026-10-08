# Benro Connect crash-loop + dial-B vendor-refusal evidence (2026-10-08 evening)

Device `6.0.0.54.61`, K-3 III `25fb:0189`, phone 192.168.0.2. Issues: #187
(app crash-loop), #186 (bulb trigger failure). Raw: `raw/` (Mlog/Clog boots
269/271 plus extracted socket/286 lines). Full boot-266/267 logs and the
trace analysis are in `../o-v16b-bulb-trace-20261008/`.

## Timeline (device-local)

- 15:08–15:37 — init OK (`state:1`), plain captures work (boot 265/266).
- 16:09–16:38 — bulb attempts never actuate the camera; gphoto returns -10
  after our own 60 s wait (#186).
- ~17:0x — camera power-cycled while in Star AF / AstroTracer 3 with the dial
  on **B**; init then fails with `Pentax init stage vendor enable returned
  0x2002` (PTP GenericNotSupported) → `state:-1/-2`; Benro Connect can see the
  device but crash-loops.
- 17:45 — dial moved **off B**, USB replugged: `vendor enable succeeded;
  gp_camera_init ret 0` within seconds. Camera then dropped off the bus
  (~17:49:51, `state:-5`).
- 17:51 — user rebooted the Polaris with the camera unplugged (boot 271).
  App still crash-loops with **no camera attached at all**: connect → query
  265/266/267/268/275 → socket closed ~0.8 s later → immediate relaunch.

## Findings

1. The app crash-loop is independent of our camera stack: it occurs with the
   camera absent (`state:-5`) and with init healthy. Filed as #187.
2. The 0x2002 vendor-mode refusal correlates with the camera dial being on B
   (and/or the astro state the camera was left in). Off B, the same daemon
   initialises immediately. The A/B confirmation (back to B → refusal returns)
   is still pending — it needs the camera replugged and a stable session.
3. `.61`'s stage2 empty-path check is confirmed inert for the bulb failure
   (see the other evidence dir); nothing here changes that.

## Pending

- Dial A/B reproduction of the 0x2002 refusal.
- Plain (non-bulb) capture with dial off B after a clean init.
- App-side crash log (logcat) for #187; `.60` comparison for app behaviour.

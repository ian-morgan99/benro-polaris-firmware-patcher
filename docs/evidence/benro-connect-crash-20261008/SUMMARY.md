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

## 2026-10-09 authorized single camera-present observation

Raw watcher output: `raw/app-crash-watch-20261009-authorized-attempt.txt`
(SHA-256 `91cecdefbe3e272a886acbc97c634e6c8e3a68c70b80978169fdd59bda1c10e0`).

- Before the attempt, Polaris identity was verified on `.62` via BSSID
  `48:E7:DA:D4:B5:73`, route `wlp8s0`, and `/app/FwVer`.
- At `19:18:53Z`, the host watcher saw USB camera count change `0 -> 1` and ran
  the read-only `app-burst.py` replay. It reported no replies for `265`, `268`,
  and `275`, valid replies for `267` and `266`, then `286 state:-5` (camera absent).
- The device-log snapshot at `19:19:04Z` contains camera property responses,
  including the white-balance list, plus `Unknown value` choices in Clog. The
  Mlog excerpt identifies client `App[96]` making type-1 control queries,
  consistent with the diagnostic replay connection. It does **not** preserve a
  distinguishable native Benro Connect accept/close pair at this test moment.
  Therefore this is not proof that the native app crashed on white balance.
- At `19:20:12Z` the watcher changed `1 -> ?` after SSH/presence polling became
  inconclusive. Follow-up on the host found Wi-Fi disconnected and the route to
  `192.168.0.1` via Ethernet; SSH refused. This does not prove whether the
  Polaris AP/service failed or only the host left the AP. No shutter/capture
  command was sent.
- The watcher was stopped after this one authorized observation. No retry or
  second camera-on cycle was attempted.

**Result:** the operator confirmed Benro Connect died as expected during this
authorized camera-present attempt, so the user-visible crash symptom is
reproduced. The device-side trace does not identify the crashing native app
transaction: `App[96]` is the diagnostic `app-burst.py` client, not proven to be
the phone; its `286 state:-5` also shows the camera was absent by that query.
The Clog snapshot contains the white-balance choices including several
`Unknown value` entries, but the trace does not correlate these lines to a
native phone socket closing. The host then lost the Polaris Wi-Fi association
and routed through Ethernet, so the subsequent SSH refusal cannot distinguish
host route loss from Polaris service/AP loss. Re-prove BSSID/route before any
further device conclusion. #187 remains open and root cause unproven. No shutter
command was sent; no new firmware build or device change is justified by this
sample.

**Next:** no immediate second camera-on attempt. First restore the safe
camera-off connection and verify Polaris identity. Then adjust the watcher to
capture the native Mlog/socket exchange before its diagnostic replay (and
preserve the event window) so `App[96]` traffic cannot be mistaken for the
phone. Only after the updated capture path is checked offline should another
single camera-on reproduction be scheduled and explicitly authorized.

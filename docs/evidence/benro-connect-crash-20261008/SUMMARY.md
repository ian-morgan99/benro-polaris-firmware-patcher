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
  first control-query burst is from `App[105]` at `192.168.0.4` (the host-side
  diagnostic replay). That replay queried `286` while camera initialization
  was still settling: it received `state:-5` at `20:19:08.425`, then the device
  reported `state:1` at `20:19:08.671`.
- Persistent Mlog boot 274 also captures the phone at `192.168.0.2`: `App[107]`
  requests code 780 and gets the expected `.62` `sw` with blank `ov`; its socket
  closes 1.55 s later. `App[108]` connects 4 ms after that, gets the same 780
  response and remains connected until `20:36:14` (over 14 minutes). Neither
  native socket requested camera-property codes 265/266/268/275 in the captured
  sequence. This socket handoff alone is not proof of a process crash: boot 273
  on `.61` shows a similar phone `App[2]` -> `App[3]` handoff in 1.9 s, and a
  native camera-present session with unknown white-balance widget values.
  Those widget values are therefore not a demonstrated cause.
- At `19:20:12Z` the watcher changed `1 -> ?` after SSH/presence polling became
  inconclusive. Follow-up on the host found Wi-Fi disconnected and the route to
  `192.168.0.1` via Ethernet; SSH refused. This does not prove whether the
  Polaris AP/service failed or only the host left the AP. No shutter/capture
  command was sent.
- The watcher was stopped after this one authorized observation. No retry or
  second camera-on cycle was attempted.

**Result:** the operator confirmed Benro Connect died as expected during this
authorized camera-present attempt. The persistent logs do not show a distinctive
native-app crash signature or explain the user's observed death. The diagnostic
replay did race camera initialization, so its `NO_REPLY` and `state:-5` results
are not the phone's replies. The phone's native code-780 exchange returned the
expected `.62` `sw`; a brief socket handoff followed that matches a pattern
already present on `.61`, and a subsequent native socket remained connected for
over 14 minutes. The Clog `Unknown value` white-balance choices also occurred
in a prior native camera-present session that remained active. Neither the
blank `ov` nor those white-balance entries are demonstrated causes. The host
later lost the Polaris Wi-Fi association and routed through Ethernet, so SSH
refusal cannot distinguish host route loss from Polaris service/AP loss.
Re-prove BSSID/route before any further device conclusion. #187 remains open;
root cause is still unproven. No shutter command was sent; no new firmware
build or device change is justified by this sample.

## Persistent-log analysis after the operator restart

The post-restart connection was identity-checked again: BSSID
`48:E7:DA:D4:B5:73`, route `wlp8s0`, `/app/FwVer=6.0.0.54.62`; the camera was
absent from USB. TCP 9090 was listening with a phone peer at `192.168.0.2`.
Persistent boots 273 and 274 and the current text logs are in
`../benro-connect-crash-20261009/raw/`:

| File | SHA-256 |
|---|---|
| `Mlog_000273.log` | `d1174144917f54cdf9a5fadc3098c463d1b492059b61053e7e6daec571674ea8` |
| `Clog_000273.log` | `23a70f884226685c6004f7353d74288aae2f485659c9e98e6797aaa9543a995f` |
| `Mlog_000274.log` | `2d4cbae8c10ac10b56061ab416d9f31505364fd8e0c26712febf0c912310b27b` |
| `Clog_000274.log` | `e0c4ef4ef5a583870df8ffa208cf743e12f5992b17c02574fea7bb5011c49143` |

`Mlog-current.txt` is 232 bytes and records Bluetooth device removal;
`Clog-current.txt` is empty. `scripts/pull-mlog-clog.sh` failed at its remote
metadata step because its SSH command refers to `$1` without passing a remote
positional argument. Logs were then pulled using the documented read-only tar
stream, after rechecking identity.

The full timeline refines the earlier watcher-only conclusion:

- Boot 274 records camera USB add at `20:18:54`. Host client `App[105]`
  (`192.168.0.4`, `app-burst.py`) begins its diagnostic replay at `20:18:57`.
  Its `265/268/275` requests time out; its `286` reply is
  `state:-5` at `20:19:08.425`. The device publishes camera `state:1` at
  `20:19:08.671`, 246 ms later. Thus that replay raced camera initialization;
  its `NO_REPLY` and `state:-5` are not evidence of what the phone received.
- The phone (`192.168.0.2`) connects as `App[107]` at `20:21:47.422`, requests
  code 780, and receives `sw:6.0.0.54.62` with blank `ov` at `20:21:47.488`.
  It closes at `20:21:48.974`; `App[108]` connects 4 ms later, receives the
  same version response at `20:21:49.052`, then remains connected until
  `20:36:14.113` (over 14 minutes). Neither phone socket logs a request for
  camera-property codes 265/266/268/275 in this interval. USB removal occurs
  at `20:34:16`, while App[108] remains connected for almost two more minutes.
- Boot 273 on `.61` shows native phone `App[2]` -> `App[3]` socket handoff in
  about 1.9 s, with `sw:6.0.0.54.61` and the same blank `ov`; its later native
  `App[9]` session requests camera code 266 and remains registered across a
  `13:36:24` state update. Clog logs the same `Unknown value` white-balance
  entries during that active camera-present session. Therefore neither the
  blank `ov` nor those unknown WB values are a demonstrated sufficient cause.

**Conclusion:** the user-visible crash is operator-confirmed, but the logs do
not show a phone process exception. The short phone-socket close on App[107] is
not independently a crash signature because both the previous `.61` boot and
this `.62` boot show rapid socket handoffs, and App[108] then remains connected
for >14 minutes. The camera-on event also overlaps a separate replay racing
camera initialization. Mlog/Clog alone therefore do **not** establish the exact
root cause. Do not patch code 780 or the WB mapping based on this evidence.

**Next:** no immediate second camera-on attempt. The safe camera-off connection
is restored and identity-verified. The watcher should be revised offline to
snapshot native Mlog before its diagnostic replay and mark replay client traffic
separately. Check that path with tests; only then schedule another single
camera-on reproduction with explicit authorization.

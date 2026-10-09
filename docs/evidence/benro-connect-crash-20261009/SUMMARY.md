# Polaris Mlog/Clog pull and #187 crash analysis — 2026-10-09

## Collection

After the operator restarted the device, identity was reverified before log access: BSSID `48:E7:DA:D4:B5:73`, SSID `polaris_d13e86`, route via `wlp8s0`, and `/app/FwVer=6.0.0.54.62`. At collection time the camera was absent from USB, TCP 9090 was listening, and a phone peer at `192.168.0.2` was established. `/app/Mlog.txt` was 232 bytes and `/app/Clog.txt` was empty; persistent boot logs were the useful evidence.

`scripts/pull-mlog-clog.sh` was attempted but failed at its remote metadata step with `sh: 1: parameter not set`: its SSH command refers to `$1` without arranging a remote positional argument. No device writes occurred. The logs were pulled using the documented read-only SSH/tar stream. Artifacts are under `raw/`; SHA-256 hashes are listed below.

| File | SHA-256 |
|---|---|
| `raw/Mlog_000273.log` | `d1174144917f54cdf9a5fadc3098c463d1b492059b61053e7e6daec571674ea8` |
| `raw/Clog_000273.log` | `23a70f884226685c6004f7353d74288aae2f485659c9e98e6797aaa9543a995f` |
| `raw/Mlog_000274.log` | `2d4cbae8c10ac10b56061ab416d9f31505364fd8e0c26712febf0c912310b27b` |
| `raw/Clog_000274.log` | `e0c4ef4ef5a583870df8ffa208cf743e12f5992b17c02574fea7bb5011c49143` |
| `raw/Mlog-current.log` | `95d8f29eff37bf51e47d84288e9ffa1252a8279c282fd067812647494f523b3c` |
| `raw/Clog-current.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty) |

The raw `.log` files are retained locally but intentionally remain untracked under
`.gitignore`'s `docs/evidence/**/*.log` rule; the summary and checksums are the
committed record. This avoids publishing device/network identifiers in raw logs.

## Relevant chronology

### Boot 274, firmware `.62`

- Device Mlog records camera USB add at `20:18:54`.
- At `20:18:57`, diagnostic client `App[105]` from host `192.168.0.4` connects. This is `app-burst.py`, not Benro Connect. Its camera-property requests time out for codes 265/268/275. It asks code 286 at `20:19:08.425` and gets `state:-5`; the device reports camera `state:1` at `20:19:08.671`, only 246 ms later. The diagnostic replay raced camera initialization. Its NO_REPLY and state:-5 results do not establish what the phone received.
- The operator confirms Benro Connect died during the authorized attempt. The persistent Mlog does not show a phone `.2` socket at the camera-add/replay moment, so it does not contain a native phone request/response sequence for that reported death.
- At `20:21:43`, a Bluetooth connection is logged. Phone `.2` then opens `App[106]` at `20:21:47.335`; it closes after 81 ms without a logged app query. `App[107]` opens 87 ms later. It requests code 780; at `20:21:47.488` the device logs and sends `hw:1.1.1.2;sw:6.0.0.54.62;exAxis:1.0.2.14;sv:1;ov: ;`. `App[107]` closes at `20:21:48.974`; `App[108]` opens four milliseconds later.
- `App[108]` requests code 780 again and receives the same correct `.62` version response at `20:21:49.052`. It remains connected until `20:36:14`—over 14 minutes. Neither captured phone socket (107 or 108) requests codes 265/266/268/275. USB removal is logged at `20:34:16`, while App[108] remains connected for almost two minutes afterwards.

### Boot 273, firmware `.61`

- A native phone session (`App[9]`, `192.168.0.2`) requests camera properties 265/268/275/267/266 at `13:35:00`; Mlog returns the white-balance list.
- Clog logs multiple `Unknown value` white-balance widget choices at the same time. The same native client remains registered through a later state update at `13:36:24`; no adjacent socket close is logged.
- An earlier phone socket handoff also occurs: `App[2]` connects, then `App[3]` connects about 1.9 seconds later. This resembles the `.62` 107→108 transition, so a short socket close by itself is not proof of an app process crash.
- Code 780 on `.61` returns `sw:6.0.0.54.61` with the same blank `ov` field.

## What the logs establish—and do not

- The user-visible Benro Connect crash is confirmed by the operator. Mlog/Clog contain no phone-process exception or stack trace, so they cannot identify the exact app crash cause.
- The blank `ov` field is not a proven cause. It occurs on `.61` and `.62`; the `.62` phone received the expected `sw:6.0.0.54.62` twice, and the later phone socket stayed connected for over 14 minutes.
- The `Unknown value` WB entries are not a sufficient cause: they also occur during a native camera-present session on `.61` that stays registered.
- The 20:19 `NO_REPLY` and `state:-5` values came from the diagnostic host client and a camera still initializing, not from the native phone client.
- The host later lost Wi-Fi association and routed through Ethernet. Its subsequent SSH refusal does not distinguish a Polaris outage from host route loss. The post-restart collection verified the Polaris again and the camera was absent.

**Conclusion:** Mlog/Clog do **not** provide an exact root cause. They materially weaken the earlier white-balance and `ov` hypotheses, but the crash itself is not represented in these device logs. Do not make a firmware change based on this sample.

## Operator-reported second camera-on/off event (captured by boot 274)

After the user reported turning the camera on, seeing Benro Connect die, then turning the camera off, boot-274 logs were pulled again. The identity check still showed `.62`; the body was absent when queried afterward. Refreshed raw files and SHA-256s:

| File | SHA-256 |
|---|---|
| `raw/Mlog_000274-after-second-event.log` | `6300ca4e3a0ecd818e73ffd3162e2126b1b3cf407c126f9606efaf2fd2283c9d` |
| `raw/Clog_000274-after-second-event.log` | `c77a9f4012069c8177952b742a3efe2bb3c2e5de7beb0ee72d9652fe41ddcdbf` |
| `raw/Mlog-current-after-second-event.log` | `684d54f8e08b6291fd31b0adc6454139be7da630d57407bab6d62c74f854a4c6` |
| `raw/Clog-current-after-second-event.log` | `ac8ae3ad0b15d6319cec314c3c2bff4172fa091447f36411b4fda42aef934a08` |

- At `20:50:45.611` the camera USB interface enumerated as `25fb:0189`. `spGphotoRest` ran; at `20:50:46.738` USB scan found the K-3 III.
- At `20:50:47.900`, Clog reports `Pentax session already open from a previous connection; observing camera state.` The subsequent `Pentax init stage vendor enable returned 0x2002`, `gp_camera_init ret -1`, and `sp_Gphoto_Init ret -1` produce code 286 `manufacturer:none;model:none;state:-1`.
- USB removal is logged at `20:50:48.406` and `20:50:48.439`, consistent with the user turning the body off. This is a concrete **camera-stack initialization failure** for this event: a stale Pentax session prevented vendor-mode enable. It plausibly explains a camera-not-ready/error state, but not by itself the phone app's process crash.
- No `.2` phone socket/request is logged during this second USB-add / init-fail window. A later `App[113]` from `.3` is present around `20:51:03`; it is not identified as Benro Connect. Therefore the log does not show the exact native phone payload immediately preceding the reported crash.

This is stronger than the first attempt's transient `state:-5`, but still does **not** prove that the `0x2002` response caused the Benro Connect crash. No new test was initiated by the agent; no shutter command was sent.

## Next diagnostic step

Keep the camera off and current `.62` installed. The exact phone crash trigger remains unproven. Repair/test `scripts/watch-app-crash.sh` offline so it captures native Mlog/socket traffic immediately at USB insertion before any separate `app-burst.py` replay; also fix its log-pull helper's remote `$1` failure. Then arrange a supervised attempt with the phone already connected and explicit operator authorization. No firmware fix is justified from this evidence alone.

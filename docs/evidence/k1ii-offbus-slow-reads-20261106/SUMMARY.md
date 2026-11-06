# K-1 II symptoms on v97: what was measured, and what it rules out

Reported on real hardware (PENTAX K-1 Mark II, `25fb:0183`, firmware
`6.0.0.54.97`): setting values works; getting values is very slow; live view
renders correctly at the top and garbled from part-way down; shutter release
fails in the app but eventually fires.

Investigation was cut short when the camera disappeared from the USB bus
mid-session and never re-enumerated, so no symptom could be observed while it
was occurring. This records what was measured and what those measurements
exclude, rather than a conclusion.

## Measurements

| Check | Result |
|---|---|
| Camera enumerated | `25fb:0183 PENTAX K-1 Mark II`, behind a 480 Mb/s USB 2.0 hub |
| `:8080` endpoints | `?action=stream` -> 200 multipart; `?action=snapshot` -> **501** "not implemented and no www-folder configured" |
| Stream from host | headers + boundary, **zero JPEG frames in 12 s** |
| pgphoto PID | 639 at boot, 8614 later, then **stable for 30 s+** and unchanged across the whole off-bus window |
| pgphoto threads | 12, all sleeping normally: `hrtimer_nanosleep`, `futex_wait_queue_me`, `poll_schedule_timeout` |
| pgphoto fds | 11 total: `/dev/null`, two to `/app/Clog.txt`, eight sockets -- **none under `/dev/bus/usb`** |
| `/app/Clog.txt` | **0 bytes**, zero `camera-usb` lines, despite supervisor and pgphoto both writing there |
| Kernel log | `dmesg` unavailable on the device |
| UI-only request | `/api/site` -> 200 in 22 ms (our server is not the slow path) |

## What this excludes

- **A hung pgphoto.** Every thread is in a normal sleep state; nothing is
  blocked in I/O. A wedged process would show `D` state or a USB wait queue.
- **A restart storm.** The supervisor's documented failure mode is ~36 dlopen
  cycles from identity-change feedback. PID 8614 held steady across the entire
  window, including the moment the camera vanished.
- **Our HTTP server being slow.** Non-camera requests return in 22 ms.

## What it does not explain

- **Why the camera left the bus.** No kernel-side record exists (`dmesg` is not
  available on the device) and the supervisor keeps its restart/quarantine
  counters in shell variables, never on disk, with `/app/Clog.txt` empty. The
  state is genuinely unobservable from where I was sitting.
- **The slow value reads and shutter failure.** Both are in Benro's
  `polestar_app`/pgphoto path, not in anything this project owns. With the
  camera off-bus and pgphoto holding no USB descriptor at all, any such request
  must fail or time out -- which is consistent with the symptoms but is not a
  diagnosis of them.

## Live view: two defects found and fixed (separate from the above)

`polaris-httpd.c` fetched `http://<host>:8080/?action=snapshot` from three
sites, an endpoint that returns 501 as shown above, via `wget ... || curl ...`
-- and the device ships neither binary (only `/bin/busybox`, no HTTP applet).
Both faults were independently fatal, so `/api/snapshot` returned 502 and the
Alpaca/INDI image paths had nothing to decode. Fixed in commit `1a37b82` with an
in-process fetch of `?action=stream`.

Two further defects surfaced during testing of that fix:

- A naive `FF D9` search for the JPEG terminator stops at an EXIF `APP1`
  embedded thumbnail's own EOI, yielding a frame whose top decodes and whose
  rest is garbage -- matching the reported garbling. Now walks markers instead.
- The read loop broke on the next `recv` timeout before parsing what it had,
  discarding frames that arrive complete in a single read.

Neither explains the slow reads or shutter failure; they are in our UI path only.

## Shutter failure: one lead, unconfirmed

`polaris-httpd.c:2728` already documents that **opcode 264 is ignored while astro
mode owns the shutter**, and `solve-now.sh` records the same; our own UI tells the
user to take the shot in the Benro app instead. If astro mode was active during
the report, an external capture request is *expected* to be dropped, which fits
"fails on the app, but does take eventually".

The competing explanation is a PTP timeout-and-retry: the shipped driver carries
`msgtimeout=100000` / `timeout=100000` and the strings `Clearing halt on IN EP and
retrying once` / `... OUT EP ...`, so a stalled endpoint can produce a long delay
followed by eventual success. Both fit "eventually fires".

Nothing here distinguishes them, so this is a lead rather than a diagnosis.

`camera-profiles.json` was also checked for per-model gating: it carries only
`sensor_width_mm` and `sensor_class` per body (K-1 II 35.9 mm full-frame, K-3 III
23.3 mm APS-C). There is no shutter or capture capability flag differentiating the
two, so nothing in our own configuration gates the shutter by model.

## Next step

Reconnect the camera (reseat USB; power-cycle the body if it will not
re-enumerate), reproduce each symptom once while watching, and capture bus
state plus pgphoto's PID at the moment of failure. Every measurement here was
taken after the fact, which is exactly why none of them is conclusive.

For the shutter specifically, record whether astro mode was active when it
failed -- that single detail separates the two leads above and has not yet been
established.

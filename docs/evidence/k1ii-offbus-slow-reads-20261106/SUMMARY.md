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

## Shutter failure: gate already shipped, so it is NOT the explanation

Commit `855f718e5` ("pentax: gate K-1 II shutter writes on Tv and verify the
shutter property", PR #144) describes a near-identical symptom, measured live on
a K-1 II:

> *In Bulb the body clears CAN_CHANGE_TV and sets BULB_TIMER, so the gate
> admitted the mode, the body refused the write, and the driver burned ten
> verification cycles (~720 ms) before returning an error.*

That fix is **already on the device**. Its pin `3fb26e536` is what v97 shipped,
and the distinctive string is present in the running driver:

```
strings /app/lib/stage2/libgphoto2/2.5.34/ptp2.so | grep -c "Tv-changeable"  -> 3
```

The operator confirmed the slow reads and shutter failure were observed **on v97**
itself. So the gate did not resolve them, and the ~720 ms verification loop is not
the cause -- it no longer runs. This was checked before building a new candidate:
`build-astro-candidate.sh` defaults to `LIB_BASELINE=3fb26e536`, identical to what
v97 shipped, so a rebuild would have produced the same driver and changed nothing.

What remains plausible is the readiness path rather than the capability gate: the
gate now returns `GP_ERROR_NOT_SUPPORTED (-6)` before touching the wire for a
capability refusal, while busy/idle/transport still comes from
`_pentax_readiness_preflight`. A refusal will therefore say which of the two
reasons it refused -- that is the measurement to take next, and it needs the
camera attached.

The competing explanation is unchanged: a PTP timeout-and-retry. The shipped
driver carries `msgtimeout=100000` / `timeout=100000` plus "Clearing halt on IN EP
and retrying once", which can produce a long stall followed by eventual success.

`camera-profiles.json` was also checked for per-model gating: it carries only
`sensor_width_mm` and `sensor_class` per body (K-1 II 35.9 mm full-frame, K-3 III
23.3 mm APS-C). There is no shutter or capture capability flag differentiating the
two, so nothing in our own configuration gates the shutter by model.

## Live-view fix deployed to the device

`polaris-httpd` from `1a37b82` was installed to both `/app/astro/polaris-httpd`
and `/app/sd/polaris-astro/polaris-httpd` (sha256 `96893201cf1e...`, verified on
the device before install; streamed over ssh stdin because the device runs no
scp/sftp server). The SD copy matters: the boot script only re-copies from it when
`/app/astro` lacks the binary. Previous binary kept at
`polaris-httpd.pre-1a37b82.bak`. Service restarted with its original cmdline;
`:8090`, LX200 `:10001`, INDI `:7624` and Alpaca `udp:32227` all came back up.

Note that flashing delivers none of this -- `polaris-httpd` appears 0 times in the
FwPkt and ships only via the additive Astro bundle, so a rebuild-and-flash would
not have carried the live-view fix at all.

Differential proof that the new fetch path executes, taken with no camera
attached (so both binaries correctly report "no live-view frame"):

| binary | `/api/snapshot` | time |
|---|---|---|
| old (`1df598d4`) | 502 | **0.013 s** -- instant: no wget/curl exists to fail |
| new (`96893201`) | 502 | **6.39 s** -- connects, reads the stream, waits to `SO_RCVTIMEO` |

The 6.4 s is the fetch actually running against `:8080`. Whether a real frame
decodes correctly is still unverified: the camera has been off the USB bus since
mid-session.

## Next step

Reconnect the camera (reseat USB; power-cycle the body if it will not
re-enumerate), reproduce each symptom once while watching, and capture bus
state plus pgphoto's PID at the moment of failure. Every measurement here was
taken after the fact, which is exactly why none of them is conclusive.

Two specific measurements would settle the shutter question:

- the driver's refusal reason -- capability (`GP_ERROR_NOT_SUPPORTED`) versus
  readiness (`_pentax_readiness_preflight`) -- since the gate now reports which;
- whether astro mode was active when it failed. Our own UI documents that opcode
  264 is ignored while astro mode owns the shutter, which would make a dropped
  external capture expected behaviour rather than a fault.

## Reproduction harness

`repro-watch.sh` is staged on the device at `/tmp/k1ii-repro-watch.sh` (syntax
checked under the device's own `sh`, probes verified to emit data). Run it before
reproducing, then read `/tmp/k1ii-repro.log`.

It samples every 2 s for 30 minutes: camera enumeration plus link speed (so a hub
vs direct attachment is visible at the moment of failure), pgphoto's pid and every
thread's state and wait channel (a stall shows as `D` state or a USB wait queue,
which is what was missing from all earlier after-the-fact checks), and any new
bytes appended to `/app/Clog.txt` -- which now matters, because the driver gate
reports *which* reason it refused for.

That last point is the one measurement that settles the shutter question: a
capability refusal returns `GP_ERROR_NOT_SUPPORTED` before anything reaches the
wire, while busy/idle/transport comes from `_pentax_readiness_preflight`. The log
line names which of the two fired.

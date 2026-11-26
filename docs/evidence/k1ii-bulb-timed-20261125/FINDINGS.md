# K-1 II timed-Bulb: accuracy, performance, and the IT2 comparison

Recorded 2026-11-26T01:31Z. Driver pin `f48a05e08` (`.libgphoto2-v117`, clean tree),
host prefix `out/v117-host-driver-prefix` built with
`scripts/build-host-driver-prefix.sh` (`pentax_research_capture=true`, asserted).

## Headline

A 1 s and a 5 s timed-Bulb request on the K-1 II both produced a **20.000 s** exposure.
The driver wrote the requested duration to `0xd00f`, PTP answered `0x2001` (OK), and the
body ignored the write and exposed for its own bulb timer instead. The ~21 s stop-edge
"performance" cost is the same bug: it is the real 20-second exposure, not overhead.

## What was measured

| Request | Driver derived | Write to `0xd00f` | PTP response | EXIF ExposureTime |
|---|---|---|---|---|
| hold 1 s | 1 s | `(1<<32)|1`, `PTP_DTC_UINT64` | `0x2001` OK | **20.000 s** (`2000/100`) |
| hold 5 s | 5 s | `(1<<32)|5`, `PTP_DTC_UINT64` | `0x2001` OK | **20.000 s** (`2000/100`) |

Body state at both runs: `exposure-mode=Bulb bulb-timer=yes bulb-seconds=20/1`,
`Tv-changeable=no`. Driver log at the stop edge:
`pentax-bulb: camera-timed fallback applying N s shutter speed (body reported 20 s at the
start edge, unused)`.

So issue #243's fix is working — the stale body report does **not** drive the duration the
driver asks for. But the write it then performs has no effect on this body in this state,
so the delivered exposure is the body's timer regardless of what we ask for.

## Two tooling errors that produced wrong conclusions earlier today

Both are recorded so they are not repeated.

1. **EXIF parser read only the numerator.** `ExposureTime` is a RATIONAL; the first version
   printed `2000` and I read it as "2000 ms = 2 s". Correctly parsed it is `2000/100` =
   **20.000 s**. The corrected parser is committed alongside this document
   (`read_exif.py`). Any earlier claim of "2 s" from that tool is void.

2. **A driver prefix built without `-Dpentax_research_capture=true`.** `camera_capture()`
   returns `GP_ERROR_NOT_SUPPORTED` (-6) as soon as vendor mode is enabled, before any
   standard `InitiateCapture` attempt. That -6 is indistinguishable from a camera defect in
   the output and was reported as one. Now prevented by
   `scripts/build-host-driver-prefix.sh`, which asserts `boundary=camlib-enter` and
   `pentax-capture[` are present in the built `ptp2.so` and refuses to emit a prefix
   without them.

## The caller-side trap that made accuracy look broken before it was understood

`gp_camera_get_config()` walks the whole settings tree and costs ~6 s on this body. If a
caller fetches the tree inside the hold, that walk lands **between** the driver's start
timestamp and stop timestamp, so a 1 s request is measured by the driver as ~7 s and
applied as 7 s. With the widget tree cached across the two edges the same request applies
exactly 1 s.

Measured breakdown, uncached vs cached:

```
uncached  start edge: get_config=6.083s set_value=0.000s set_config=0.008s
          stop  edge: get_config=5.840s set_value=0.000s set_config=21.036s   -> applied 7 s
cached    start edge: get_config=0.000s set_value=0.000s set_config=0.007s
          stop  edge: get_config=0.000s set_value=0.000s set_config=21.181s   -> applied 1 s
```

The driver was faithful in both cases; the caller inflated the interval it measures. Callers
must cache the widget tree across the two edges.

`gphoto2 --wait-event` cannot be used to measure fidelity at all: it schedules in whole
seconds and added exactly +1.000 s to every hold (measured 2.002/2.001/4.001/5.999 for
requests 1/2/3/5).

## Image Transmitter 2 comparison — the user's question, answered

Yes. IT2 has exactly the two mechanisms described, and it selects between them on one flag.

`MtpDevice.cs:5620`:

```csharp
if ((this._exposureMode == 9U || this._exposureMode == 12U || this._exposureMode == 20U)
    && !this.IsCamBulbTimer)
{
    this._releaseMode = 2U;      // held bulb
}
else if (this.IsMovieMode) { this._releaseMode = 3U; }
else                       { this._releaseMode = 0U; }  // ordinary capture
```

**Mechanism A — held bulb, initiate/terminate.** `releaseMode = 2`, chosen only when the
camera's own bulb timer is **off**. `CamRelease()` (`MtpDevice.cs:4419`) is a toggle:
first call sends `MtpInitiatePentaxCapture(2, ...)` and sets `_shutterReleased = true`;
the next call sees that flag and sends `MtpTerminatePentaxCapture(2, ...)`. The duration
is entirely host-side — IT2 counts down between the two calls. No shutter-speed write is
involved at all.

**Mechanism B — set the time and expose for it.** Chosen when `IsCamBulbTimer` is set:
`releaseMode = 0`, and the duration is written to `0xd00f` exactly like an ordinary
exposure, using a value taken from the camera's own published list:

```csharp
// MtpDevice.cs:1655-1662  TvCurrentIndex setter
byte[] bytes = BitConverter.GetBytes(this._TvList[value]);
this.MtpSetDevicePropValue(53263, ref bytes, out num);   // 53263 = 0xD00F
```

`_TvList` is `List<ulong>` populated from the device's own `GetDevicePropDesc` for `0xd00f`
(`RefreshShutterSpeedList`, `MtpDevice.cs:2800`), reading each entry as a raw `ulong`. So
IT2 sends the camera's own wire values, not synthesised ones. And in this state IT2 renders
that list as seconds, confirming it is a duration domain:

```csharp
// MtpDevice.cs:2826
if (this.IsCamBulbTimer && this.IsTvChangeable)
{
    TimeSpan timeSpan = new TimeSpan(0, 0, (int)num4);
    this._TvCbxItems.Add(timeSpan.ToString("mm\\'") + " " + timeSpan.ToString("ss\\\""));
}
```

So the user's framing is exactly right: mechanism B **is** the ordinary exposure path,
reused for durations beyond the normal dial range. Same property, same write, same capture.

**The gate IT2 has and we do not.** Both the seconds rendering and the timer-domain readback
are conditioned on `IsTvChangeable`:

```csharp
this.IsTvChangeable   = ((num & 2U)  > 0U);   // MtpDevice.cs:5899  == CAN_CHANGE_TV 0x2
this.IsCamBulbTimer   = ((num & 64U) > 0U);   // MtpDevice.cs:5908  == BULB_TIMER     0x40
```

On the K-1 II in Bulb, `CAN_CHANGE_TV` is **clear** and `BULB_TIMER` is **set**. So for this
body in this state IT2 has no available mechanism: A is excluded by `!IsCamBulbTimer`, and B
is not offered because the Tv list is not changeable. IT2 leaves the duration to the camera.
That matches what we observe — a 20 s exposure — and it means IT2 almost certainly cannot
deliver an arbitrary timed-Bulb duration on a K-1 II with the bulb timer enabled either.

## Our driver already has the correct gate, and the Bulb path bypasses it

`pentax-utils.h:245-268` documents precisely this measurement and provides
`pentax_shutter_write_permitted(capability_flags, requested, advertised_seconds,
advertised_count)`:

> Shutter speed is a Tv property, so a non-Bulb request requires
> `PENTAX_CONDITION_CAN_CHANGE_TV` specifically. ... measured on the K-1 II, in Bulb
> (exposure mode 9) CAN_CHANGE_TV is clear and BULB_TIMER is set, and every shutter write
> there was refused by the body. Admitting those requests let the driver issue a doomed
> write and poll ten times before failing.

The camera-timed fallback at `library.c:7895` does not call it:

```c
propval.u64 = pentax_whole_second_shutter_value (seconds);
setres = ptp_setdevicepropvalue (params, PTP_DPC_PENTAX_ShutterSpeed, &propval, PTP_DTC_UINT64);
if (setres != PTP_RC_OK) { /* log and capture anyway */ }
```

Two defects follow from that single omission:

1. **No capability gate.** The write is attempted in a state where the body cannot honour it.
2. **No readback verification, and the failure is silent.** `setres == PTP_RC_OK` is treated
   as success. The body returns `0x2001` and then ignores the value, so the existing error
   branch never fires and the caller gets no diagnostic at all. The widget path
   (`_put_Ricoh_ShutterSpeed`) verifies with a readback; this path does not. A `PTP_RC_OK`
   here proves only that the property is writable in general, not that the duration took
   effect.

## Performance: the 21 s is the exposure, not overhead

The stop edge runs the full capture lifecycle. Inside it the driver polls `0x900f`
(GetAllConditions) every ~200 ms and exits as soon as the body publishes a candidate
(conditions offset 32 == 1, handle at offset 36). One instrumented run:

```
 3.77s  InitiateCapture returned 0x2001
24.79s  candidate 1 observed          <- +21.02 s, 105 x 0x900f polls, zero GetObjectHandles
24.82s  transfer returned 0 (108339 bytes)
```

The loop is correct — it breaks the moment output exists. The 21 s is the body taking 20 s
to expose plus ~1 s to publish. Later runs measured 41.9 s and 44.8 s for the same 1 s
request; that variance is unexplained and needs its own investigation, but it is not
driver-side polling.

Consequence: **accuracy and latency are one defect.** Once the duration actually applies, a
1 s shot should return in roughly 2-3 s instead of ~21 s. Do not optimise the poll interval;
there is nothing there to reclaim.

## Also observed, separate defects

- **`capturetarget` write is a silent no-op.** `--set-config capturetarget=1` returned
  `rc=0`; reading it straight back still reported `Internal RAM`. Same class as the shutter
  write: accepted, not applied, no diagnostic.
- **USB re-enumeration after file deletion** moved the K-1 II from `usb:001,011` to
  `usb:001,013`. Any tooling that hardcodes a port silently targets nothing. Port must be
  discovered by PID (`0x0183` K-1 II, `0x0189` K-3 III) on every run.

## Evidence loss

`/tmp/exif` was wiped mid-session. Lost: the two ground-truth JPEGs, `read_exif.py`,
`bulb_ground_truth.py`, `card_timing.py`, and the compiled direct driver. The EXIF numbers
above were read before the wipe and are recorded here; the raw files are gone and the runs
must be repeated to re-attach byte-level evidence. The direct driver survives as
`tools/pentax_bulb_direct.c` in the test harness repo. The parser is restored in this
directory, corrected.

## Next steps

1. Gate the camera-timed fallback on `pentax_shutter_write_permitted`, matching IT2's
   `IsTvChangeable` condition, and fail loudly rather than shooting at the wrong length.
2. Add a readback of `0xd00f` after the write; treat mismatch as an error, not `PTP_RC_OK`.
3. Decide the product behaviour when neither mechanism is available: refuse with a clear
   message, or fall back to held-bulb (`releaseMode = 2`) even with the timer enabled —
   the latter needs a live test, since IT2 never attempts it in that state.
4. Re-run on the K-3 III, where the header records a populated `0xd00f` enumeration up to
   600 s and a passing 300->600->300 round trip. If B works there and not on the K-1 II,
   the gate is per-body and must stay product-specific.
5. Investigate the 21 s vs 42-45 s stop-edge variance separately.

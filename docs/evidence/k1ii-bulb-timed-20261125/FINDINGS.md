# K-1 II timed-Bulb: accuracy, performance, and the IT2 comparison

Recorded 2026-11-26T01:31Z. Driver pin `f48a05e08` (`.libgphoto2-v117`, clean tree),
host prefix `out/v117-host-driver-prefix` built with
`scripts/build-host-driver-prefix.sh` (`pentax_research_capture=true`, asserted).

## Headline

A 1 s and a 5 s timed-Bulb request on the K-1 II both produced a **20.000 s** exposure --
the body's own bulb timer, not the requested duration. The driver derived the right number,
wrote it to `0xd00f`, and PTP answered `0x2001` (OK). The delivered exposure was 20 s both
times.

The ~21 s stop-edge "performance" cost is the same problem, not a separate one: it is the
real 20-second exposure plus ~1 s to publish. Accuracy and latency are one defect.

**Cause is not yet pinned.** "PTP_RC_OK then ignored" has two candidate explanations that the
evidence so far cannot separate -- see *What is proven and what is not* below. The next run
must read back `0xd00f` and conditions offset 272 immediately after the write, before
`InitiateCapture`; that single measurement decides which fix is correct.

## What was measured

| Request | Driver derived | Write to `0xd00f` | PTP response | EXIF ExposureTime |
|---|---|---|---|---|
| hold 1 s | 1 s | `(1<<32)|1`, `PTP_DTC_UINT64` | `0x2001` OK | **20.000 s** (`2000/100`) |
| hold 5 s | 5 s | `(1<<32)|5`, `PTP_DTC_UINT64` | `0x2001` OK | **20.000 s** (`2000/100`) |

Body state at both runs: `exposure-mode=Bulb bulb-timer=yes bulb-seconds=20/1`,
`Tv-changeable=no`. Driver log at the stop edge:
`pentax-bulb: camera-timed fallback applying N s shutter speed (body reported 20 s at the
start edge, unused)`.

So issue #243's fix is working -- the stale body report does **not** drive the duration the
driver asks for. What fails is downstream of that: the write the driver then performs does not
result in the requested exposure, and nothing in the current path notices.

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

**IT2's view of the same two flags:**

```csharp
this.IsTvChangeable   = ((num & 2U)  > 0U);   // MtpDevice.cs:5899  == CAN_CHANGE_TV 0x2
this.IsCamBulbTimer   = ((num & 64U) > 0U);   // MtpDevice.cs:5908  == BULB_TIMER     0x40
```

On the K-1 II in Bulb, `CAN_CHANGE_TV` is **clear** and `BULB_TIMER` is **set**, so mechanism
A is excluded outright by `!IsCamBulbTimer`. Mechanism B remains *writable*: IT2's
`TvCurrentIndex` setter (`MtpDevice.cs:1655-1662`) has no capability gate at all -- it only
returns early when vendor mode is off. What `IsTvChangeable` gates is the **presentation and
readback** of the list, not the write:

```csharp
// MtpDevice.cs:2826  -- seconds rendering, gated on IsCamBulbTimer && IsTvChangeable
// MtpDevice.cs:5911-5914 -- when IsCamBulbTimer, the current bulb timer value is looked up
//                            as an index into the Tv list
this._camBulbTimerValue = timeSpan.ToString("mm\\'") + " " + timeSpan.ToString("ss\\\"");
this._TvCurrentIdx = this._TvCbxItems.IndexOf(this._camBulbTimerValue);
```

Line 5911-5914 is the important structural fact: **the bulb timer value is itself an entry in
the `0xd00f` list.** Setting Tv to a whole-second value *is* setting the bulb timer. That is
why mechanism B is the right shape for this state, and why our write returning OK but not
taking effect is a real defect rather than "this body simply cannot do it".

IT2 never reads back after writing, so there is no IT2 behaviour to copy for verification --
we would be first. Whether IT2 can actually deliver an arbitrary timed-Bulb duration on a
K-1 II with the timer enabled is **not established**; it would write and then report success
regardless of what the body did.

## Correction to an earlier draft of this document

An earlier version of this file claimed the camera-timed fallback "bypasses" the capability
gate `pentax_shutter_write_permitted()` and that adding it would have prevented this. **That
is wrong**, and it was wrong in the direction that would have sent the fix to the wrong place.
Tracing the gate (`pentax-utils.c`) against our actual request:

```c
uint32_t denominator = (uint32_t)(requested >> 32);   // (1<<32)|N  ->  denominator = 1
uint32_t numerator   = (uint32_t)requested;           //              numerator    = N
if (capability_flags & PENTAX_CONDITION_CAN_CHANGE_TV) return 1;   // clear on K-1 II B
if (!(capability_flags & PENTAX_CONDITION_BULB_TIMER)) return 0;   // set -> continue
if (denominator != 1 || numerator == 0) return 0;                  // passes
/* then membership in the advertised/published second-counts */
```

For a 1 s or 5 s request on this body the gate **returns 1 -- it admits the write.** The
Bulb/seconds domain is deliberately allowed through on `BULB_TIMER` alone, because that
domain was proven writable on the K-3 III. So inserting that gate here changes nothing.

The gate's own comment says exactly what is supposed to judge these requests:

> those requests still go through and are judged honestly by the post-write read-back rather
> than being refused or accepted here

That read-back is the missing piece, and it is the only defect in this path. The
camera-timed fallback at `library.c:7895`:

```c
propval.u64 = pentax_whole_second_shutter_value (seconds);
setres = ptp_setdevicepropvalue (params, PTP_DPC_PENTAX_ShutterSpeed, &propval, PTP_DTC_UINT64);
if (setres != PTP_RC_OK) { /* log and capture anyway */ }
```

`setres == PTP_RC_OK` is treated as success. The body answers `0x2001` and then exposes for
its own timer, so the error branch never fires and the caller receives no diagnostic of any
kind. A `PTP_RC_OK` here proves only that the property is writable in general -- not that the
duration took effect. The widget path (`_put_Ricoh_ShutterSpeed`) verifies with a readback;
this path does not.

## What is proven and what is not

Proven, by EXIF on the captured files:
- A 1 s and a 5 s request both produced a 20.000 s exposure.
- The driver derived the correct duration and issued the write.
- The body answered `PTP_RC_OK` to that write.

**Not proven -- and this is the discriminating question:** what did `0xd00f` read back as
after the write, and what did `bulb-seconds` (conditions offset 272) report at that moment?
Two different failures fit the current evidence equally well:

1. **The write did not land.** Read-back returns 20 s. The body accepted the property and
   silently discarded the value in this state.
2. **The write landed but does not govern the exposure.** Read-back returns 1 s / 5 s while
   the body still exposes for its own timer, meaning the timer runs from a separate control
   that `0xd00f` does not drive on this body.

These need different fixes, and nothing measured so far distinguishes them. The next run must
capture both values immediately after the write, before `InitiateCapture`. Note that
`bulb_timer_seconds` is parsed from conditions offset 272 (`pentax-utils.c:743`) and IT2
line 5911-5914 treats it as an index into the same Tv list, so if read-back shows the write
landed while the exposure still runs 20 s, the timer is being driven from somewhere else.

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

Ordered by what unblocks a decision. Step 1 must run before any code change, because steps
2 and 3 are different fixes and picking one now would be guessing.

1. **The discriminating measurement.** In the camera-timed fallback, immediately after the
   `0xd00f` write and *before* `InitiateCapture`, read back `PTP_DPC_PENTAX_ShutterSpeed` and
   a conditions sample, and log both alongside the requested value. That single run decides
   between "the write did not land" and "it landed but does not govern the exposure". Add it
   as instrumentation first, not as a behaviour change.
2. **Post-write read-back verification**, whichever way step 1 lands. The gate's own comment
   already promises this ("judged honestly by the post-write read-back"), and the widget path
   has one. Today a body that returns `PTP_RC_OK` and ignores the value produces a wrong
   exposure with no diagnostic at all -- the worst possible failure mode for astrophotography,
   because the user only finds out after the frame is lost.
3. **Do not reach for held-bulb as the fallback.** `library.c:7173` records that this body
   "runs its own countdown and rejects a held start" when the timer is on, so mechanism A is
   already known-refused in this state -- it was tried, and refusing outright is what produced
   the pgphoto `state:-6` reports behind issue #239. Reaching mechanism A would require
   *disabling* the camera's bulb timer, and no writable property for it exists in `ptp.h`
   (`PTP_DPC_PENTAX_*` has no bulb-timer entry; IT2 only ever reads it, at 5561/5913). If a
   route to mechanism A is wanted, it has to be found on the wire first.
4. **Re-run on the K-3 III**, where the header records a populated `0xd00f` enumeration up to
   600 s and a passing 300->600->300 write round trip. If the same write lands and governs the
   exposure there, the difference is per-body and any gate must stay product-specific rather
   than becoming a general Pentax rule.
5. **Investigate the 21 s vs 42-45 s stop-edge variance** separately. Same request, same
   driver, roughly double the wall time on later runs -- unexplained, and it will confound any
   latency measurement until it is understood.

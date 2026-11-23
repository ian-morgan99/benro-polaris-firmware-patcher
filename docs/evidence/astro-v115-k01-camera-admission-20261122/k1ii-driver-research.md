# K-1 II driver research — root causes + performance (v115, 2026-11-23)

Body: PENTAX K-1 Mark II fw 2.51, USB 25fb:0183, "Pentax K-1 Mark II (PTP mode)".
Driver: host x86 build of exact v115 pin 0f2f34e00040. Exposure mode Manual.
All findings reproduced direct-PC with PTP traces captured.

## R1 — imageformat/imagequality -102: EXACT root cause (fixable, driver-side)
The Pentax imageformat write is a compound read-modify-write of DPC 0xd01b
(WritingFileFormat). Flow in _put_Pentax_ImageFormat (config.c):
  1. _pentax_readiness_preflight -> GetAllConditions 0x900f (OK)
  2. _pentax_wff_read_payload -> GetPropValue 0xd01b, then a fail-closed guard
  3. pentax_wff_set_format -> ptp_pentax_set_device_prop_raw (0x1016 write)

The K-1 II returns 0xd01b as a **6-byte** payload:
    06 00 50 03 00 01 01   (size field 0x06, then 50 03 00 01 01)
But pentax_wff_payload_is_valid() hard-requires size == 10 or 11:
    if (!payload || (size != 10 && size != 11)) return 0;
So _pentax_wff_read_payload returns GP_ERROR_CORRUPTED_DATA (-102) and step 3
never runs. Trace confirms ZERO 0x1016 ops were sent — the failure is entirely
local, before any write.

Note byte0 = 0x06 = size-4, so the driver's OWN invariant (payload[0]==size-4)
already holds for this body; only the fixed 10/11 window is wrong. The guard was
written for a different Pentax payload form (#54/#55).

FIX: accept the K-1 II's actual 0xd01b shape. Either widen the size window to
include the 6-byte form (and map its byte layout), or special-case model_no for
K-1 II fw 2.51. Must preserve unrelated bytes per #54/#55 intent. This unblocks
JPG+RAW (#386) on both K-1 II and likely K-3 III (same -102).

## R2 — MF drive 0xa00c: EXACT code identity (needs one hardware check)
Both bodies reject the focus op with vendor response 0xa00c:
  - K-3 III: PTP_OC 0x9017 (FocusControlNew) -> 0xa00c
  - K-1 II:  PTP_OC 0x9016 (FocusControl, old family / #303 path) -> 0xa00c
0xa00c is DEFINED in the driver itself as PTP_RC_NIKON_MfDriveStepEnd ("MF drive
reached its step/limit end"). Pentax reuses that vendor code. translate_ptp_result
has no mapping for it, so it reports "unmapped PTP result code 0xa00c reported as
generic error" and the widget write returns -1.

Two possibilities, not yet distinguishable headlessly:
  (a) 0xa00c means "already at limit / nothing to do" -> the drive is actually
      working and #381 is partly a false-positive reporting bug.
  (b) 0xa00c is a genuine reject for this payload shape.
pentaxconditions has no focus-position field, so lens movement cannot be read
back over PTP. Needs either a focus-distance proxy or a visual/physical check on
the mount. Regardless, the driver should map 0xa00c to a meaningful message
instead of "generic error" — that alone improves BenroConnect UX and diagnosis.

## R3 — Performance: full widget tree rebuilt on EVERY command (7.85s / 62 ops)
Measured direct-PC on K-1 II:
  - one --list-config:            7.85 s
  - one --get-config (single):    7.86 s   <-- identical cost for ONE widget
PTP ops issued for a SINGLE get-config:
    30 x GetDevicePropDesc (0x1014)
    18 x GetPropValue      (0x1015)
     5 x GetAllConditions  (0x900f)
     3 x GetObjectHandles  (0x1007)
     2 x GetDeviceInfo     (0x1001)
     1 each Open/Close session, GetStorageIDs, 0x9001
Total ~62 round-trips to answer one question. The driver builds the entire widget
subtree on every gp_camera_get_config regardless of which widget is requested.

This COMPOUNDS #369 (Stage-2 enumerates one property at a time): Stage-2 calls
get_single_config per property, and each such call re-pays the full 62-op tree
build. That is the dominant K-1 II latency source, larger than #369 alone.

FIX directions (perf):
  - Cache GetDevicePropDesc results per session; do not refetch all 30 descriptors
    on every get_config. The driver has devprop caching but it is flushed (see
    "cached devprop should have been flushed" comments in library.c).
  - Build the widget tree once per session and reuse across get/set calls.
  - For Stage-2, batch reads via GetAllConditions 0x900f where a value is derivable
    from conditions instead of a per-property GetPropValue (#369).
Expected: single-widget read drops from ~7.8s to sub-second once descriptors are
cached; UI refresh round-trips drop from 30-50+ to a handful.

## R4 — Confirmed working on K-1 II (do not regress)
iso, whitebalance, shutterspeed, aperture: write + readback + body-state proof via
GetAllConditions (ISO=400 seen in conditions, not just gphoto cache). 51 widgets,
zero empty arrays. Live-view zoom writes WORK here (2x/off round-trip), unlike K-3
III (#384 is K-3 III-specific).

## R5 — Capture/preview unavailable direct-PC (body limit)
--capture-image and --capture-preview both -6; body advertises no 0x4006. #316/#317
must be qualified on the Polaris lane via wire code 264 after v115 installs.

## Open items to exhaust tonight
- Confirm R2(a) vs R2(b) with a focus-position proxy or physical check.
- Measure live-view frame fetch cost and whether pclvkeep reduces per-frame setup.
- Enumerate advertised-but-unpublished properties (missing widgets).
- Test pentaxdrivemode 23-choice writes for silent no-ops like K-3 III peaking.

## R4 — Exact perf fix site (located in source; NOT yet implemented or tested)
Per-widget cost comes from `_get_Pentax_DirectProperty` (config.c ~9615). For each
property it issues:
  1. `ptp_generic_getdevicepropdesc()` — **cached** via `params->dpd_cache` with
     `params->cachetime` TTL (ptp.c:4901).
  2. `ptp_pentax_get_device_prop_desc_raw()` — **uncached**, a fresh
     `PTP_OC_GetDevicePropDesc` transaction every call (ptp.c:1980).
  3. `ptp_pentax_get_device_prop_raw()` — **uncached**, a fresh
     `PTP_OC_GetDevicePropValue` every call (ptp.c:1966).

Steps 2 and 3 bypass the cache entirely, which is why ops scale linearly with
widget count (63 -> 489 for 1 -> 10 widgets) instead of being paid once.

### Why a naive cache would be WRONG here (do not "optimise" this blindly)
Pentax descriptor *contents* are mode-dependent, proven by this same round: in
Bulb the shutter enum contains only `mm:ss` values (00:01..20:00) and **zero**
fractional entries, while other modes expose fractions. Caching a raw descriptor
across a mode change would hand clients a stale choice list — the exact class of
"slider shows values the body rejects" bug this project already tracks (#316).

Therefore any caching must be keyed on, or invalidated by, shooting mode /
drive state. Step 3 (the *value*) must never be cached: it is live body state.

### Status
Located and reasoned only. No patch applied, no measurement of improvement,
because both bodies went unresponsive (every PTP op times out) before a build
could be validated. Implementing without a responsive camera would ship an
unverified change to the packaged driver, which the release-integrity rules
forbid. Requires: responsive body -> build in the registered worktree
(exp/k1ii-driver-perf) -> measure ops+wall-clock before/after -> confirm choice
lists still track mode changes.

## R5 — "Unresponsive camera" was actually PTP_RC_DeviceBusy (0x02fa), not sleep
Earlier I described the bodies as "asleep or powered off". That was wrong. With a
long-enough timeout the K-1 II answers, and the driver reports:

    Pentax init stage OpenSession attempt 1, session 1, returned 0x02fa.
    Pentax state is busy or unknown; refusing session close and USB reset.

`0x02fa` is `PTP_RC_DeviceBusy`. The body is powered and on the bus; it is
declining a new session. Per docs/pentax-mode-aware-liveness.md, busy is a
legitimate post-capture state (dark-frame NR, pixel-shift processing, RAW/JPEG
production, Bulb/astro) and must not be treated as a failure. The driver's
refusal to force-close the session or reset USB is deliberate safety behaviour,
so polling within an expected envelope is the correct response — not a reset.

### Consequence for my earlier measurements
The runs I misread as "fast" (low op count, high wall clock) were sessions that
never completed because OpenSession was refused/timed out. That is exactly why
op counts looked small. Recorded here so the reasoning error is not repeated:
**a low PTP op count alongside a high wall clock means the session failed, not
that the driver was efficient.** Always check gphoto2's own exit code and look
for `returned 0x02fa` / `Timeout` before interpreting timing.

### Also corrected: my perf attribution
The raw Pentax descriptor fetch is a *fallback* (only when the generic call
fails), so it is not the source of the 30 descriptor ops. The source-confirmed
mechanism is `params->cachetime` defaulting to 2 s (library.c:12086) while one
full widget walk spans ~7.95 s, so cached descriptors expire mid-walk and are
refetched. Not every refetch is explained by TTL expiry — gaps as short as
+1.409 s occur inside the window, implicating the `timestamp = 0` invalidation
sites (ptp.c:3744, 5032, 6111), which I have not yet traced.

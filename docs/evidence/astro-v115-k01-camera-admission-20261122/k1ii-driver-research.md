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

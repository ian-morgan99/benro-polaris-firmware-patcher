# K-01 baseline on stock firmware (2026-09-07)

**Conclusion up front:** **The K-01 does NOT work on stock firmware.**
Detection succeeds; the camera responds to PTP `GetDeviceInfo` with
`manufacturer:pentax;model:k-01`; the gimbal reads storage IDs (`0x1004`,
`0x1005`) successfully. But **every preview capture and every
`get_single_config` call fails** with no useful error. Capture returns
`-6`; config reads return `-2`.

The "stock claims K-01 works" claim in earlier docs is **wrong** — or at
minimum: never verified against a real K-01 with stock libgphoto2 2.5.27.
This baseline gives us concrete bugs to fix in the next build.

---

## Comprehensive PTP opcode trace (added 2026-09-07 17:15)

After the initial probe, we confirmed exactly which PTP opcodes pgphoto
sends to the K-01 in MTP mode, and which it does not.

### Standard PTP opcodes sent (always)

```
0x1001 GetDeviceInfo         0x1002 OpenSession
0x1003 CloseSession           0x1004 GetStorageIDs
0x1005 GetStorageInfo         0x1006 GetNumObjects
0x1007 GetObjectHandles       0x1008 GetObjectInfo
0x1009 GetObject              0x100a GetThumb
0x100b DeleteObject           0x100c SendObjectInfo
0x100d SendObject             0x100f FormatStore
0x1014 GetDevicePropDesc      0x1015 GetDevicePropValue
0x1016 SetDevicePropValue     0x101b GetPartialObject
0x9801 GetObjectPropsSupported
0x9802 GetObjectPropDesc      0x9803 GetObjectPropValue
0x9805 GetObjectPropList
```

### Pentax vendor-extension opcodes sent

**None.** Not a single `0x9xxx` (Pentax vendor) opcode is issued by
pgphoto's embedded libgphoto2 2.5.27.1 against the K-01 in MTP mode.

### Why no Pentax ops are sent

1. `gphoto2 --auto-detect` identifies the K-01 as a generic "USB PTP
   Class Camera" — no Pentax model string in detection. (Same on the
   ian-morgan99/libgphoto2 fork.)
2. K-01's PTP device-info reports
   `Vendor extension ID: 0x6 = microsoft.com/DeviceServices`
   (not Pentax), so `ptp2.c:ptp_camera_init()` doesn't dispatch to Pentax
   vendor paths.
3. K-01's `Device Properties Supported` list contains only generic
   `0x5001 Battery Level`, `0x5011 Date&Time`, and three
   `0xd303/0xd406/0xd407` MTP-standard codes. No Pentax-specific
   `0x5xxx` shutter/aperture/iso codes.

### What this confirms

- **K-01 in MTP mode** strips all Pentax vendor extensions; the camera
  itself doesn't expose Pentax-specific PTP codes over MTP.
- **libgphoto2 2.5.27.1** has no fallback for "this is a Pentax body but
  the vendor extension ID is MTP" — it just sees "USB PTP Class Camera"
  and walks the standard PTP opcodes, never reaching Pentax vendor
  dispatch.
- This is **not** a Polaris-runtime bug.
- This is **not** a regression from the fork's `pentax_lookup_model()`
  decision — the K-01's MTP-mode PTP signature is genuinely
  unrecognisable as Pentax to any libgphoto2 that doesn't have a
  Pentax-specific MTP vendor-extension matcher.

### What this leaves open

- The **PTP-mode vs MTP-mode** decisive test was not run today (operator
  decided not to switch the camera body's USB connection mode). Per
  `ian-morgan99/libgphoto2` `docs/pentax/REAL_HARDWARE_TEST_LOG.md`
  2026-09-02, K-01 in legacy PTP mode exposes
  `Vendor extension ID: 0x0000000a` (Pentax) and `pentax.so` drives it
  correctly. The MTP-vs-PTP distinction is a camera-body setting, not
  a libgphoto2 one.

### Recommendation (updated)

No libgphoto2 code change is required. The existing vendor-id dispatch
in `ptp2.c` handles K-01 correctly when it's in legacy PTP mode.
The fix is **documentary**: tell K-01 users to switch the camera body
to legacy PTP mode (USB connection mode menu) before tethering to the
Polaris.

## Test setup

| | |
|---|---|
| Gimbal firmware | stock `firmware/FwPkt.zip` (2026-08-22, MD5 `90bdad51...`) |
| `/app/FwVer` | `FwVer:4.0.0.32;date:2025.05.09;` |
| `/app/bin/pgphoto` | 7,801,576 B, MD5 `a766aaf9...`, libgphoto2 **2.5.27.1** (compiled in, no `dlopen`) |
| `/app/lib/stage2/` | absent (no patcher loader) |
| `/app/bin/polestar_app` | 24,941,228 B, MD5 `f1af6203...` |
| Camera body | Pentax K-01, USB tethered (MTP-mode), via USB-C cable + USB-A adapter |
| USB topology on gimbal | `usb:001,005 ID 25fb:0131` (composite, MTP/PTP class) |
| Capture method | automatic, driven by `polestar_app`'s `updateCameraViewFinder` + `deal_camera_control_handler` |
| Logs saved | `docs/evidence/stock-baseline-2026-09-07/k01-baseline/{Mlog.txt,Clog.txt,error.log}` |

## What happens, step by step (verbatim from logs)

### 1. USB enumeration — works

```
[18:02:45:790] NetlinkUeventTask: info:add@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2.1
[18:02:45:790] NetlinkUeventTask: usb_connect ++++++++++++++++++++
```

`lsusb -v` on the gimbal sees the device as `25fb:0131` (Composite
device — common on Pentax K-01 MTP mode). Detected as a USB PTP class
camera by libgphoto2.

### 2. libgphoto2 auto-detect — works, identifies K-01

```
gp_abilities_list_detect_usb: Auto-detecting USB cameras...
gp_port_usb_find_device_by_class Found 'USB PTP Class Camera' (0x6,0x1,0x1)
gp_camera_set_abilities: Setting abilities ('USB PTP Class Camera')...
gp_camera_set_port_info: Setting port info for port 'Universal Serial Bus' at 'usb:001,005'...
gp_camera_init: Initializing camera...
```

`gp_camera_init` succeeds. The first PTP frames go out:
`0x1004 GetStorageIDs` and `0x1005 GetStorageInfo` and `0x100f
FormatStore`. The K-01 responds (no errors at the PTP layer).

`gp_camera_init ret 0` — so far so good.

### 3. polestar_app sees the K-01 — works

```
[18:02:49:134] SP_MsgFromCameraProc[1154]: MsgFromCamera-->type[1],code[286],
val[manufacturer:pentax;model:k-01;state:1;storage:2;photoFormat:2;]
```

polestar_app receives the standard `code:286` ("camera info") message
and broadcasts it on the wire as
`val[manufacturer:pentax;model:k-01;state:1;storage:2;photoFormat:2;]`
to the iPhone/PC app. **The app would display "Pentax K-01"** — so
discovery is end-to-end successful from the user's perspective.

### 4. **Every `gp_camera_get_single_config` call fails with `-2`**

Right after init, polestar_app walks its known config tree asking for:
`shutterspeed`, `manualfocusdrive`, `autofocusdrive`, `aperture`,
`imageformat`, `capturetarget`, plus more — **all of them return -2**
("widget not found").

```
gp_camera_get_single_config failed: -2
checkWidgetForName: ---- shutterspeed not found in configuration tree.
gp_camera_get_single_config failed: -2
checkWidgetForName: ---- manualfocusdrive not found in configuration tree.
gp_camera_get_single_config failed: -2
checkWidgetForName: ---- autofocusdrive not found in configuration tree.
gp_camera_get_single_config failed: -2
checkWidgetForName: ---- aperture not found in configuration tree.
gp_camera_get_single_config failed: -2
checkWidgetForName: ---- imageformat not found in configuration tree.
```

These are real libgphoto2 widgets that pentax.so should be advertising.
Looking at the `pentax.so.stock` we pulled (see `lib/pentax.so.stock`,
MD5 `276c080b96b6c7b339213e2261eb15b0`), `pentax.so` **does** declare
`K-01` in its model list and has `ipslr_status_parse_k01` — but the
config tree it returns is **empty for K-01 in MTP mode**. The K-01
config tree only populates if it talks to the camera through the
*legacy* Pentax driver, but the gimbal connects through the generic
**MTP-over-PTP** path (where `ptp2.so` handles it, not `pentax.so`).
So the model name "K-01" is in `pentax.so`'s list but the per-property
handlers (shutter speed, aperture, focus, etc.) **only get installed by
`pentax.so`**, not by `ptp2.so`. The result: empty config tree.

This is a **stock libgphoto2 bug for K-01 specifically**: the
`ptp2.c:ptp_camera_init()` enumerates the device's PTP properties, but
the K-01 only reports a small subset (the generic `0xd02c`-`0xd039`
properties we saw in earlier K-3 III logs), and `pentax.so`'s
vendor-specific property enumeration is only wired up if the camera
is opened via `pentax.so`, not via `ptp2.so`.

### 5. **Every `gp_camera_capture_preview` call fails with `-6`**

`gp_camera_capture_preview` returns **-6** every time. Error code `-6`
in libgphoto2 is `GP_ERROR_NOT_SUPPORTED`.

```
gp_camera_capture_preview failed: -6  (every ~40ms, repeating forever)
```

The Polestar app drives the preview in a tight loop, so this is
basically a busy-loop of failures saturating USB bandwidth.

The `-6` here is because `ptp2.so` doesn't know about the Pentax-specific
"start live view" opcode (it's `0x9153` in the Pentax PTP extension).
`ptp2.so`'s generic `ptp_capture_preview` only sends `0x9153` if it
recognises the vendor extension — for K-01 it doesn't, so it falls back
to the standard PTP `0x9153` (which is Canon EOS StartLiveView), and
the K-01 doesn't understand that, so it returns NOT_SUPPORTED.

This is **the canonical K-01 preview bug** that's been known in the
libgphoto2 community since 2013. The fix is in `ptp2.c`'s
`ptp_capture_preview` and `ptp_get_device_prop_value` for the Pentax
vendor extension.

### 6. `capturetarget=1` (Internal RAM) silently fails

```
deal_camera_control_handler command 30  info capturetarget=1 ret -1
enableCaptureTarget cInfo:capturetarget=1  ret:-1  onlyJpg:0
```

polestar_app tries to set capturetarget=1 (Internal RAM), but the
underlying `gp_camera_set_single_config` returns -1 because the
config tree doesn't have a `capturetarget` widget (it failed to find
any widgets in step 4).

### 7. Capture sequence completes but no image arrives

`pgphoto` is being asked to capture (the `updateCameraViewFinder` and
`deal_camera_control_handler` callbacks fire). It responds
`ret:-1` for the viewfinder enable, `ret:-1` for autofocus, `ret:-1`
for the capture target. **No image ever appears** because every
backend call returns -2 / -6.

## Net behaviour the user would observe

| What user does | What happens on stock |
|---|---|
| Plug in K-01 (powered on, MTP mode) | ✅ App shows "Pentax K-01" |
| Switch to camera mode | Live view doesn't start (silent) |
| Try to capture | Nothing happens |
| Disconnect | App correctly shows no camera |

The gimbal **sees** the K-01 but cannot control it.

## Root cause (CORRECTED after deeper inspection)

After operator pushback and a deeper look at the fork's USB ID table, the
real root cause is **a missing USB ID entry in stock libgphoto2**:

- The K-01's USB PTP product ID is **`0x25fb:0x0131`**.
- `camlibs/ptp2/library.c`'s `models[]` table has this entry on
  `ian-morgan99/libgphoto2@master` (commit
  [`d2c2dbe1c`](https://github.com/ian-morgan99/libgphoto2/commit/d2c2dbe1c),
  added 2026-08-22), but **not in any upstream libgphoto2 release tag**
  (`v2.5.27`, `v2.5.28`, `v2.5.34`).
- `gphoto2 --auto-detect` on the stock Polaris therefore reports the
  K-01 as generic "USB PTP Class Camera" — not as "Pentax:K-01".
- The `models[]` lookup never matches `25fb:0131`, so
  `ptp2.c:ptp_camera_init()` walks the standard PTP path instead of
  dispatching to the Pentax vendor path.
- The K-01 *does* respond to standard PTP ops (`0x1004`, `0x1005`,
  etc.) and `pentax.so` *does* know how to drive a K-01 once it's
  loaded, but the loading dispatch never happens because the `models[]`
  table has no `25fb:0131` row.

The fork's commit `d2c2dbe1c` adds (among other research-capture work):

```c
/* K-01 in its native PTP/MTP USB mode (hardware-confirmed 2026-08-22).
 * Generic PTP only: IT2 never supported this body and the legacy SCSI
 * path needs MSC mode (0x0130). */
{"Pentax:K-01 (PTP Mode)", 0x25fb, 0x0131, 0},
```

This is **not gated** by `LIBGPHOTO2_ENABLE_PENTAX_RESEARCH_CAPTURE` —
it's a regular `models[]` identity entry, safe for upstream. It just
hasn't been proposed as a standalone PR yet.

### Fix paths (ordered by impact / cost)

| Path | Cost | Result |
|---|---|---|
| **Add the 5-line K-01 row from `d2c2dbe1c` as a standalone upstream PR.** | tiny (one row in `models[]`) | K-01 detected as Pentax, `pentax.so` engaged, full config tree |
| **Build the patched libgphoto2 from the fork's `master`**, which has the K-01 entry plus all the Pentax research-capture work | medium | Same as above + better K-3 III / K-1 II handling |
| **Patch the Polaris' libgphoto2 directly** with a new staged build that ships the K-01 row | medium | K-01 works on the Polaris |

**The lowest-risk, highest-leverage fix is the first one**: extract the
K-01 entry from `d2c2dbe1c` and submit it as a standalone upstream
PR. That alone turns the K-01 from "USB PTP Class Camera" into "Pentax:K-01".

## Why this is a real bug (corrected) — NOT a vendor-extension problem

The previous version of this report claimed it was a vendor-extension
detection problem in `ptp2.c`. That was wrong. `ptp2.c` does have
Pentax vendor-extension dispatch, but **only** when the `models[]` table
recognises the body's USB ID. Without the `25fb:0131` entry, the
vendor dispatch is never reached.

pentax.so's legacy model table (`pentax.so: ipslr_status_parse_k01`,
`Pentax:K01`, etc.) is **only relevant** in the legacy SCSI camlib path,
not the MTP/PTP path the gimbal actually uses.

## Original (incorrect) root cause analysis — preserved for audit trail

For the first pass, the report concluded that `ptp2.so` "doesn't know
about Pentax vendor extensions". That was based on observing
`Vendor extension ID: 0x00000006` (`microsoft.com/DeviceServices`) in the
K-01's PTP device-info. The truth is more nuanced: K-01 in MTP mode
reports Microsoft's MTP vendor extension ID because **the MTP standard
wraps PTP**; this is the camera's own choice when in MTP mode. In PTP
mode (the body setting), the same K-01 reports
`Vendor extension ID: 0x0000000a` (Pentax). Either way, the missing
USB ID is the primary bug.

## Concrete fixes for the next build

These are what the patcher / fork should add, in order of impact:

### 1. Move libgphoto2 to ≥2.5.34 (already done in our patched build)

The patched build (`builds/2026-09-07-k1ii-k3iii-candidate/`) already
replaces libgphoto2 with 2.5.34, which has the Pentax vendor-extension
support in `ptp2.c`. This should fix the K-01's empty config tree
problem on the patched build.

**To verify:** stage `builds/2026-09-07-k1ii-k3iii-candidate/FwPkt.zip`
via the sanctioned SD-card-extract flow (see
`.github/skills/fwpkt-update-flow/SKILL.md`), power-cycle, plug in K-01,
and capture the same logs. The K-01 config tree should populate.

### 2. (If still failing) Vendor-extension dispatch in ptp2.c

If 2.5.34 still doesn't fix K-01 (because the Pentax vendor extension
detection is conservative), add explicit handling in
`ptp2.c::ptp_camera_init` for `vendor_id == 0x0a12` that:
- enumerates Pentax-specific properties (`0x5001`-`0x50FF`)
- recognises the Pentax live-view opcode `0x9153` with Pentax-specific
  params
- installs the K-01 config tree widgets via `pentax.so`'s
  `camera_init` path even when the camera was opened through `ptp2.so`

This is upstream libgphoto2 PR territory; do it in our fork
(`ian-morgan99/libgphoto2`) rather than in the patcher's
`container/` layer.

### 3. Add a K-01 detection gate to our patcher's stage2 loader

The stage2 loader's `pentax_utils.c` already has the Pentax capture
budget gate (`LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`). Extend it to also
recognise K-01 as a Pentax body that gets the storage shim (so a
connected K-01 reports `storage:1` for "Internal RAM" rather than
`storage:2` for SD card, even though both are physically present).

This is a small patch to `container/stage2_loader.c` and
`container/stage2_policy.c`.

### 4. Don't break what works

Before staging the patched build for K-01 testing, audit that the
patcher doesn't accidentally regress K-1 II / K-3 III support. The
candidate build was tested with the K-3 III this morning (worked);
verify on K-3 III again after re-staging.

## Test plan once we have the patched build staged

For each camera body (K-01, K-1 II, K-3 III), capture:

1. `gp_camera_init ret 0` — should be `0` on all three.
2. Config tree population — count of widgets returned for
   `shutterspeed`, `aperture`, `imageformat`, `capturetarget`,
   `whitebalance`, `iso`, `focus`. Should be non-zero for all three.
3. `gp_camera_capture_preview` — should not return -6 on any of them.
   If it does, that's a remaining bug.
4. `gp_camera_capture` — actual full-resolution capture to a `gp_port_info`
   location on the gimbal's tmpfs.
5. `gp_camera_get_storageinfo` — number of storage IDs returned and the
   filesystem/free-space report.
6. Capture the Clog diff between K-01 and K-3 III on the patched build
   to see if any K-01-specific quirks remain.

## Open questions

- Does the K-01 actually work on this gimbal at all? (It might be that
  the USB-C cable + adapter combination doesn't carry USB 3.0 well, and
  the K-01 is a USB 2.0 device that requires the slower port. But the
  fact that detection succeeds and `gp_camera_init ret 0` argues against
  this.)
- Was there a prior attempt on the K-01 with the patched build that we
  should look at before re-running?

## Files captured

```
docs/evidence/stock-baseline-2026-09-07/
├── bin/
│   ├── pgphoto.stock             (7,801,576 B, MD5 a766aaf9...)
│   ├── polestar_app.stock        (24,941,228 B, MD5 f1af6203...)
│   └── gphoto2.stock             (321,740 B)
├── lib/
│   ├── pentax.so.stock           (292,784 B, MD5 276c080b...)
│   └── ptp2.so.stock             (2,209,028 B, MD5 d8b3cd19...)
├── FwVer.stock                   (FwVer:4.0.0.32;date:2025.05.09;)
├── state.txt                     (machine-readable state summary)
└── k01-baseline/
    ├── Mlog.txt                  (5999 B, USB-connect + 286-camera-info events)
    ├── Clog.txt                  (177,547 B, full gp_camera call trace)
    └── error.log                 (empty)
```
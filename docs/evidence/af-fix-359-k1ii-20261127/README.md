# #359 AF fix — qualified on a physical PENTAX K-1 Mark II (2026-11-27)

## What was tested
Two native x86_64 `ptp2.so` builds, same libgphoto2 version (2.5.34), same meson
options (`-Ddocs=false -Ddocs-internal=false`), differing only by the fix commit:

| camlib | source | md5 |
|---|---|---|
| `/tmp/camlibs-parent` | `f48a05e08` = parent of `089ae66c7` | see camlib-md5.txt |
| `/tmp/camlibs-fixed`  | `089ae66c7` (the shipped pin) | see camlib-md5.txt |

Loaded into the system `gphoto2` 2.5.28 CLI via `CAMLIBS=`, so the only variable is
the camlib. Body: `Pentax K-1 Mark II (PTP mode) usb:001,010`, `25fb:0183`.

## Result — the defect and the fix on the same body, back to back

**Parent (pre-fix):**
```
*** Error ***
autofocusdrive not found in configuration tree.
*** Error (-1: 'Unspecified error') ***
exit=1
Sending PTP_OC 0x9011 -> 0 times
```
This is #359 verbatim: `ret:-1`, no diagnostic, nothing sent to the body.

**Fixed (`089ae66c7`):**
```
/main/actions/autofocusdrive
Label: Drive Pentax Autofocus
Readonly: 0
Type: TOGGLE
```
```
_put_Pentax_AutofocusDrive (2): Pentax autofocus drive: release_mode=0,
                                focus_mode=1, mwb_mode=0, sync_mode=0, aperture_reset=0
ptp_usb_sendreq (2): Sending PTP_OC 0x9011 request...
ptp_usb_getresp (2): Reading PTP_OC 0x9011 response...
0000  0c 00 00 00 03 00 01 20-0c 00 00 00
```
Response container decodes to `type=0x0003` (response), `code=0x2001` = **PTP_RC_OK**.
The body accepted the autofocus drive. Conditions were then polled (`0x900f`,
`0x9001`) by the bounded settle loop, and the session closed normally (`0x1003`).

`DeleteObject` appears **0** times — the settle loop created no candidate and deleted
nothing, as designed.

## Scope of this qualification
Proven: the fix makes AF work on a physical K-1 Mark II, the exact body in #359, using
a camlib built from the commit v119 ships (`git_commit=089ae66c7…`).

Not proven here:
- **AF through the head's own runtime.** No camera is attached to the Polaris head
  (`lsusb` on 192.168.0.1 lists hubs only), so pgphoto → ARM libgphoto2 was never
  exercised. The deployed ARM camlib is `md5 84c724e23a447a688a445f6f18dd9a46` at both
  `/app/lib/libgphoto2/2.5.27.1/ptp2.so` and `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so`,
  built from the same commit, but that is provenance — not a driven lens on the head.
- **K-3 III regression.** The K-3 III is not present on either host, so the body that
  previously worked has not been re-tested. The fix removes a gate rather than adding
  one, and the set path now enforces `af_mode != 0`, but no regression evidence exists.

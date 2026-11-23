# K-3 III direct-PC findings against the v115 driver — 2026-11-23

Driver under test: host x86 build of the exact v115 pin 0f2f34e00040 (contains
dd676defb and ed958942f). Body: PENTAX K-3 Mark III, firmware 2.20, USB
25fb:0189, model string "Pentax K-3 Mark III (MTP mode)". Camera in B (Bulb).

## Works on direct PC
- Enumerates once, no duplicate port.
- 93 widgets published, including /main/capturesettings/shutterspeed,
  /main/imgsettings/iso, /main/capturesettings/aperture,
  /main/imgsettings/whitebalance, /main/capturesettings/exposurecompensation.
- Verified write + readback + restore: iso 100->400->100, whitebalance
  auto->daylight->auto, shutterspeed 00:06->00:15->00:06 and 00:01/00:02 in B
  mode, aperture f/3.2->f/8->f/3.2. All read back exactly; final state matches
  the pre-test baseline.

## Not a defect: EV in B mode
exposurecompensation publishes as Readonly:1, Type: TEXT, Current: 0. That is
the intended shape from ed958942f: _get_Pentax_DirectEV falls back to a readonly
text widget when the body returns no enumeration for 0x5010, and writes stay
enum-gated so none can occur until the camera advertises choices. The user's
expectation ("publish just option 0") is what the code already does. Writes of 1
and 0 both fail closed, which is correct for a readonly widget.

## Real finding: capture is not available in MTP mode
--capture-image returns -6 Unsupported operation. The debug trace shows the
driver never sent PTP_OC 0x4006 (count = 0). The body's own GetDeviceInfo
advertises exactly:
  0x1001-0x100b, 0x100f, 0x1014-0x1016, 0x101b, 0x4002-0x4005, 0x400c,
  0x5001, 0x5011, 0xd303, 0xd406, 0xd407
No 0x4006 (CaptureImage), no 0x9001 (Pentax vendor command). ptp2 therefore
falls through to GP_ERROR_NOT_SUPPORTED without issuing anything.

Consequence: #316/#317 cannot be reproduced or qualified over direct PC in MTP
mode. This is a body capability limit, not a v115 regression. Capture on K-3 III
must be qualified on the Polaris lane via wire code 264, consistent with
docs/ISSUE-WBS-2026-11-14.md (K-3 III belongs on the real Polaris lane; the
K-1-II-specific qualification round must not be run against it).

## Not covered here
Physical capture, Bulb timing and shutter admission on K-3 III still require the
Polaris lane with v115 installed.

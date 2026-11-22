# K-3 III direct-PC findings — 2026-11-22 ~23:10 GMT (v115 driver)

Driver under test: host x86 build from the EXACT v115 pin 0f2f34e00, verified to
contain ed958942f (PR#169 "route EV through conditions"). So this IS the build
with the recent EV fix. Confirmed by `git merge-base --is-ancestor`.

Body: PENTAX K-3 Mark III, USB 25fb:0189, enumerated as
"Pentax K-3 Mark III (MTP mode)". Camera dial in B (Bulb); conditions reported
exposure-mode=Bulb, bulb-timer=yes.

## Settings writes that PASS (write + readback + restore)
- iso            100 -> 400 -> 100   exact
- whitebalance   auto -> daylight -> auto   exact
- aperture       f/3.2 -> f/8 -> f/3.2   exact
- shutterspeed (B mode, whole seconds) 00:06 -> 00:01 -> 00:02 -> 00:30 -> 00:06   exact

## EV in B mode — CONFIRMED: no option, readonly, value 0
Both widgets publish identically in B mode:
  exposurecompensation : Readonly:1  Type:TEXT  Current:0  (zero choices)
  pentaxdirectev       : Readonly:1  Type:TEXT  Current:0  (zero choices)
Writes are rejected because the widget is readonly — correct fail-closed, not a
driver defect. This matches the code path _get_Pentax_DirectEV (config.c ~10227):
when the body returns no enumeration for ExposureBiasCompensation (0x5010), the
driver exposes a readonly TEXT widget carrying the raw thousandths value (0) and
"writes remain enum-gated so none can occur until the camera advertises choices."
The fix is Pentax-vendor-wide (PTP_VENDOR_PENTAX), NOT model-gated, so this is the
intended behaviour on any Pentax whose body advertises no EV enumeration.

Assumption adopted per operator: in B mode there is no EV option; publish only
value 0. The current build already does exactly that (readonly TEXT Current:0).
No code change required for B mode. Whether EV gains choices outside B mode (Av/Tv)
is NOT confirmed here — the driver cannot move the mode dial; needs a physical dial
change to test.

## Shutter 31 s — not a defect
The body's own B-mode shutter list has no 00:31 (nearest published are 00:30 and
00:40). 00:30 writes and reads back exactly. The #241 synthesis path only re-adds
whole-second Bulb entries when the body returns an EMPTY list; here the body
returned a populated list, so it is used verbatim. Requesting 00:31 fails because
the body never advertised it — correct enum-gated rejection.

## Harness coverage gap (honest)
The harness has NO direct-PC physical gate for K-3 III. The only env-gated physical
test is tests/test_k01_pc_transport.py (K-01 MSC). test_v114_shutter_admission.py is
ARM and hash-pinned to the v114 binary, so it cannot exercise v115. Therefore "test
K-3 III via the harness on PC" is not currently possible; a K-3 III direct-PC gate
mirroring the K-01 one would have to be written first.

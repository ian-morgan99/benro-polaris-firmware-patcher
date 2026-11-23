# K-3 III direct-PC findings on v115 — full issue list (2026-11-23)

Body: PENTAX K-3 Mark III fw 2.20, USB 25fb:0189, "Pentax K-3 Mark III (MTP mode)".
Driver: host x86 build of the exact v115 pin 0f2f34e00040. Camera in B (Bulb).
Evidence: k3iii-widget-shapes.tsv (95 widgets), k3iii-empty-arrays.txt,
k3iii-mf-drive-debug.log, k3iii-capture-debug.log.

## Working (verified write + readback + restore)
iso, whitebalance, shutterspeed (incl. 00:01/00:02 in B), aperture,
exposurecompensation-as-readonly-readout. 95 widgets publish; no duplicate port.

## F1 MF drive entirely non-functional (regression vs #320 which says it works)
manualfocusdrive: only val=0 succeeds. -7,-3,-1,1,3,7 all ERROR.
manualfocusdrivenear/far: ERROR. autofocusdrive: ERROR.
Trace: driver sends PTP_OC 0x9017 (FocusControlNew) payload 0xffffffe9; body
rejects with vendor response 0xa00c. 0x900f GetAllConditions in the same session
succeeds, so vendor mode is enabled and the op itself is refused.
Opcode passthrough: 0x9016 -> -6 (driver allowlist blocks it), 0x9017 -> -1.

## F2 MF speed grading is architecturally impossible on this path
pentax_minimum_focus_displacement(open_av_num, direction, *displacement) takes
no magnitude/step argument: magnitude = openAvNum*5/6, sign from direction only.
So every slider position and every "arrow count" sends the identical
displacement. The 3-arrow button can never be faster than the 2-arrow button.
#303 fixed this for the old-focus (0x9016) family; the new-focus path was not
given the same treatment.

## F3 Focus peaking is a silent no-op
pentaxfocuspeaking publishes RADIO [off,on,on+outline] readonly=0. Writes of on
and on+outline return success; readback stays off. Reproduced with PC-LV enabled.
BenroConnect will believe peaking is on while the body never changes.

## F4 Live-view zoom writes all fail
pentaxliveviewzoom publishes RADIO [off,2x,4x,8x,10x,16x] readonly=0; every
write ERRORs, including writing the current value off.

## F5 pclvmode write is a silent no-op
pentaxpclvmode on -> readback off. liveviewcontrols still reports active area,
so the body is not entering PC-LV from this write.

## F6 imageformat / imagequality published writable but every write fails
imageformat [JPEG,RAW,RAW+JPEG] and imagequality [fine,normal,low] publish
readonly=0; all writes fail with -102 Corrupted data, including writing the
already-current value (RAW). BenroConnect cannot set JPG+RAW. Related to #362
(K-1/K-1 II display mapping) but this is a K-3 III write failure.

## F7 Five empty MENU arrays published as writable
5010, d024, d025, d026, d02c: type=MENU readonly=0 choices=0 current=0.
Same class as closed #269 (exposurecompensation 0 choices). A writable widget
with no options is unselectable by any client.

## F8 No NR / pixel-shift / bulb widgets published at all
Zero matches for pixelshift/noise/longexpnr/bulb in the 95-widget list. Bulb
duration is reachable only via shutterspeed enum in B mode.

## F9 Direct-PC capture and preview are unavailable in MTP mode (body limit)
--capture-image and --capture-preview both return -6. The body's GetDeviceInfo
advertises no 0x4006 (CaptureImage), no 0x9001, and no stream ops, so ptp2
never issues a capture op. #316/#317 must be qualified on the Polaris lane via
wire code 264, not direct PC.

## F10 Harness coverage gap
benro-polaris-test-harness has zero references to focuspeaking, liveviewzoom,
manualfocusdrive or imageformat in tests/*.py. None of F1-F6 are gated.

## Not assessed tonight
K-1 II was not on the PC bus (only 25fb:0189 present), so no direct-PC K-1 II
results were produced. No K-1 II hardware claim is made here.

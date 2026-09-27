# o-v13g linked-publication candidate — 2026-09-27

## Result

**INSTALLED; RUNTIME VERIFIED; K-3 III RAW+JPEG CANARY PASS; TWO-SHOT PASS.**

Version F failed before `InitiateCapture` because the Automake-built `ptp2.so`
left `pentax_capture_publications_clear` unresolved. The helper source was in
the Meson build but absent from `camlibs/ptp2/Makefile-files`. No exposure was
made by that failed attempt. libgphoto2 `8601460b3` adds the missing Automake
source entries; patcher `93e1898` makes unresolved internal `pentax_*` symbols
a fail-closed build and package error.

## Exact candidate

- Build id: `6.0.0.54.31-o-v13g-linked-publication`
- libgphoto2: `8601460b3ac055f665e3e132742d3417b6f8298f`
- build-time patcher: `93e1898ab8030a8f868b3ab3f9036c6b87e3e3fe`
- selected camlibs: `ptp2,pentax`
- FwPkt ZIP MD5: `b1b2c79d1777468c4da30fb6ed2abe08`
- FwPkt ZIP SHA-256: `b03e58ee892f778e8a8154bc6ee7d4e020ec1db8f5f300bfdccf3dde0119c271`
- appfs MD5: `c041a33c098707b547054f272521bab6`
- private artifact commit: `355834a9d`

## Deterministic and package gates

- libgphoto2 focused Pentax suite: four tests PASS on the predecessor exact
  reviewed head; the only subsequent source change is the Automake inclusion.
- patcher offline gate: 13 container + 24 Python PASS.
- package gate: structure and `firmwareInfo` manifest PASS, zero failures or
  skips.
- built `ptp2.so`: no unresolved internal `pentax_*` dynamic symbols.

## Install and runtime proof

The complete extracted `FwPkt/` tree was staged through the sanctioned SD
watcher flow. All six on-device MD5 checks passed before reboot. The device
went dark and returned after about 60 seconds. Post-boot `/app/FwVer` and the
embedded provenance matched the build id and both source commits above.

Both active camera-library paths contained identical corrected bytes:

- core, Stage-2 and stock paths: `390194dd561de4bde4eb7ed701401507`
- `ptp2.so`, Stage-2 and stock paths: `28820ac36b0c51af8e88bc352f5d7b54`

The attached K-3 III remained present as USB `25fb:0189`.

## Physical result

1. Bounded RAW+JPEG canary: PASS — lifecycle completion plus file event.
2. Independent fail-closed two-shot gate: PASS — two consecutive operations,
   two distinct file identities, and no second shutter before the first
   operation satisfied its completion/output contract.

The second observed operation crossed `camlib-enter`, preconditions and
`initiate-enter/return` with PTP `0x2001`, reported state 4, reconciled
`IMGP3642.DNG` plus `IMGP3642.JPG`, published `/app/sd/normal/SP_0106.dng`
(32,233,328 bytes) and `SP_0106.jpg` (388,014 bytes) as code 773 events, then
returned state 0. `pgphoto` remained alive; the version-F symbol-lookup crash
did not recur.

## Qualification boundary

This proves ordinary RAW+JPEG completion, publication, and safe subsequent
shutter admission on the K-3 III. It does not by itself close the separate
session/rebind, external mode-change, Preview interaction, long-exposure and
cancellation matrices, nor qualify unavailable Canon/K-1 II hardware.

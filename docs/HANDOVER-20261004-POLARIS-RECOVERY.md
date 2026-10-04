# Polaris recovery and takeover handover — 2026-10-04

## Current position

The Polaris is not reachable over its normal control path. The host can see
the cached Bluetooth device `48:E7:DA:D4:B5:72`, but the connection drops with
`le-connection-abort-by-local`; the Wi-Fi network `polaris_d13e86` never
appears. There is no verified SSH identity, no `/app/FwVer`, and no basis for
claiming which firmware is currently installed. Treat the unit as potentially
hung or bricked until it is physically recovered.

No firmware was written over SSH in this investigation. The latest candidate
was not installed through the documented update flow by this session.

## Corrections to the previous handover

### PrivateResearch archive

The recent release ZIPs were in fact uploaded to the private archive. The
remote `ian-morgan99/PrivateResearch` `main` branch is at commit `6c0ed67ab`
and contains the o-v15p ZIP plus the earlier o-v15a and o-v15c through o-v15o
candidate directories. The failure was candidate quality and provenance
clarity, not a missing PrivateResearch upload.

### Firmware version

The last physically evidenced device identity is o-v15i, displaying
`6.0.0.54.52`. The o-v15j/k patch was invalid and explains the `null` display.
The o-v15p ZIP carried `.53`, but it was built from patcher `02fa2f0`, before
the safety repair in `353e2fd`; its source and package were therefore stale.
The `.53` number is now recorded as consumed and withdrawn. The next candidate
must be derived automatically as `6.0.0.54.54` by the current release builder.

### Candidate safety

o-v15p is now explicitly marked **WITHDRAWN — DO NOT STAGE** in the registry
and its evidence summary. Its old code-780 patch copied the raw version with
`strcpy` but overwrote the adjacent `mov r2,#0x40` memset length. The corrected
patch is on patcher `main` at `c1bbacd` and includes the regression test.

Do not stage o-v15j, o-v15k, o-v15m, o-v15n, or o-v15p. o-v15l also predates
the memset-length repair and should not be used as a recovery image.

## Required recovery order

1. Physically power or charge the Polaris/gimbal and confirm an LED. If it is
   hard-off, Bluetooth cannot wake it.
2. Use the last physically evidenced image, o-v15i, for manual SD recovery,
   after verifying its ZIP hash against the PrivateResearch README and using
   the documented extracted `FwPkt/` update layout. If that updater refuses
   the image, use the original stock FwPkt as the recovery baseline.
3. Once the AP returns, verify SSID/BSSID, route via `wlp8s0`, SSH identity,
   `/app/FwVer`, running process identity, and the matched Stage-2/core/port
   hashes before any camera command. Pull fresh Mlog/Clog before testing.
4. Build a new candidate from patcher `main` `0556e19` (including the
   code-780 repair at `c1bbacd` and the fail-closed `polaris-preflight.sh`)
   and libgphoto2 `main`
   `52196d9f1`, from original stock, with the builder's automatic display
   version. That candidate should be `.54`, not a manually typed value. Run
   the offline package gate, upload the exact ZIP to PrivateResearch, then use
   the sanctioned install flow.
5. Only after runtime identity is proven, test one Manual timed exposure,
   then Bulb, then RAW+JPEG. Keep physical qualification separate from source
   and package success.

## Handoff boundaries

- Patcher delivery branch: `main`, currently `0556e19`.
- Libgphoto2 delivery branch: `main`, currently `52196d9f1`.
- Patcher `main` has unrelated user changes in `.vscode/settings.json` and
  `docs/evidence/polaris-test-20261003/`; preserve them.
- Libgphoto2 `main` has unrelated user documentation edits; preserve them.
- No candidate should be called installed or camera-qualified until the live
  identity and physical capture evidence exist.

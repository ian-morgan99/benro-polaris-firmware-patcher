# Candidate `.89` change summary

Candidate ID: `o-v18k-k1ii-k3iii-controls-20261029`

This is a publishable candidate built from `libgphoto2` `main` and patcher
`main`. It is intended for controlled Polaris testing with the K-1 II and the
colour K-3 III. The release builder records the exact source commits and
artifact hashes in the generated provenance and change manifest.

## Changes included

- Expose the Pentax-gated public `whitebalance` control even when modern bodies
  omit `0x5005` from DeviceInfo. The control uses the complete 18-entry
  IMAGE Transmitter 2 list-index mapping and suppresses the duplicate generic
  property entry.
- Pass IMAGE Transmitter 2's source-derived release-mode argument to the
  Pentax AF-only `0x9011` action. The focus-mode argument remains the AF-only
  value and is not confused with manual focus movement or still capture.
- Retain the reviewed model-specific capability table, K-1/K-1 II direct
  live-view start path, separated IMAGE Transmitter 2 format domains, and
  capture-cycle output reconciliation already present on `main`.
- Retain the patcher `main` K-3 III timed-B dispatch gate and cancellation
  cleanup fix.

## Deliberately excluded

- No periodic 100 ms live-format polling loop is included. Format state is
  handled at the capture-cycle boundary using the source-defined output
  contract and actual candidate reconciliation.
- No unsupported TIFF, speculative StarAF, or unqualified K-1 II AF/MF
  hardware claim is added.

## Qualification status

The host-side libgphoto2 regression suite passed before this candidate build.
Physical qualification remains required after deployment: K-1 II WB and AF
controls, ordinary capture, live view, and restoration; and K-3 III ordinary
capture plus timed-B behaviour. A successful build or install does not close
those hardware gates.

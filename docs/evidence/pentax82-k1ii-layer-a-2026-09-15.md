# Issue #82 K-1 II Layer A start — blocked by USB enumeration

Date: 2026-09-15
Intended camera: Pentax K-1 II
Intended layer: A, direct PC
Raw evidence: `/tmp/pentax82-k1ii-layer-a-20260915/`

## Result

No Pentax USB device was present during the test window. Full `lsusb` showed no
`25fb:*` device and `gphoto2 --auto-detect` returned an empty table. Summary,
config, storage, and file-count commands all returned:

```text
-52: Could not find the requested device on the USB port
```

No camera operation was attempted, and no recovery action was performed. This
is an attachment/enumeration precondition failure, not a K-1 II stability result.

## Required next physical action

Connect the powered-on K-1 II to the PC USB port and leave it connected. Verify
that `lsusb` shows the K-1 II vendor/product identity (`25fb:0183`) before
re-running Layer A.

## Completed Layer A result

The camera later enumerated as `25fb:0183` on `usb:001,004` and the complete
direct-PC sequence was executed. Camera identity passed: K-1 Mark II, firmware
`1.02`, serial `7371227`, battery `100%`. Configuration reads, storage info,
file-count access, and final USB stability passed. The camera reported
`No Image Capture`; generic capture and preview both returned `-6 Unsupported
operation`. No camera files were modified or deleted.

This completes the available direct-PC Layer A checks. Capture, preview, and
K-1 II control lifecycle tests must continue on the embedded Polaris path.

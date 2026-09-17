# Issue #82 Layer A: K-3 III direct-PC test

Date: 2026-09-15
Camera: Pentax K-3 Mark III, firmware 2.20, serial 8093033
USB: `25fb:0189`, Bus 002 Device 002
Layer: A, direct PC `gphoto2`
Evidence capture directory: `/tmp/pentax82-layer-a-20260915/`

## Results

| Check | Result | Evidence |
|---|---|---|
| USB enumeration before tests | PASS | `usb.txt` |
| Camera identification | PASS | `summary.txt`; model, firmware and serial reported |
| Storage read | PASS | `storage.txt`; SD1 read-write, 1328 free images |
| Configuration enumeration | PASS | `config.txt`; status and action nodes visible |
| File enumeration | PASS | `files.txt`; camera files listed without mutation |
| Generic capture | EXPECTED UNSUPPORTED | `capture.txt`; `No Image Capture`, `-6 Unsupported operation` |
| Generic preview | EXPECTED UNSUPPORTED | `preview.txt`; `-6 Unsupported operation` |
| USB after tests | PASS | `post.txt` and `final.txt`; `25fb:0189` remained present |

## Interpretation

The direct PC path is healthy for identification, storage access, configuration reads,
and file enumeration. It does not expose generic capture or preview through this
`gphoto2` build, so this path cannot test the Polaris Pentax capture/preview lifecycle
or the #82 timer/session hypotheses. The capture and preview failures are capability
rejections, not evidence of a USB drop or a stale-session failure.

No files were deleted or downloaded, and no camera recovery action was performed.

## Next boundary

Layer A is complete for the available direct-PC operations. The K-3 III must now be
moved to the Polaris for the embedded Layer C tests. After the move, independently
verify the Polaris USB identity before any capture or preview operation.

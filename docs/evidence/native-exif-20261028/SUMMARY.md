# Native solve EXIF write-back smoke

**Date:** 2026-10-28
**Scope:** host native C EXIF writer and JPEG decode smoke. This is not a
camera or Polaris SD-card qualification.

The host ARM-independent build's `polaris-exif-solve` wrote a solved result
containing RA, Dec, rotation, scale, match count, RMS, focal length, sensor
width, and source metadata into a copy of the 4096×3072 Gaia-rendered JPEG.
The original file was not modified.

`polaris-extract` decoded both the original and rewritten JPEGs at 4096×3072
with 30 detected stars and the same reported decode timing. The output file
was published only after the writer returned success and produced a non-empty
file, matching the temporary-file replacement contract used by
`polaris-align.sh`.

The remaining qualification is physical: verify EXIF read-back with the
camera/consumer path, power-loss behaviour during replacement, and the local
Polaris-side copy after a real capture. A camera-card-only file is outside
this contract.

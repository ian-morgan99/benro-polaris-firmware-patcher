# Pentax Capture Memory Budget (Issue #2)

**Status:** Implemented in `f3933a4` (parameterization) + this commit (256 MiB default). Awaiting hardware validation.

## Why this matters

libgphoto2's Pentax driver (`camlibs/ptp2/pentax-utils.c`) enforces a hard upper
bound on a single capture's file size, both as a safety valve (a buggy camera
that streams forever) and as a memory-pre-allocation guard. The default is:

```c
#define PENTAX_CAPTURE_MAX_FILE_SIZE_DEFAULT (2U * 1024U * 1024U * 1024U)  /* 2 GiB */
```

The driver calls `gp_malloc(PENTAX_CAPTURE_MAX_FILE_SIZE)` once per tether
session to stage the largest plausible frame. On a desktop workstation, 2 GiB
is harmless. On the Polaris, the entire userspace has only **512 MB – 1 GB of
RAM** (depending on appfs variant and runtime carve-out), and that 2 GiB
allocation is *worse* than a normal OOM kill: it can succeed against an
overcommit, then fail partway through capture, leaving pgphoto stuck in a
partial state and the tether hung.

## Consequence observed (predicted, not yet on-device)

- **K-1 II tether:** PEF/DNG raw ~35-40 MB; full-res DNG + embedded JPEG
  ~50-80 MB.
- **K-3 III tether:** PEF ~30-35 MB.
- **65536 × 4912 (6×7 analog film scan via Pentax capture mode):** single
  image 600+ MB.

The 256 MiB default is **6× the largest single-frame K-1 II capture** with
comfortable headroom for a 32-bit ptp2 struct ring + libusb2 buffers + the
loader policy shim stack.

## How to override

```sh
./patch-polaris.sh --fwpkt FwPkt/ --pentax-max-capture-size 536870912   # 512 MiB
./patch-polaris.sh --fwpkt FwPkt/ --pentax-max-capture-size 1048576     # 1 MiB, regression-test only
```

The flag flows `patch-polaris.sh` → `docker run -e PENTAX_MAX_CAPTURE_SIZE=…`
→ `container/patch.sh` → `sed` substitution of `@PENTAX_MAX_CAPTURE_SIZE@` in
`container/ondisk/pgphoto.wrapper.in`. The wrapper exports it as
`LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE` for `pgphoto.stage2ondisk` (the
trampolined Pentax-aware binary) to read at session start.

Bounds enforced by the libgphoto2 fork:

| Setting           | Value     | Source                                        |
| ----------------- | --------- | --------------------------------------------- |
| Min (hard floor)  | 1 MiB     | `PENTAX_CAPTURE_MIN_FILE_SIZE` in pentax-utils.c |
| Default (we ship) | 256 MiB   | this document + `PENTAX_MAX_CAPTURE_SIZE` env default in `container/patch.sh` |
| Stock (libgphoto2) | 2 GiB     | `PENTAX_CAPTURE_MAX_FILE_SIZE_DEFAULT`        |
| Max (theoretical) | UINT64_MAX | only constrained by `strtoull` parsing       |

## Hardware evidence so far

**This is the open item.** All evidence above is *predicted* from the
allocator pattern + the Polaris SoC datasheet. To validate:

1. Flash a custom FwPkt built with `--pentax-max-capture-size 1048576` (1 MiB).
2. Plug in a K-1 II, attempt a tether capture of a 35 MB PEF.
3. Expected: `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE` log message at pgphoto start,
   capture rejected with `GP_ERROR_NO_MEMORY` or a Pentax-specific "file too
   large" error from ptp2, pgphoto exits cleanly without segfault.
4. Repeat with `--pentax-max-capture-size 268435456` (256 MiB) → capture
   succeeds, file is received intact.
5. Repeat with stock `--pentax-max-capture-size 4294967296` (4 GiB) → expect
   OOM kill of pgphoto (DO NOT ship).

If steps 1-4 do not behave as predicted, file a new issue linking
`pentax-utils.c` line numbers and the on-device log.

## Related issues

- **#1** (parameterization) made this fix possible — without the env-var
  pathway, every non-default cap value would have required a hand-edited
  checked-in wrapper.
- **#21** (FwPkt ZIP structure validation) will produce the hash of the
  FwPkt.zip we can use to correlate against stock OOBE captures.

## Files touched

- `container/ondisk/pgphoto.wrapper.in` — added `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE` export
- `container/ondisk/install_stage2.sh` — added `PENTAX_MAX_CAPTURE_SIZE` env var with 256 MiB default
- `container/patch.sh` — added the env var to the wrapper-generation `sed`; logged the active value
- `patch-polaris.sh` — added `--pentax-max-capture-size BYTES` flag
- `patch-polaris.ps1` — added `-PentaxMaxCaptureSize BYTES` parameter

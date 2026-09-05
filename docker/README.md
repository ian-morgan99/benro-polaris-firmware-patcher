# Docker image: `polaris-patcher-pentax`

The Pentax + HDMI Benro Polaris patcher is built and verified
inside a single self-contained Docker image. This directory
contains the Dockerfile that produces the image.

## Image identity (as of 2026-08-27)

| Field | Value |
|---|---|
| Repository / tag | `polaris-patcher-pentax:latest` |
| Image digest (sha256) | `b475ca01354845358d21e7adbf0eba9fffc3792e8f49a2d548cadf327cc27953` |
| Approx. size | ~981 MB |
| Base image | `debian:9` (stretch, archived) |
| Architecture | `linux/amd64` |
| Toolchain | `gcc-arm-linux-gnueabi` 6.3.0 (Debian 9) — targets glibc 2.24 to match the Polaris camera board (HiSilicon Hi3559V200, Linux 4.9.37) |

## Why Debian 9 / glibc 2.24

A modern toolchain would emit references to glibc symbol
versions the device does not have (e.g. the 2.34 libpthread
merge) and the rebuilt `libgphoto2.so` would fail to load
on the Polaris. Debian 9 (stretch) ships GCC 6.3.0 — the same
compiler family Benro / Snoppa used for the stock build —
and its libc matches the device's exactly.

## Build the image

```bash
cd <repo-root>
docker build -f docker/Dockerfile -t polaris-patcher-pentax:latest .
```

After build, confirm the digest:

```bash
docker images --digests polaris-patcher-pentax
# REPOSITORY                  TAG     IMAGE ID       DIGEST                                                                SIZE
# polaris-patcher-pentax      latest  <image-id>     sha256:b475ca01354845358d21e7adbf0eba9fffc3792e8f49a2d548cadf327cc27953  ~981MB
```

The digest will change if any of these change:

- The base `debian:9` image
- The apt packages listed in the `RUN apt-get install` step
- The `python3` packages added in the second `RUN` step
- The copy of the patcher source if the build context drifts

If your digest differs, rebuild from a clean `docker build
--no-cache` and update the table above. The combined FwPkt
re-pack at `builds/2026-08-27-combined-720p60/` was produced
using the digest listed above.

## What the image provides

- `arm-linux-gnueabi-gcc` cross-compiler targeting glibc 2.24
- `mkfs.ubifs`, `ubinize` (mtd-utils) for the UBIFS re-pack step
- `qemu-user-static` for the patcher's optional self-test
  (the build+package smoke test at
  `container/test_polaris_pentax_build_package.sh` runs with
  `SELFTEST=0`, so qemu is not actually exercised by the
  default test)
- `python3` + `lzo` for `container/hdmi_geometry_patch.py`
- `libexif-dev`, `libltdl-dev`, `zlib1g-dev`, `libpopt-dev`,
  `libusb-1.0-0-dev` for libgphoto2's autoconf build

## Builds that depend on this image

| Build | Status | How the image is used |
|---|---|---|
| `builds/2026-08-23/` (Pentax only) | Round-trip verified | Source cross-build of `libgphoto2` against the clean `da8c33482` checkout |
| `builds/2026-08-27-combined-720p60/` (Pentax + HDMI) | Round-trip verified (layered over the 2026-08-23 FwPkt) | Re-pack of `appfs.ubifs` with the HDMI-patched `bin/polestar_app` substituted in |

For the end-to-end rebuild that supersedes the layered
combined build, see `docs/CRITICAL-REVIEW.md` §8.5.

## Reproducing the layered combined build

The current combined FwPkt was produced by:

1. Extracting `appfs.ubifs` from `builds/2026-08-23/FwPkt.zip`
2. Running `container/hdmi_geometry_patch.py --include-dead=0`
   against the extracted `bin/polestar_app` to write the
   5 LIVE-site patches
3. Re-packing `appfs.ubifs` inside the Docker image (so the
   `mkfs.ubifs` / `ubinize` versions are the ones the image
   was built with)
4. Substituting the new UBIFS back into the FwPkt zip

For the exact command sequence and the recorded hashes, see
`docs/RUN-JOURNAL.md` and the
`builds/2026-08-27-combined-720p60/build-source-provenance.txt`
file.

## Image publication

The image is currently built locally only — it is **not**
pushed to a public registry. To share with the project owner,
either:

- Export: `docker save polaris-patcher-pentax:latest | gzip > polaris-patcher-pentax.tar.gz`
- Or rebuild on the recipient's host from this Dockerfile
  (recommended, since the digest above is the canonical
  reference).

If/when the project owner wishes to publish the image, the
image does not contain the firmware itself — it is purely
the build environment — so publication has no licensing
implications.

# Building and publishing an Astro candidate

This branch is a separate Astro candidate line. The firmware packet is built
through the same camera patcher as the standard line; Astro is an additive
native-C SD-card bundle. It is not a second camera implementation.

## Reproducible build

Use a clean clone of the pushed Astro branch, not the dirty owner worktree.
Use a clean checkout of libgphoto2 `feature/polaris-capture-events` (NOT driver main) and the stock FwPkt input:

    git clone --branch feature/astro-native-platesolve \
      https://github.com/ian-morgan99/benro-polaris-firmware-patcher.git astro-build
    cd astro-build
    scripts/build-astro-candidate.sh \
      --id astro-v1-camera-baseline-YYYYMMDD \
      --stock-fwpkt /path/to/stock/FwPkt \
      --libgphoto2-source /path/to/LibGphoto2-polaris-capture-events \
      --display-fwver 6.0.0.54.N \
      --build-id astro-v1-camera-baseline-YYYYMMDD \
      --camera-baseline 397320411a1355f06d21233435e144d24efc4207 \
      --libgphoto2-commit 3fb26e536ac169e4970d69516a9d45daf62563f5 \
      --catalog-package /path/to/gaia-dr3-g10 \
      --change-summary docs/release-change-summary-v95-astro.json \
      --focal-min 50 --focal-max 50 --sensor-mm 23.5

The focal and sensor values are deliberate. In production they should be
derived from the camera EXIF or an explicit camera profile. The command
selects FITS indexes, bundles the Gaia tile catalogue and includes the exact
GPL corresponding sources. It runs both the shared camera gate and Astro
tests, then writes:

- FwPkt.zip and FwPkt/;
- astro-bundle.tar.gz and ASTRO-MANIFEST.sha256;
- install-manifest.json;
- shared-camera-gate.txt and astro-test-transcript.txt;
- astro-candidate-manifest.json with all source, dependency and packet hashes.

The builder refuses dirty source, a libgphoto2 baseline that is not reachable from
`origin/main` or `origin/feature/polaris-capture-events`, a wrong libgphoto2 commit,
stale libgphoto2 build directories and outputs outside the selected out directory. A
detached checkout at the pinned SHA is accepted; an orphan or unmerged commit is not.
It does not install, reboot,
flash, stage or upload anything.

## Publication

After reviewing all evidence:

    scripts/publish-astro-candidate.sh \
      --build out/astro-v1-camera-baseline-YYYYMMDD

The publisher uses a fresh or clean detached PrivateResearch worktree, refuses
dirty checkouts and refuses to replace ZIP bytes for an existing destination,
recomputes packet hashes, verifies the candidate identity, and pushes only:

    firmware-packets/<display-version>--<candidate-id>/

The published directory contains the packet, Astro bundle archive, manifests,
test transcripts and a README. It is a candidate only. It must not be staged
on Polaris until the camera owner accepts the baseline, issue #251 is resolved
or explicitly waived, and a supervised test window is scheduled.

## Installation boundary

No SCP or manual SSH code replacement is part of this process. Firmware
installation uses the documented extracted FwPkt ZIP/Bluetooth-wake process.
The Astro SD bundle is installed separately according to its README. A green
host gate, emulator result, or synthetic solve does not qualify camera
lifecycle, JPEG publication, EXIF writeback, pointing accuracy, drift control
or motor safety on physical hardware.

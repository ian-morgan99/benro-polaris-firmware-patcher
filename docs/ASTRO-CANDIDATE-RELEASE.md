# Building and publishing an Astro candidate

This branch is a separate Astro candidate line. The firmware packet is built
through the same camera patcher as the standard line; Astro is an additive
native-C SD-card bundle. It is not a second camera implementation.

## Reproducible build

Use a clean clone of the pushed Astro branch, not the dirty owner worktree.
Use the clean pinned libgphoto2 main checkout and the stock FwPkt input:

    git clone --branch feature/astro-native-platesolve \
      https://github.com/ian-morgan99/benro-polaris-firmware-patcher.git astro-build
    cd astro-build
    scripts/build-astro-candidate.sh \
      --id astro-v1-camera-baseline-YYYYMMDD \
      --stock-fwpkt /path/to/stock/FwPkt \
      --libgphoto2-source /path/to/LibGphoto2-v86-main \
      --display-fwver 6.0.0.54.N \
      --build-id astro-v1-camera-baseline-YYYYMMDD \
      --camera-baseline 8c015c0a73c8affea8fa723badcceb4070ef81b4 \
      --libgphoto2-commit 051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff \
      --catalog-package /path/to/gaia-dr3-g10 \
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

The builder refuses dirty source, the wrong branch, a non-main libgphoto2
checkout, a wrong libgphoto2 commit, stale libgphoto2 build directories and
outputs outside the selected out directory. It does not install, reboot,
flash, stage or upload anything.

## Publication

After reviewing all evidence:

    scripts/publish-astro-candidate.sh \
      --build out/astro-v1-camera-baseline-YYYYMMDD

The publisher uses a fresh or clean detached PrivateResearch worktree, refuses
dirty checkouts and existing destinations, recomputes packet hashes, and
pushes only:

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

# Firmware patcher agent instructions

These instructions apply to all automated or human-assisted work in this repository.

## Mandatory libgphoto2 upgrade contract

Before changing any packaged libgphoto2 component, read and follow `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`.

A libgphoto2 upgrade is a **matched-stack change**, not a camlib-only change. The load-bearing set includes:

- `/app/bin/pgphoto` wrapper/launcher;
- `pgphoto.stage2ondisk`;
- `libpolaris_stage2.so`;
- `libgphoto2.so.6`;
- `libgphoto2_port.so.12`;
- `ptp2.so`;
- `usb1.so`;
- every active camlib/iolib lookup path;
- the wrapper environment and ABI/symbol assumptions.

Do not conclude an upgrade is correct because `ptp2.so` builds, QEMU passes, or direct `gphoto2` works.

## Source/runtime ownership rule

When a camera operation fails:

```text
direct exact libgphoto2 SHA + directly attached camera FAIL
  -> candidate libgphoto2 issue

direct PASS + Polaris-local FAIL
  -> patcher / pgphoto / Stage-2 / loader / path / session issue

direct PASS + Polaris-local PASS + OpenPolaris FAIL
  -> OpenPolaris issue
```

Compare the first divergent lower-level PTP operation/state transition, not just final GP error numbers.

Do not make a libgphoto2 change to fix a Polaris-only symptom without a direct source-repo reproducer.

## No direct runtime mutation as a release fix

Do not replace camera-stack binaries directly under `/app` over SSH as a supported fix. Release-qualified changes must flow:

```text
source change
 -> clean patcher build
 -> architecture/ABI/provenance gates
 -> immutable FwPkt + manifest
 -> supported firmware install
 -> cold reboot
 -> runtime-loader proof
 -> physical camera regression matrix
```

SSH is read-only diagnostic by default. A temporary explicitly authorised experiment invalidates qualification evidence until a canonical FwPkt is reinstalled.

## Regression protection

Every libgphoto2 upgrade must rerun all previously physically qualified cameras. Never optimise only for the camera that motivated the upgrade.

At minimum preserve the known-good Canon R5 Mark II path from the Blaine upstream architecture and the Pentax K-3 III / K-1 II paths as they become qualified.

If required hardware is unavailable, mark the candidate unqualified for that camera; do not silently downgrade a previous PASS to untested.

## Documentation obligations

Every upgrade issue must identify which of these need updating and update them before closure:

- `docs/canonical-pentax-source.md`
- `docs/TESTED.md`
- `docs/HOW-IT-WORKS.md`
- `docs/patcher-gates.md`
- `docs/RUN-JOURNAL.md`
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`
- README supported/qualification claims
- libgphoto2 direct-hardware matrix
- OpenPolaris E2E matrix

Keep direct libgphoto2 evidence separate from Polaris runtime and OpenPolaris E2E evidence.

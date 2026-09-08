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

## FwPkt provenance contract (cross-repo, cross-agent)

Every FwPkt artifact — no matter which repo (`BenroPolarisPatcher`, `OpenPolaris`,
the libgphoto2 fork) or which agent session produced it — must be traceable by
**commit links + hashes**, per `docs/FWPKT-PROVENANCE-CONTRACT.md`:

- **Record before handoff.** The moment a zip is built, received, or copied to
  another machine/card/repo, add (or update) its row in the registry table in
  `docs/FWPKT-PROVENANCE-CONTRACT.md` with: zip MD5 + SHA-256, payload appfs MD5,
  libgphoto2 source commit SHA, and patcher commit/branch. Recompute hashes from
  the actual file; never copy them forward from a doc.
- **Handoff passes four things:** registry id, zip MD5+SHA-256, appfs MD5, and
  both commit links. The receiver verifies all of them before staging on a device.
  A zip with no matching registry row is *unprovenanced* — do not stage it.
- **Zips stay out of public git.** Zip bytes live in `builds/`, `out/`, the SMB
  share, or the SD card; only the registry row (hashes + commit links) is
  committed. A private zip location may be added later as a `zip_location` column.

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
- `docs/FWPKT-PROVENANCE-CONTRACT.md` (registry row for any new/received FwPkt zip)
- README supported/qualification claims
- libgphoto2 direct-hardware matrix
- OpenPolaris E2E matrix

Keep direct libgphoto2 evidence separate from Polaris runtime and OpenPolaris E2E evidence.

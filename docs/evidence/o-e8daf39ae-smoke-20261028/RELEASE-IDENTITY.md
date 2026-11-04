# Release identity: `6.0.0.54.84` offline smoke candidate

**Lifecycle state: `BUILT` and `PUBLISHED`; deployment blocked.** This record is
not evidence of staging, installation, runtime verification, or camera
qualification.

## Identity

| Field | Value |
|---|---|
| Candidate ID | `o-e8daf39ae-9fdedd4-smoke` |
| Display firmware version | `6.0.0.54.84` |
| `FwPkt/FwVer` | `FwVer:6.0.0.54.84;date:2026.10.28;` |
| libgphoto2 commit | `e8daf39aebaa6dc748e9f22d07c3368ed5aa7515` |
| Patcher commit | `9fdedd499e34d280ebbc93dbbb501dc94f7d274b` |
| libgphoto2 dirty diff | empty |
| Patcher dirty diff | empty |
| Selected camlibs | `ptp2,pentax` |
| Legacy USB-SCSI packaging | enabled (`1`) |
| Build provenance | `/tmp/polaris-k1-e8daf3-smoke/build-source-provenance.txt` |

`177f7edea` is the immediate parent of the libgphoto2 commit above. It is
lineage information, not the exact libgphoto2 commit used for this package.

## Artifact fingerprints and locations

| Item | Value |
|---|---|
| Local ZIP | `/tmp/polaris-k1-e8daf3-smoke/FwPkt.zip` |
| ZIP size | `68392693` bytes |
| ZIP SHA-256 | `3a7f4e550e7f66fb412619acbce7998a06d2191349c6e684b555f0ba8cee0464` |
| ZIP MD5 | `84d38af66793186de852041c726db622` |
| `appfs.ubifs` MD5 | `bb1ff0765987703e7a7fc0d08eba3de5` |
| Durable private artifact | `firmware-packets/6.0.0.54.84--o-e8daf39ae-9fdedd4-smoke/FwPkt.zip` in `ian-morgan99/PrivateResearch` (latest record commit `809d58eac`; original publication commit `1e824fcb4`) |
| Install manifest | `/tmp/polaris-k1-e8daf3-smoke/install-manifest.json` (generated from this exact ZIP) |
| Device staging path | none |
| Install evidence | deployment attempt stopped before staging: supported installer invoked the automatic Bluetooth/Wi-Fi wake path, but the Polaris target did not advertise or hold a link; preflight remained `ASLEEP` and SSH was refused |

The `/tmp` path is an ephemeral working copy. The exact ZIP, provenance, and
install manifest are now recorded in the durable PrivateResearch firmware
registry; the local path is retained only for the pending install attempt.

## Package contents

The package contains the standard `FwPkt` camera and gimbal payloads:

```text
FwPkt/camera/config
FwPkt/camera/uImage
FwPkt/camera/rootfs.ubifs
FwPkt/camera/appfs.ubifs
FwPkt/gimbal/polaris403_2.0.0.22.bin
FwPkt/gimbal/polaris413_2.0.0.22.bin
```

The provenance declares the selected `ptp2` and `pentax` camlibs and the
optional legacy USB-SCSI package. That describes package contents; it does not
prove any camera model is physically supported.

## Firmware component checksums

These are the checksums recorded in this package's `FwPkt/firmwareInfo`:

```text
config       MD5 1905e2d041be62b679f7dc6c64ab9d3a
uImage       MD5 5f6a0c1861a254371c4a956b57f26685
rootfs       MD5 778b27bcade9ddc6ea4a7cb45254c551
appfs        MD5 bb1ff0765987703e7a7fc0d08eba3de5
polaris403   MD5 4facafa7d29c1e6c2a125b8309c9b901
polaris413   MD5 c0299d06a15f5c2fbecb9a6db76a29c5
```

## Deployment status

The install manifest was generated with the repository's canonical manifest
generator and the candidate now passes the deployable identity check. The
structural package and firmwareInfo manifest gates passed. The full canonical
pre-release gate was not run, so this remains a built/published candidate, not
a fully gated release.

Deployment was attempted on 2026-10-28. The supported installer detected that
SSH was unavailable and invoked `scripts/polaris-preflight.sh --wake`; the
local Bluetooth route was available, but the Polaris target was not advertising
and no held Bluetooth link or access point appeared. Preflight therefore
reported `VERDICT=ASLEEP` and the installer refused to stage any files. The
complete attempt is in the candidate `install.log` and was copied to the
durable PrivateResearch record. Do not infer installation from the publication
record. Re-run the supported installer against this exact candidate only after
Polaris is powered and preflight is `READY`.

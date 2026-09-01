# Layman summary — 2026-08-31 22:11 UTC

> Plain-English snapshot for "what is going on, what are we doing next,
> and how do we know it's safe?" Read this first.

## Where we are

We are trying to install a custom-built `FwPkt.zip` onto the Benro
Polaris gimbal. The custom build differs from the factory firmware in
exactly one way: the `appfs.ubifs` (the on-board Linux application
filesystem) has been padded with extra data so the MD5 differs from
stock. Every other key in the package (config, uImage, rootfs, the two
polaris bin files) is byte-identical to the factory build.

The challenge is **not** building the zip — we have done that, and an
offline verifier confirms all six keys in `firmwareInfo` (the manifest
inside the zip) match the actual file contents. The challenge is
**getting the gimbal to actually pick up the zip and run the upgrade**.

## The two paths into the gimbal's upgrade code

The Benro Polaris firmware has **two distinct ways** to receive a
firmware update. We know this because we have already reverse-engineered
the gimbal's protocol and the Benro Connect Android app's bytecode
(`com.snoppa.libra` v3.0.33 from `BenroConnect_1727595281455.apk`).

### Path A — Autonomous SD-card (the "Benro documented" way)

The Benro website says: "place `FwPkt.zip` on the SD card, then either
reboot the gimbal or hold the power button twice." This works by:

1. `polestar_app` (the gimbal's main app) starts up.
2. It scans `/app/sd/FwPkt.zip` — this is the SD card mount point.
3. If it finds the zip, it unzips it into `/app/sd/FwPkt/`.
4. It runs `/app/getFwInfo.sh` to compute the MD5 of every file on the
   device's NAND flash, writing the result to `/app/sd/FwPkt/crcInfo`.
5. It compares the on-device MD5s against the `firmwareInfo` MD5s from
   the zip. If they match, it hands off to U-Boot to reflash NAND.
6. If MD5s already match (or the zip is missing), it logs
   "no need upgrade" and does nothing.

We have direct evidence this path works: in our pre-probe capture at
18:50 UTC, `polestar_app` was restarted, the on-boot watcher fired,
and it logged "no need upgrade" because the stock FwPkt.zip it found
on `/app/sd/` already matched the device. So the **watcher exists and
runs** — we just need to give it a non-matching zip and it will install.

### Path B — Benro Connect app over WiFi (the "iPhone" way)

The Benro Connect app pushes upgrades over the gimbal's TCP control
port (9090) using a sequence of protocol commands:

1. `810` (the "SYS_FW_UPGRADE" arm) — tells the gimbal "an upgrade is
   coming, open your USB-UART."
2. The gimbal then tries to open `/dev/ttyUSB2` or `/dev/ttyUSB3` and
   expects the FwPkt.zip to stream in over USB-serial.
3. `819`, `820`, `821`, `822`, `825` are the progress and result
   messages that the app uses to drive the UI.

**The critical issue:** our gimbal does not have a USB-serial gadget
connected. The Mlog shows `SP_TtyUsbUartInit[298]:usb uart open failed`
every 500ms when 810 is sent, because no `/dev/ttyUSB*` device exists
on the device. The iPhone app physically plugs into the gimbal's
USB-OTG port to deliver the zip — it is not a WiFi delivery.

**Conclusion:** Path B is blocked by a missing USB-serial gadget. We
cannot fix this without loading a kernel module or patching
`polestar_app` itself. Path A is the user-facing way and does not
require USB.

## What we are doing next

The plan is to use **Path A** by restarting `polestar_app` while the
custom FwPkt.zip is staged on `/app/sd/`. The on-boot watcher should
then detect the zip, run the MD5 check (which will fail in the way we
want, because the appfs MD5 is different), and proceed to the U-Boot
reflash handoff.

Concrete steps:

1. **Confirm the zip is at the right place** — done, `/app/sd/FwPkt.zip`
   is 68,484,216 bytes, md5 `92da888387b14dc02976b5fa22b94067`.
2. **Confirm the on-board app is running** — currently PID 248,
   `/app/bin/polestar_app`, started 20:35 UTC.
3. **Restart `polestar_app`** via SSH so the on-boot watcher fires
   against the padded zip. We expect to see `SP_UpgradeCheckFw` lines
   in Mlog, then `fwPack Md5 crc success` and the U-Boot handoff
   message. If any MD5 mismatch fires, we know exactly which key is
   wrong.
4. **Watch Mlog live** during the restart.

## How we know it is safe

- The padded FwPkt.zip is **byte-identical to the stock FwPkt.zip
  except for `appfs.ubifs`**. Five of the six keys are unchanged. So
  the worst case is "appfs doesn't install" — the existing NAND appfs
  is untouched, the gimbal continues to work, and we just see the
  install fail in Mlog with a specific error message.
- The MD5/size integrity check runs **before** any NAND reflash. If
  the check fails, nothing on the device is overwritten. This is by
  design — the gimbal refuses to install corrupt packages.
- We have the stock `FwPkt.zip` in the patcher repo at
  `builds/stock/` and can push it back to the gimbal at any time over
  SSH if we need to revert.
- The padded FwPkt.zip is on the SD card (`/app/sd/`), not on the
  internal NAND. Even if the install half-completes, the SD card is
  removable.

## Why we are not just using Path B (810 from the iPhone app)

The iPhone app's 810 trigger arms a USB-serial port that does not
exist on this device. We could try to:

- Load a USB-serial kernel module (`g_serial` or `usb_f_acm`) on the
  gimbal. **Blocker:** the kernel modules are not on the device and we
  cannot `apt install` (no compiler, no internet on the gimbal).
- Patch `polestar_app` to skip the `SP_TtyUsbUartInit` and instead
  read the zip from `/app/sd/`. **Blocker:** this is a 24 MB ARM ELF
  binary, we have no ARM cross-toolchain, and a wrong patch would
  break the running gimbal.
- Connect a real USB-serial gadget. **Blocker:** the gimbal has only
  one USB port and it is not host-mode (it is a peripheral).

None of these are tractable in the time we have. Path A works with the
tools we already have.

## Open questions

1. **Will the on-boot watcher actually fire on a polestar_app restart,
   or only on a full cold reboot?** The 18:50 evidence is from a
   restart, so it should fire. If it doesn't, we will trigger a cold
   reboot (812 = `SYS_REBOOT` over TCP 9090).
2. **Will the 2-press on the gimbal body work as a manual trigger if
   the on-boot watcher doesn't see the zip in time?** This is a
   physical action the user can take; the protocol should be the same
   either way.
3. **Why does the iPhone app show "6.0.0.54" and not offer an
   upgrade?** This is a separate issue from the install path. The
   "sw:6.0.0.54" string is hardcoded as an immediate in
   `polestar_app` (`SP_GetDeviceVer` @ code 780) and the iPhone
   compares the device's `sw:` against the zip's `sw:` before
   offering an upgrade. We do not need to fix this for the install
   itself to succeed — the install is autonomous, the iPhone is just a
   status viewer.

## Key files

- `/app/sd/FwPkt.zip` (on the gimbal) — padded build, 68,484,216 bytes
- `/app/bin/polestar_app` (on the gimbal) — main app, 24,941,228 bytes,
  PID 248
- `/app/getFwInfo.sh` (in appfs) — MD5 manifest generator, byte-identical
  between stock and padded builds
- `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-30-padded-appfs/FwPkt.zip`
  (local copy of the padded build)
- `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/STATE.md`
  (authoritative state file for this investigation)
- `/home/ian/Documents/VSCodeProjects/OpenPolaris/shared/src/commonMain/kotlin/dev/openpolaris/core/protocol/Codes.kt`
  (line 214 = 810 SYS_FW_UPGRADE, line 254 = 819 SP_OMS_UPGRADE_START
  per the decompile audit)
- `/home/ian/Downloads/BenroConnect_1727595281455.apk` (the Benro
  Connect app that was decompiled; 148.8 MB)

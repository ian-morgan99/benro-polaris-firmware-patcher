# Standard SD-card install runbook

**Date**: 2026-09-01
**Author**: investigation agent
**Status**: ready, blocked on physical SD card
**Padded FwPkt.zip**: `builds/2026-08-30-padded-appfs/FwPkt.zip` (68,484,216 bytes, md5 `92da888387b14dc02976b5fa22b94067`, sha256 `0d4ae8101cc190ee2db45453442fb165b343171785671e641e022cbfc1d2dd8f`)

---

## Why this is the only remaining standard path

From `docs/HOW-IT-WORKS.md` line 374-375:

> `polestar_app` (Linux userspace) **never writes NAND**. It verifies MD5s, then
> reboots; **U-Boot** performs the flash from the SD card on the next boot.

From `blaineam/benro-polaris-firmware-patcher` README:

> Use the same SD-card firmware-update procedure you already use for official
> Benro updates, but with the FwPkt.zip this tool produced. The device verifies
> the package (MD5), reboots, and U-Boot writes it.

So the install procedure is the **same** one the user has already used many
times for official Benro firmware updates. Blaineam's `patch-polaris.sh` is
just a zip-builder. The install is "drop zip on the SD card and boot".

**What does NOT work** (confirmed by prior sessions):

| Path | Why it fails |
|------|--------------|
| Autonomous scan on boot (drop zip in `/app/sd/` on internal rootfs) | polestar_app does not scan `/app/sd/` for FwPkt.zip on plain boot. Mlog shows zero hits after a clean reboot. |
| 810 over WiFi (TCP 9090) | The zip stream requires `/dev/ttyUSB2` which only exists when the camera/USB-OTG cable is physically plugged in. |
| `trigger_upgrade.sh` (debug artifact) | Removed. Was leftover from a prior session, not a real install path. |
| `OmsPkt.zip` in `/app/sd/` | That file is camera-written, not user-actionable. |

## The actual standard path (what we need to do)

```
[builds/2026-08-30-padded-appfs/FwPkt.zip]
    │
    ▼ write zip to a physical SD card
[SD card reader or phone+OTG]
    │
    ▼ insert into gimbal head's SD slot
[gimbal head SD slot]
    │
    ▼ power on the gimbal (cold boot, not just wake)
[gimbal]
    │
    ▼ U-Boot reads SD, validates FwPkt.zip, flashes NAND
[NAND has patched appfs]
    │
    ▼ reboot into new firmware
[polaris running patched libgphoto2]
```

## Step-by-step

### 1. Get the padded FwPkt.zip onto a physical SD card

The dev box has no built-in SD card reader (only `loop*`, `sda`, `nvme0n1`).
Options, in order of preference:

**A. Plug in a USB SD card reader.** Cheapest, fastest. ~$5 on Amazon.

```bash
# On dev box, after plugging in USB SD card reader:
lsblk  # new device should appear, e.g. /dev/sdc
sudo mkfs.vfat /dev/sdc1   # only if SD is not yet FAT-formatted
mkdir -p /tmp/sd && sudo mount /dev/sdc1 /tmp/sd
sudo cp /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-30-padded-appfs/FwPkt.zip /tmp/sd/
sync
sudo umount /tmp/sd
```

**B. Transfer the zip to the phone, then use the phone's SD card slot.**

The phone (Android or iPhone) can move the file to the SD card via the Files
app, then plug the SD card into the gimbal head. This is what most users do
since they don't have an SD card reader on their PC.

### 2. Insert SD card into the gimbal head

The Benro Polaris has a microSD slot somewhere on the head. **Unplug the
gimbal first** (or at least make sure it's powered down). Insert the SD
card. **Do not eject the SD card while the gimbal is on**.

### 3. Cold-boot the gimbal

The standard firmware-update procedure requires a **full power cycle**, not
just a "wake from sleep" via the phone app. So:

1. Make sure the gimbal is **fully off** (no lights).
2. Power on.
3. Watch the lights. The upgrade sequence takes longer than a normal boot.

### 4. Watch Mlog for the flash

If the gimbal is awake enough to have SSH up, we can tail Mlog. If not, we
just have to wait for the device to come back online and check the firmware
version.

```bash
# On dev box, if SSH is up:
ssh root@192.168.0.1 'tail -F /app/Mlog.txt'
# Look for lines like:
#   unzip /app/sd/FwPkt.zip -d /app/sd/
#   SP_GetDeviceVer: ...
#   crcInfo: ...
# or U-Boot-level messages
```

### 5. Confirm the new firmware is installed

After the device comes back online, the firmware version should be reported
differently. But since we are using the **same FwVer string** as stock
(v4.0.0.32), the iPhone app won't see "an upgrade is available" — it'll just
be the patched libgphoto2 in the background. The check is whether the
**libgphoto2 patch actually took effect** (Pentax works, etc.).

## Risk and recovery

From `docs/HOW-IT-WORKS.md`:

> A bad/incomplete appfs is "normally recoverable" by re-flashing (stock or
> corrected) because U-Boot itself is not touched. **This is an argument for
> recoverability, not a guarantee; flash at your own risk.**

Specifically:
- The flasher is U-Boot, which is in a separate NAND partition and is NOT
  modified by this install.
- If the patched appfs is bad, the device may fail to boot, but U-Boot will
  still be alive and will read the next SD card you put in.
- Recovery: put a known-good FwPkt.zip (or stock) on the SD card, insert,
  power on. U-Boot will re-flash.

## What's the stock zip?

If you want to **baseline-test the install path** before installing the
patched zip, the stock FwPkt.zip can be extracted from a full Benro firmware
update file (e.g., `POL_BM7A_V4.0.0.32.zip` or similar — the same file you
use for official Benro updates). The Benro update zip should contain
`FwPkt.zip` at the root.

`container/verify_firmwareinfo.py` can verify any FwPkt.zip is well-formed.

# Phase 3 — Cellular (Quectel / Sierra modems) on the Benro Polaris

> **Status:** optional, off by default. The patcher ships the loader scripts
> unconditionally so the bootapp wiring is in place, but it does **not** ship
> the four `.ko` modules — you must supply them. Verified against stock
> firmware `FwVer 4.0.0.32` (May 2025).

## 1. What the stock firmware already does

The Polaris camera board firmware already contains the full **Quectel PPP
userspace stack**, even on units that Benro never sold with a cellular modem:

- `pppd`, `chat`, `pppdump`, `pppstats`, `quectel-ppp-kill` in `/app/bin/`.
- `/etc/ppp/peers/quectel-ppp` — defaults to `/dev/ttyUSB3 115200` with APN
  `3gnet`.
- `polestar_app` has the full glue: `check_pppd_ttyusb ok/failed`,
  `update_pppd_cfg apn name :%s len:%d`, `/etc/ppp/peers/quectel-ppp-%s`,
  `/dev/ttyUSB3 %d`, `update quectel-chat-connect-%s apn:%s info complete`.

That means the **userspace is already there and correctly wired** for a Quectel
EC25 / EG25-style modem. The only thing missing is the **kernel-side
USB-serial host driver stack** — `usbserial.ko`, `option.ko`, `qcserial.ko`,
`cdc_acm.ko` — so the modem never enumerates as `/dev/ttyUSB*` and the PPP
glue above never runs.

The Phase 3 patch is precisely the addition of those four `.ko` modules (plus
a VID-gated loader that is a no-op when no modem is present).

## 2. Hardware caveat — does your unit have a modem?

The Benro Polaris launched in two variants: a SIM-card version and a
non-SIM version. The SIM socket is on the same PCB in both, but only the
cellular variant has the Quectel/EC25 (or equivalent) module **populated**.

- **Cellular variant** — SIM socket + populated Quectel modem. The
  Phase 3 patch will make `/dev/ttyUSB*` appear after boot and `polestar_app`
  will offer the "Cellular" / SIM-APN settings page.
- **Non-cellular variant** — SIM socket present but the modem IC, antenna
  lines, and SIM-data lines are unpopulated. The Phase 3 patch is a **safe
  no-op** on this unit: the loader checks `lsusb` for a Quectel (0x2c7c) or
  Sierra (0x1199) VID and exits cleanly when none is found.

> If you can open the gimbal and visually confirm the modem IC + u.FL antenna
> pigtail are soldered down, the cellular variant is a real possibility.
> Otherwise assume non-cellular and use this feature only to learn the wiring.

## 3. Pre-built modules you must supply

The device kernel is **Linux 4.9.37** on the **HiSilicon hi3559v200** SoC,
built with a glibc 2.24 userland. The cross-toolchain inside the docker
image (`arm-linux-gnueabi`, gcc 6.3.0) targets glibc 2.24, but it does **not**
ship the HiSilicon SDK or the matching 4.9.37 kernel headers — both of which
are needed to build out-of-tree modules against the device's `Module.symvers`
and `.config`. The patcher therefore accepts pre-built modules instead of
trying to cross-build them itself.

### What you need to build the four modules

Required:

- A Linux 4.9.37 source tree matching the Polaris kernel (HiSilicon's BSP
  tarball, not mainline).
- The Polaris `Module.symvers` (extract from `/proc/kallsyms` after a stock
  boot, or from the device's `vmlinux`).
- The Polaris `.config` (extract from `/proc/config.gz`, or rebuild from the
  same BSP tarball with the Polaris defconfig).
- The Linux 4.9.37 `drivers/usb/serial/{usbserial,option,cdc_acm,qcserial}.c`
  sources. These are part of mainline 4.9 and not HiSilicon-specific.

Recommended build invocation (assumes `$KDIR` is your kernel source tree):

```bash
cd $KDIR
make ARCH=arm CROSS_COMPILE=arm-hisiv400-linux- modules_prepare
make ARCH=arm CROSS_COMPILE=arm-hisiv400-linux- \
  M=drivers/usb/serial modules
```

Then stage the four files into a directory of your choice:

```bash
mkdir -p ~/polaris-cellular
cp $KDIR/drivers/usb/serial/usbserial.ko ~/polaris-cellular/
cp $KDIR/drivers/usb/serial/option.ko     ~/polaris-cellular/
cp $KDIR/drivers/usb/serial/cdc_acm.ko    ~/polaris-cellular/
cp $KDIR/drivers/usb/serial/qcserial.ko   ~/polaris-cellular/
```

> **Note:** the toolchain prefix `arm-hisiv400-linux-` matches the HiSilicon
> SDK that ships with the Polaris BSP. Do not use `arm-linux-gnueabi-` — it
> targets a different ABI for `__user` pointer handling and the modules will
> fail to load with `disagrees about version of symbol module_layout`.

### Directory layout the patcher expects

The patcher looks for exactly these four filenames — anything else in the
directory is ignored:

```
~/polaris-cellular/
├── usbserial.ko
├── option.ko
├── cdc_acm.ko
└── qcserial.ko
```

If a subset is supplied, the loader still runs and warns about missing
modules but the missing `insmod` is non-fatal — you'll see cellular
enumerate only the modules that did get installed.

## 4. Running the patcher

```bash
# macOS / Linux
./patch-polaris.sh --fwpkt /path/to/FwPkt --cellular-modules ~/polaris-cellular
```

```powershell
# Windows (PowerShell)
.\patch-polaris.ps1 -FwPkt C:\path\to\FwPkt -CellularModules C:\polaris-cellular
```

The patcher will:

1. Run the normal libgphoto2 swap (or the `--ptp2-only` variant, if you set
   that flag).
2. Copy the four `.ko` files into `/app/komod/` with the same uid/gid/mode
   as the stock modules already there.
3. Install `cellular_load.sh` and `cellular_unload.sh` into `/app/komod/`
   with the same perms as the stock `sp_usb2net_load.sh` template.
4. Append one line to `/app/bootapp` so that immediately after the stock
   `cd /app/komod && ./sp_load3559v200 -i` line, the boot also runs
   `cd /app/komod && ./cellular_load.sh`. The insertion is idempotent — a
   re-patch is a no-op for the bootapp change.
5. Repack `appfs.ubifs` and rebuild the `FwPkt.zip`.

When `--cellular-modules` is **omitted**, the patcher still places the
two loader scripts and wires `cellular_load.sh` into `bootapp`; the loader
will then exit 0 immediately on next boot (it is a no-op when no Quectel /
Sierra device is present).

## 5. On-device verification

After flashing, log in over the Polaris' serial console (or via the on-device
shell if your unit has it enabled) and check:

```sh
# Did the four modules load?
lsmod | grep -E 'usbserial|option|qcserial|cdc_acm'

# Did the modem enumerate?
ls /dev/ttyUSB*

# Is pppd running?
ps | grep pppd

# Look at the loader's own log if anything looks off
dmesg | grep -iE 'usbserial|qcserial|option|cdc_acm|quectel'
```

A working cellular boot looks like this in `dmesg`:

```
usbcore: registered new interface driver usbserial
usbserial: USB Serial Driver core
USB Serial support registered for Qualcomm USB modem
qcserial 1-1:1.0: Qualcomm USB modem converter detected
usb 1-1: Qualcomm USB modem converter now attached to ttyUSB0
usb 1-1: Qualcomm USB modem converter now attached to ttyUSB1
...
```

The exact `/dev/ttyUSB*` numbering varies by modem firmware; the loader
insmod's `qcserial` last so the Quectel-specific mapping wins over the
generic `option` mapping.

## 6. Reverting the cellular patch

Re-flash your **stock** `FwPkt`. The patcher does not modify `rootfs.ubifs`,
U-Boot, or anything outside `appfs.ubifs`; the cellular feature is
fully reversible by restoring the factory `appfs.ubifs`.

## 7. Files added or modified

- `container/cellular_load.sh` — VID-gated `insmod` of the four modules.
- `container/cellular_unload.sh` — symmetric `rmmod` (strict reverse order).
- `container/patch.sh` — new section 7a, with bootapp wiring.
- `patch-polaris.sh` / `patch-polaris.ps1` — new `--cellular-modules` /
  `-CellularModules` flag.
- `README.md` — new "Phase 3 — Cellular" section + new row in the options
  table.
- `CHANGELOG.md` — new "Unreleased — Phase 3 cellular" entry.

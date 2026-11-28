# K-01 attached to the Polaris: the documented root cause is wrong

**Date:** 2026-11-28
**Device:** `polaris_d13e86`, `FwVer:6.0.0.54.119;date:2026.11.27`, armv7l
**Camera:** Pentax K-01, physically attached to the Polaris USB port
**Issues:** #378 (investigation), #379 (integration fix), #380 (X18 subcommands)

This closes the evidence #379 asked for: kernel sg enumeration, the actual
pgphoto-selected model and port, loaded module hashes, and a fresh application
setting read. It also **refutes** the root cause recorded in
`ROADMAP.md`/`INVESTIGATION.md`, so those must not be used to plan the fix.

## The two recorded theories are both false on this device

`PrivateResearch/investigations/issue-378-k01-firmware/ROADMAP.md` (Phase B) says:

> **Root cause:** Clog.txt shows pgphoto is loading libgphoto2 **2.5.27** (system),
> not **2.5.34** (Stage-2 build) … The Stage-2 loader reports
> `CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34` but pgphoto is actually loading
> camlibs from `2.5.27.1` where pentax has value `null`.
> **Fix needed:** Ensure pgphoto loads camlibs from `/app/lib/stage2/libgphoto2/2.5.34/`

Measured on the live device, both halves are wrong:

| Claim | Measured | Verdict |
|---|---|---|
| pgphoto loads 2.5.27.1 | `CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34`, `IOLIBS=…/0.12.2` in `/proc/4860/environ`; `/proc/4860/maps` shows only `/app/lib/stage2/libgphoto2.so.6` and `libgphoto2_port.so.12` | **False** — Stage-2 is loaded correctly |
| pentax camlib missing / null in 2.5.34 | `pentax.so` present in **both** trees, identical MD5 `88d9c00abdeb48ae5c67733c48487f9c`; contains model string `Pentax:K01` | **False** — nothing is missing |
| init fails with `-7` (PTP I/O Error) | `sp_Gphoto_Init ret -105` = `GP_ERROR_MODEL_NOT_FOUND` (`gphoto2/gphoto2-result.h:59`) | **Different error** |

The `2.5.27.1` lines in Clog are a red herring: they are the *system* pgphoto's
enumeration, and the newest Clog (`Clog_000047.log`, mtime 2026-11-28 10:31) was
**not** written by my probe at 12:46:57Z — no process holds it open, and its
timestamps (14:39) run ahead of device time (11:43), so RTC is unset and those
lines are not attributable to the current session. Planning a fix against them
would target a path that is not executing.

## Actual root cause: the Polaris kernel has no SCSI generic layer

`libgphoto2_port/usbscsi/linux.c` enumerates ports by opening
`/sys/class/scsi_generic` and reading `modalias` from each entry:

```c
dir = gp_system_opendir ("/sys/class/scsi_generic");   /* gp_port_library_list() */
snprintf (path, …, "/sys/class/scsi_generic/%s/device/../../../modalias", sg);
```

On the Polaris that directory is empty, so **no `usbscsi` port is ever offered**,
the `Pentax:K01` ability row can never match a port, and detection returns
`GP_ERROR_MODEL_NOT_FOUND`.

| Check | Result |
|---|---|
| `ls /sys/class/scsi_generic/` | **empty** (0 entries) |
| `ls /dev/sg*` | **0 nodes** |
| `/proc/devices` major 21 (`SCSI generic`) | **absent** (only `252 bsg`) |
| `/proc/modules` | no `sg`, no `scsi` lines |
| `find / -name 'sg.ko*'` | **0 files**; `/lib/modules/` has **0** directories |

The kernel was built without `CONFIG_SCSI_GENERIC` and there is no loadable
module, so this cannot be fixed at runtime with `modprobe`. The K-01 is bound to
`usb-storage` instead:

```
25fb:0130  product "K-01"   bInterfaceClass=08 (Mass Storage)
/sys/block/sda             vendor "PENTAX"  model "DSC_K-01"  removable=1 size=0
driver -> .../usb/drivers/usb-storage
/proc/scsi/scsi            Host: scsi0  Vendor: PENTAX  Model: DSC_K-01  Rev: 1.05
```

`size=0` is expected — the K-01 speaks SCSI for camera control, not as a disk.
The SCSI transport therefore exists at the kernel level; only the generic-chardev
interface libgphoto2 needs is missing.

## Fresh application setting read (the qualification #379 required)

`scripts/canary-probe.py --probe`, 2026-11-28T12:46:57Z, against the attached K-01:

```
TX 1&286&2&-100#
RX 286@manufacturer:none;model:none;state:-105;storage:0;photoFormat:0;#
SUMMARY model=none state=-105 photoFormat=0
```

`model:none` and `state:-105` reproduce on every attempt (3 of 3 in Clog, plus
two fresh probe runs at 12:02:59Z and 12:46:57Z). An installed packet alone does
not qualify this route — the route is not reachable at all.

## Module hashes (dual-path match holds)

```
88d9c00abdeb48ae5c67733c48487f9c  /app/lib/stage2/libgphoto2/2.5.34/pentax.so
88d9c00abdeb48ae5c67733c48487f9c  /app/lib/libgphoto2/2.5.27.1/pentax.so
e3f295b3124396e00d961e159be4f1ea  /app/lib/stage2/libgphoto2.so.6
e3f295b3124396e00d961e159be4f1ea  /app/lib/libgphoto2.so.6
```

`usbscsi.so` is present in both port trees (`…/libgphoto2_port/0.12.2/usbscsi.so`
and `0.12.0/`), so the driver shipped — it simply has no device to enumerate.

## Why PR #168 cannot help here

PR #168 (merged 2026-11-22, `0f2f34e00`) gates the `Pentax 645D (PTP Mode)`
ability row so the USB-SCSI backend can discover a K-01 in MSC mode. That is
correct and it fixed the PC case — but on the Polaris the USB-SCSI backend has no
port to bind to, so removing the shadowing row changes nothing. The PC result
does not transfer: the PC has `/dev/sg2`, the Polaris has no sg layer at all.

## Feasible fix direction (verified feasible, not yet implemented)

`bsg` **is** present and exposes the same SCSI device:

```
/dev/bsg/0:0:0:0            crw-rw---- root root 252, 0
/sys/class/scsi_device/     0:0:0:0
```

`gp_port_usbscsi_open()` opens whatever path it is given and issues `SG_IO`,
which `bsg` supports — so the open/io half already works unchanged. Only
enumeration needs adapting, and the required `modalias` is reachable at the same
relative depth from `scsi_device`:

```
/sys/class/scsi_device/0:0:0:0/device -> …/usb1/1-1/1-1.2/1-1.2:1.0/host0/target0:0:0/0:0:0:0
/sys/bus/usb/devices/1-1.2:1.0/modalias = usb:v25FBp0130d0105dc00dsc00dp00ic08isc06ip50in00
```

`usbscsi.c`'s older-kernel fallback (`device/../../../modalias`) lands exactly on
that interface directory, so a `scsi_generic` → `scsi_device` enumeration
fallback plus `/dev/bsg/<host:target:lun>` as the port path is a small, local
change. It has **not** been implemented or tested; treat it as a candidate.

## What this changes for #378/#379/#380

- **#379 stays open**, but its blocker is not "pgphoto loads the wrong camlib".
  It is that the Polaris kernel exposes no SCSI generic interface, so no
  `usbscsi` port exists to match `Pentax:K01`.
- **Phase A results do not qualify the Polaris route.** They were measured on a
  PC with `/dev/sg2`; the same code path has no transport here.
- **#380 (X18 subcommands)** cannot be probed on the Polaris until a SCSI port
  exists at all — it is blocked behind #379, not independent of it.
- Any K-01 claim must state which host it was measured on. "K-01 works" is true
  on a PC and false on the Polaris, for different reasons.

## Reproduce

```sh
nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes'          # polaris_d13e86
ssh root@192.168.0.1 'cat /app/FwVer; ls /sys/class/scsi_generic/ | wc -l; \
                      grep -cE "^ *21 " /proc/devices'  # 0 and 0
python3 scripts/canary-probe.py --probe                 # state:-105 model:none
```

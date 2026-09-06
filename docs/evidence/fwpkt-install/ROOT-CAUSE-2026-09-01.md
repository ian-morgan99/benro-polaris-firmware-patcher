# Root cause — why camera-side install is skipped (2026-09-01)

## Setup
- Gimbal awake, polestar_app PID 248, FwPkt.zip (68,484,216 bytes) staged at `/app/sd/FwPkt.zip`
- Mlog_000018 captured live

## Direct evidence from Mlog_000018
```
12:34:24:243 SP_EVENT_SD_PLUGED
12:34:24:261 SP_EVENT_SD_MOUNTED
12:34:25:730 SP_EVENT_SD_SCAN      ← 0x405 fired
                  (then silent — nothing happens)
```
6+ hours of running. **0x402 NEVER fired. 0x403 NEVER fired. Only 0x405 fired (on boot).**
Only one 810 protocol message in the entire boot: a temperature telemetry (0x525) at 18:13.

## What 0x405 actually does
SP_EVENT_SD_SCAN (case 0x405 at 0x3f8fc) calls:
- `SP_ExdevUpgradeFromSD` (0x5d89c) — looks for `/app/sd/FwPkt/gimbal/*.bin`
- `SP_OmsUpgradeFromSd` (0x77cf4) — looks for `/app/sd/FwPkt/camera/*`

## What 0x402 does
Case 0x402 at 0x3f790 calls `HI_system` to run a shell command, then posts 0x403 if
the command returns 0. The shell command is one of the 4 known commands:
`rm -r /app/sd/FwPkt` | `unzip /app/sd/FwPkt.zip -d /app/sd/` |
`rm -r /app/sd/FwPkt.zip` | `/app/getFwInfo.sh`.

`unzip` is the one that creates `/app/sd/FwPkt/{gimbal,camera}/`.

## Why nothing happens
1. On boot, the SD watcher fires 0x405 (SP_EVENT_SD_SCAN) directly
2. The watcher's scan finds `/app/sd/FwPkt.zip` but does NOT extract it
3. It only scans for the EXTRACTED directory layout
4. `/app/sd/FwPkt/gimbal/` and `/app/sd/FwPkt/camera/` don't exist → silent no-op
5. 0x402 only fires when the iPhone/Android app sends a 810 command telling
   polestar_app to extract the zip (via the `unzip ...` shell command)

## What we need to do
- **DO NOT** just stage FwPkt.zip and reboot — that path is broken by design.
  The padded zip sitting in `/app/sd/FwPkt.zip` for 12+ hours proves this.
- Either:
  (a) **Pre-extract the zip to `/app/sd/FwPkt/{gimbal,camera}/` before boot
      (or before inserting the SD card)** — this is the path the on-boot
      scanner actually reads, and it is the path the **Benro website now
      instructs end-users to take** (the 2026-09-06 revision of the
      Polaris download page at `https://www.benro.com/en/downloads/product/
      benro-polaris.html` reads: *"Unzip the package you downloaded and
      then move the folders to SD card"*). "The folders" is the plural
      form because the zip contains exactly one top-level folder `FwPkt/`
      plus its `camera/`, `gimbal/` sub-folders — Benro is referring to
      the entire extracted `FwPkt/` tree, moved as a unit to the SD card
      root, **not** its contents flattened onto the root. SD card root must
      end up as `/app/sd/FwPkt/{firmwareInfo,camera,gimbal}/…` — *not*
      `/app/sd/{firmwareInfo,camera,gimbal}/…`. See §"What 'move the
      folders' actually means" below. The website is finally telling users
      to do what the firmware already expected.
  (b) Send the 810 protocol message that triggers 0x402 (unzip command) —
      i.e. trigger the on-board `unzip /app/sd/FwPkt.zip -d /app/sd/`
      step from the Benro app side, which leaves the zip on the SD card.
  (c) Trigger 0x402 by other means (e.g. SD card unplug/replug? Hot-add a
      FwPkt directory? The `getFwInfo.sh` script?)

### Vendor alignment (2026-09-06)

Prior to 2026-09-06, the Benro Polaris download page at
`https://www.benro.com/en/downloads/product/benro-polaris.html` told
users to *"Click the link and download the newest Polaris firmware
package"* and then implicitly drop the zip on the SD card (the prior
wording was ambiguous about whether the zip or the extracted folders
went on the card). On 2026-09-06 the page was revised to be explicit:

> 1. Click the link and download the newest Polaris firmware package;
> 2. **Unzip the package you downloaded and then move the folders to
>    SD card;**
> 3. Insert your SD card into Polaris and power it on …

This is the same layout contract the on-board updater's `0x405`
`SP_EVENT_SD_SCAN` reads on plain boot (`/app/sd/FwPkt/gimbal/*.bin`
and `/app/sd/FwPkt/camera/*`). The vendor doc and the firmware are
now in agreement; the disagreement the project worked around (zip
staged at `/app/sd/FwPkt.zip` and ignored for 12+ hours) was a
**user-instruction bug** in the vendor doc, not a firmware bug.

If a future session sees the vendor revert to "drop the zip on the
card" wording, treat it as the old instruction set and re-stage the
pre-extracted `FwPkt/` folder on the SD card. The vendor wording
should not be the source of truth; the firmware behaviour at 0x405
should be.

### What "move the folders" actually means (resolving the ambiguity)

The 2026-09-06 vendor wording *"Unzip the package you downloaded
and then move the folders to SD card"* is intentionally loose;
*"the folders"* is plural because the unzipped payload contains
**one top-level folder `FwPkt/`** plus its `camera/`, `gimbal/`
sub-folders. The contract is unambiguous on the device side: every
firmware-side path string hardcodes the `FwPkt/` prefix (see
`docs/POLESTAR_APP_REVERSE_ENGINEERING.md` §13.5 and §13.6 and the
table in [§"The FwPkt/ prefix is mandatory"](../../fwpkt-zip-layout-and-smb-delivery.md)).

The **only correct SD-card layout** for option (a) is therefore:

```
SD card root
└── FwPkt/                       ← the folder that was inside the zip
    ├── firmwareInfo
    ├── camera/
    │   ├── appfs.ubifs
    │   ├── config
    │   ├── rootfs.ubifs
    │   └── uImage
    └── gimbal/
        ├── polaris403_<ver>.bin
        └── polaris413_<ver>.bin
```

What you should **not** do (this silently no-ops, like the dropped-zip
case):

- ❌ Move `FwPkt.zip` to the SD card root (the on-boot scanner walks
  the **directory tree**, not the zip; only the 810 app trigger runs
  `unzip`).
- ❌ Move `FwPkt/camera/`, `FwPkt/gimbal/`, `FwPkt/firmwareInfo` to
  the SD card **root** (drops the `FwPkt/` prefix → `SP_ExdevUpgradeFromSD`
  looks for `/app/sd/FwPkt/gimbal/*.bin`, will not find anything at
  `/app/sd/gimbal/*.bin` → silent reject).
- ❌ Move the zip and also a stale half-extracted `FwPkt/` left over
  from a prior 810 run (the 810 state machine begins with
  `rm -r /app/sd/FwPkt`, so a stale dir will be wiped before the
  unzip, but only on the 810 path — on plain boot, a stale dir is
  scanned as-is and any `firmwareInfo` MD5 mismatch in the stale
  tree will silent-reject the upgrade; always delete any stale
  `FwPkt/` on the SD card before staging the new one).

The host-side equivalent (what `container/validate_fw_package.py`
already enforces, see
[`fwpkt-zip-layout-and-smb-delivery.md` §1](../../fwpkt-zip-layout-and-smb-delivery.md)):
the validator exits non-zero with "top-level layout must contain
exactly one entry, `FwPkt/`" if either the zip or the extracted
tree does not have `FwPkt/` at its root. The user's SD card should
mirror that structure verbatim.

## Open questions (still unknown)
- Which 810 protocol code triggers 0x402? Need to look at the SP_EventPub(0x402)
  caller at 0x325d8.
- What is the full sequence the Benro app performs on firmware upload?
  (openpolaris's docs/evidence/capability-guide.md describes it but it
  hasn't been tested end-to-end.)
- Will 0x402 fire automatically if the SD card is re-plugged after
  boot? Or only on the 810 protocol path?

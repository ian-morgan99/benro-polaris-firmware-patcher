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
  (a) Pre-extract the zip to `/app/sd/FwPkt/{gimbal,camera}/` before boot
  (b) Send the 810 protocol message that triggers 0x402 (unzip command)
  (c) Trigger 0x402 by other means (e.g. SD card unplug/replug? Hot-add a
      FwPkt directory? The `getFwInfo.sh` script?)

## Open questions (still unknown)
- Which 810 protocol code triggers 0x402? Need to look at the SP_EventPub(0x402)
  caller at 0x325d8.
- What is the full sequence the Benro app performs on firmware upload?
  (openpolaris's docs/evidence/capability-guide.md describes it but it
  hasn't been tested end-to-end.)
- Will 0x402 fire automatically if the SD card is re-plugged after
  boot? Or only on the 810 protocol path?

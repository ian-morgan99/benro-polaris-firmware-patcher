# Polaris Upgrade Function Map

Source: `dwarf_lines.py` against `polestar_app.original` (24.9 MB ARM ELF, 108k symbols).

## FwPkt path (Gimbal, the main update flow)

| Addr              | Symbol                         | Source file / range       | Purpose |
|-------------------|--------------------------------|---------------------------|---------|
| 0x0004dfb0..0x4e050 | SP_PushUpgradeState            | sp_msgProc.c              | Push upgrade state to app via 810 |
| 0x0005b9d8..0x5b9fc | SP_GetGimbalUpgradeInfo        | sp_gimbalUpgrade.c        | Stub: get current upgrade state |
| 0x0005c488..0x5c78c | SP_CreateGimbalUpgradePthread  | sp_gimbalUpgrade.c        | Thread: search SD for new FwPkt |
| 0x0005ccfc..0x5cdc4 | SP_ExDevFwPktCheck             | sp_exDevUpgrade.c:304..   | Check ExDev (extended-device) FwPkt |
| 0x0005cdc4..0x5d6bc | SP_SrchExdevNewPkt             | sp_exDevUpgrade.c         | Search for ExDev new FwPkt |
| 0x0005d6bc..0x5d764 | SP_PushExdevUpgradeStateToApp  | sp_exDevUpgrade.c         | Push ExDev state to app |
| 0x0005d860..0x5d89c | SP_CreateExdevUpgradeLedTask   | sp_exDevUpgrade.c         | LED task during ExDev upgrade |
| 0x0005d89c..0x5daf4 | SP_ExdevUpgradeFromSD          | sp_exDevUpgrade.c         | Trigger ExDev upgrade from SD |
| 0x0005e4f4..0x5e6b8 | SP_CreateGimbalUpgradePthread  | sp_gimbalUpgrade.c        | (Gimbal-side) search SD for FwPkt |
| 0x0005e6b8..0x5eb24 | SP_UartRcvGimbalUpgradeMsgProc | sp_gimbalUpgrade.c:204..  | UART msg handler for gimbal upgrade (810 side) |
| 0x0005eb24..0x5f424 | SP_SrchGimbalNewPkt            | sp_gimbalUpgrade.c:268..  | Core: search gimbal for new FwPkt.zip |
| **0x0014023c..0x140990** | **SP_UpgradeCheckFw**     | sp_upgrade.c:438..        | **Run rm/unzip/rm/getFwInfo.sh, MD5-verify 4 files** |
| 0x0013f804..0x13fc58 | SP_GetDeviceVer                | sp_upgrade.c:298..        | Get gimbal HwVer/FwVer from struct |
| 0x0013fc58..0x13fc.. | SP_PushDeviceVer               | sp_upgrade.c:348..        | Format `hw:%s;sw:%s;...` and push |

## OmsPkt path (OMS — operates on `/app/sd/OmsPkt.zip`)

| Addr              | Symbol                          | Source / range            | Purpose |
|-------------------|---------------------------------|---------------------------|---------|
| **0x000768e8..0x76f24** | **SP_OmsUpgradeMsgProc**   | sp_oms.c:495..            | **810 protocol message dispatcher (the gate)** |
| **0x00076f24..0x7787c** | **SP_OmsUpgradeCheckFwPkt** | sp_oms.c:575..            | **Run rm/unzip/rm/getOmsFwInfo.sh, MD5-verify OmsPkt files** |
| 0x0007787c..0x77944 | SP_OmsUpgradePushDeviceVer      | sp_oms.c                  | Push OMS device version |
| 0x00077944..0x779a0 | SP_OmsUpgradeSetStep            | sp_oms.c                  | Set OMS upgrade step |
| 0x000779a0..0x77a48 | SP_OmsUpgradePush               | sp_oms.c                  | Push OMS update to app |
| 0x00077c90..0x77cf4 | SP_OmsUpgradePushResult         | sp_oms.c                  | Push upgrade result to app |
| **0x00077cf4..0x77da4** | **SP_OmsUpgradeFromSd**   | sp_oms.c:750..            | **SD card entry point: open /app/sd/OmsPkt.zip** |

## OmsPkt install flow

```
SD card hot-plug or app upload
        ↓
SP_OmsUpgradeFromSd()  ← reads /app/sd/OmsPkt.zip
        ↓
SP_OmsUpgradeMsgProc()  ← 810 protocol gate, dispatches subcommand
        ↓
SP_OmsUpgradeCheckFwPkt()  ← 4× HI_system() (rm, unzip, rm, getOmsFwInfo.sh) + 4× CrcMd5()
        ↓
  (on success) → install via existing U-Boot firmware path
```

## FwPkt install flow (the one we care about)

```
SP_SrchGimbalNewPkt()  ← polls for new FwPkt.zip somewhere
        ↓
SP_UpgradeCheckFw()  ← 4× HI_system() (rm, unzip, rm, getFwInfo.sh) + 4× CrcMd5()
        ↓
  (on success) → SP_PushDeviceVer() → SP_PushUpgradeState()
```

## Two-tier structure

There is a **gimbal side** (sp_gimbalUpgrade.c, sp_exDevUpgrade.c, sp_upgrade.c)
and an **OMS side** (sp_oms.c). Both have the same `check → unzip → md5 → push state`
pattern but for different files: `/app/sd/FwPkt.zip` (gimbal) vs `/app/sd/OmsPkt.zip` (OMS).

The two-tier design suggests the upgrade may proceed in **two phases**:
1. OMS upgrade first (over `/app/sd/OmsPkt.zip` — updates the OMS/4G cellular module firmware)
2. Gimbal upgrade second (over `/app/sd/FwPkt.zip` — updates the gimbal STM32 firmware)

This matches the hypothesis: the gimbal-side install is waiting for the OMS-side install
to complete (or vice versa).

## SD card watch path

`SP_SrchGimbalNewPkt()` is the candidate watcher function. The path it polls must be
determined. The polestar_app uses a **symlink** `/app/sd` (verified via ssh) that points
to the real SD mount. The real path may be `/app/sdcard/`, `/mnt/mmcblk0p1/`, or similar.

## 810 protocol subcommand dispatch

`SP_OmsUpgradeMsgProc` (sp_oms.c:495..) handles 810-protocol upgrade messages.

Bytes parsed:
- byte 1 == 0x64 (100, the upgrade opcode)
- byte 2 high nibble: 0xf0, 0xf1, 0xf2 (subcommand class)
- payload bytes: command-specific

Subcommands:
- 0xf1 — start / cancel / etc. (multiple sub-commands)
- 0xf2 — data / finish / etc.

This is the gate that decides whether an upgrade proceeds. Without going through this
gate, SP_OmsUpgradeCheckFwPkt is never called.

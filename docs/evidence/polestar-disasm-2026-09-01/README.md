# Disassembly Evidence — Quick Reference for Handover

**Date:** 2026-09-02
**Subject:** Reverse-engineering the `polestar_app` ARM ELF for cross-vendor firmware upgrade support
**Target binary:** `artifacts/polestar_app/polestar_app.original` (24.9 MB ARM ELF, 108k symbols)

---

## TL;DR for next agent

There are **FOUR confirmed upgrade trigger paths** in the polestar firmware:

1. **himm() trigger** — write 0x100 to register at 0x12020000
   (`himm 0x12020000 0x100` via /sbin/devmem)
2. **byte=0x21 gimbal UART message** — sent from gimbal MCU → polestar ARM,
   dispatched by `GimbalUartRxMsgProcTask@0x60620` case 0x21
3. **byte=0x61 gimbal UART message** — same function, case 0x61
   (also calls SP_GetGimbalExFwTask @ 0x13ef98)
4. **byte=0x63 / 0x64 gimbal UART messages** — same dispatcher
   (full handler bodies not yet transcribed, see file 08)

**A FIFTH trigger exists via the SD card hotplug path:**
- `EventMsgProc@0x3f610` case `SP_EVENT_SD_MOUNTED` (at 0x3f91c)
  calls `bl 0x5d89c` (SP_ExdevUpgradeFromSD, r0=2) automatically
  whenever the SD card is mounted at /app/sd. See file 08 for details.

The UART trigger paths (0x21, 0x61) call `SP_GetGimbalExFwTask@0x13ef98`
which spawns `GetExFwTask@0x13eed4` as a pthread. **GetExFwTask does the actual upgrade.**

The SD_MOUNTED path calls `SP_ExdevUpgradeFromSD@0x5d89c` directly.

The **fatal flaw** (UART path) is that GetExFwTask only loops while
`obj->field_4b0 == 0` (UpgradeTask not running). Once field_4b0 is set
(by a successful SP_UpgradeCheckFw call), GetExFwTask exits. Without
SP_CreateUpgradeTask being called first, field_4b0 stays 0 forever —
which is the case currently on the device.

---

## File index

| File | Purpose |
|------|---------|
| [00-HANDOVER-2026-08-31.md](00-HANDOVER-2026-08-31.md) | Prior handover from 2026-08-31 (copied from OpenPolaris repo) |
| [00-MANIFEST-2026-08-31.md](00-MANIFEST-2026-08-31.md) | Manifest of evidence files in OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/ |
| [01-upgrade-task-table.md](01-upgrade-task-table.md) | The 8-entry task table at VA 0xc5a250 |
| [02-obj-fields-and-state-machine.md](02-obj-fields-and-state-machine.md) | obj struct fields, 8-state machine |
| [03-sp-create-upgrade-task.md](03-sp-create-upgrade-task.md) | SP_CreateUpgradeTask + UpgradeTask analysis |
| [04-plt-got-mechanism.md](04-plt-got-mechanism.md) | PLT/GOT, switch dispatchers, literal pool stub trick |
| [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) | **THE TRIGGER COMMANDS** + pivot options A through E |
| [06-strings-and-logs.md](06-strings-and-logs.md) | Decoded log strings, error messages |
| [07-gimbal-uart-rx-thread.md](07-gimbal-uart-rx-thread.md) | Full byte=0x21 trigger chain analysis |
| [08-exdev-uart-upgrade-path.md](08-exdev-uart-upgrade-path.md) | **NEW** — Full call graph, EventMsgProc event table, SD_MOUNTED path, 0x61/0x63/0x64 trigger bytes |

## Critical addresses (verified, file offsets)

| Addr (VA) | File offset | Purpose |
|-----------|-------------|---------|
| 0x13eed4 | 0x12eed4 | GetExFwTask (size 196) |
| 0x13ef98 | 0x12ef98 | SP_GetGimbalExFwTask (size 80) |
| 0x13f080 | 0x12f080 | UpgradeTask (size 836) |
| 0x13f3c4 | 0x12f3c4 | SP_CreateUpgradeTask (size 156) |
| 0x3f130 | 0x2f130 | SP_SdMountHandler2 (called from SD_MOUNTED) |
| 0x3f214 | 0x2f214 | SP_SdMountHandler1 (called from SD_MOUNTED, SD_SCAN) |
| 0x3f610 | 0x2f610 | EventMsgProc (size 3144) |
| 0x3f91c | 0x2f91c | EventMsgProc case SP_EVENT_SD_MOUNTED body |
| 0x3f8cc | 0x2f8cc | EventMsgProc case SP_EVENT_SD_SCAN body |
| 0x4042c | 0x3042c | SP_SdMountHandler4 (called from SD_MOUNTED) |
| 0x423b4 | 0x323b4 | SP_SdMountHandler3 (called from SD_MOUNTED) |
| 0x60620 | 0x50620 | GimbalUartRxMsgProcTask (size 7568) |
| 0x6099c | 0x5099c | Switch dispatcher in GimbalUartRxMsgProcTask |
| 0x60b2c | 0x50b2c | Case 0x21 (gimbal ex-fw trigger) |
| 0x60b94 | 0x50b94 | Case 0x61 cmp (gimbal ex-fw trigger) |
| 0x60bb0 | 0x50bb0 | bl SP_GetGimbalExFwTask (target of 0x21 / 0x61) |
| 0x62934 | 0x52934 | GimbalUartInitTask (size 324) |
| 0x62a78 | 0x52a78 | SP_GimbalUartInit (size 68) |
| 0x5d89c | 0x4d89c | SP_ExdevUpgradeFromSD |
| 0x77cf4 | 0x67cf4 | SP_AfterExdevUpgrade (helper) |
| 0x76f24 | 0x66f24 | SP_OmsUpgradeMsgProc (810 protocol gate) |
| 0xbf3000 | 0xbd3000 | GLOBALS (in .got) |
| 0xc5a250 | 0xc3a250 | Upgrade task table (8 entries) |
| 0xc47148 | — | GLOBALS[0x1310] -> obj pointer |

## Segment mapping (verified, critical for all string/VA lookups)

The ELF has two LOAD segments:

| Segment | File offset | Virtual addr | Notes |
|---------|-------------|--------------|-------|
| LOAD 0 (R+X) | `0x000000` | `0x0010000` | Covers .text + .rodata + .ARM.extab + .ARM.exidx |
| LOAD 1 (R+W) | `0xbb7100` | `0xbd7100` | Covers .data, .bss |

**For all read-only sections (text, rodata):** `file_offset = VA - 0x10000`
**For all read-write sections (data, bss):** `file_offset = VA - 0x200000`

Section ranges (verified via `readelf -l` and `readelf -S`):
- `.text`        VA 0x0022bc0 – 0x0a56c80  (file 0x0012bc0 – 0x0a46c80)
- `.rodata`      VA 0x0a56cc0 – 0x0b7ece8  (file 0x0a46cc0 – 0x0b6ece8)
- `.ARM.extab`   VA 0x0b7ece8 – 0x0bb5cec
- `.ARM.exidx`   VA 0x0bb5cec – 0x0bc6fe4
- `.data`        VA 0x0bd7100+ (R+W segment)
- `.bss`         VA 0x0c45f80 (NOBITS, size 0x1beef0)

**Common pitfall:** Strings inside `.text` (at VA 0x0a1xxxx range) are
**still code bytes**, not ASCII data. The first legitimate `.rodata`
section starts at VA `0x0a56cc0`.

## PLT entries (verified)

| PLT addr | Symbol |
|----------|--------|
| 0x206b0 | sleep@GLIBC_2.4 |
| 0x21658 | pthread_self@GLIBC_2.4 |
| 0x2245c | pthread_create@GLIBC_2.4 |
| 0x227f8 | pthread_detach@GLIBC_2.4 |
| 0x229e4 | usleep@GLIBC_2.4 |

## Live device state (verified 2026-09-02)

- IP: 192.168.0.1, SSH: root@192.168.0.1 (no password)
- polestar_app PID: 248, state: S (sleeping)
- /app/sd/FwPkt.zip: 68,484,216 bytes (staged)
- /app/sd/FwPkt/: EXTRACTED with gimbal/, camera/, crcInfo, firmwareInfo
- /app/sd/OmsPkt.zip: 68,484,216 bytes (staged)
- /app/sd/FwPkt/gimbal/polaris403_2.0.0.22.bin: 84,328 bytes
- /app/sd/FwPkt/gimbal/polaris413_2.0.0.22.bin: 84,284 bytes
- Gimbal: AWAKE (sending temp telemetry 0x525 every 30s)
- Last Mlog: 23:26:07 0x525 telemetry (no upgrade activity)
- /sbin/devmem: available (use himm wrapper)

## What to do first when resuming

1. **Verify state** — `ssh root@192.168.0.1 'ps -ef | grep polestar; tail -5 /app/Mlog.txt'`
2. **Check FwPkt** — `ls -la /app/sd/FwPkt/`
3. **Read the triggers file** — [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) section 7 (himm) and section 9 (byte=0x21)
4. **Choose a pivot option** from [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) section 9.7

## Key insight: the literal pool stub trick

The polestar passes **literal-pool data** as thread start routines
at addresses **8 bytes BEFORE** the real function. Those 8 bytes
decode to conditional ARM instructions (Z flag) which don't fire
in a fresh thread, so execution falls through.

Known instances:
- 0x60618 (Thread C) → falls through to GimbalUartRxMsgProcTask @ 0x60620
- 0x6292c (Init thread) → falls through to GimbalUartInitTask @ 0x62934

This is **deliberate obfuscation**, not a bug. See [04-plt-got-mechanism.md](04-plt-got-mechanism.md) section 5.

## Key insight: the signed literal pool

`ldr rN, [pc, #X]; add rN, pc, rN` uses **signed** literals. So
`0xfffff9c8` means `-0x638`, and `0x00be475c` means `+0xbe475c`.

When the literal + PC equals a small positive number, the result is
a BSS address (0x00c4xxxx range). When the literal is negative,
the result is a code address (0x005fxxxx to 0x006xxxxx range).

This is why the gimbal thread spawn at 0x62a14 mixes 0xfffff9c8
(-0x638, code) and 0x00be475c (BSS) in alternating pattern.

## Root cause: why nothing happens

The chain we need to fire:
1. GimbalMCU sends 0x21 to polestar (or himm writes 0x100)
2. `SP_GetGimbalExFwTask` spawns `GetExFwTask`
3. `GetExFwTask` polls and **waits for `obj->field_4b0 != 0`**
4. `obj->field_4b0` is set by `SP_CreateUpgradeTask` → which is **never called**
5. So GetExFwTask never completes; it just loops
6. Meanwhile, the SD watcher's 0x405 event calls the WRONG functions
   (ExdevUpgradeFromSD and OmsUpgradeFromSd) which both return
   silently because `/app/sd/FwPkt/{gimbal,camera}/` don't exist
   at the time the watcher runs

**Workaround:** Manually create `/app/sd/FwPkt/{gimbal,camera}/`
**before boot** so the watcher's 0x405 fires and finds the files.
This has been tried and the FwPkt directory IS already extracted,
but the watcher apparently still doesn't fire 0x402.

**The remaining unknown:** what specifically needs to happen for
UpgradeTask to start. Likely candidates:
- A successful CrcMd5 verification (which requires the watcher's
  full chain to run)
- A specific 810 protocol message (0x64 0xf0 0x01) that bypasses
  the watcher entirely

## NEW: SD_MOUNTED auto-trigger (the simplest path!)

Per [08-exdev-uart-upgrade-path.md](08-exdev-uart-upgrade-path.md) section 3,
`EventMsgProc@0x3f610` automatically fires case `SP_EVENT_SD_MOUNTED` (at
0x3f91c) whenever the SD card is mounted at /app/sd. The case calls
`bl 0x5d89c` (SP_ExdevUpgradeFromSD) with r0=2.

**This means**: simply unmounting and remounting the SD card (e.g.
`umount /app/sd; mount /app/sd`) should re-fire the SP_ExdevUpgradeFromSD
path. This is the **easiest pivot to test first** because:

1. It does not require gimbal MCU cooperation
2. It does not require any 810 protocol
3. It does not require writing to /sbin/devmem
4. It just requires the FwPkt files to exist at /app/sd/FwPkt/ (they DO)

The only unknown is whether the SD watcher (the one that posts
SP_EVENT_SD_MOUNTED) is even running on the device, and what
filesystem path it watches. See file 08 section 9.3.

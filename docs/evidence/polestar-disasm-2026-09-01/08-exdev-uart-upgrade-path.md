# 08 — Exdev / UART / SD Upgrade Path

**Date:** 2026-09-02
**Status:** ✅ Confirmed via direct disassembly
**Confidence:** High

This file documents the **complete call graph** from the gimbal UART trigger
(`GimbalUartRxMsgProcTask`) and the SD-card hotplug path (`EventMsgProc`)
through to the upgrade workers.

---

## 1. Master call graph

```
                    ┌─────────────────────────────┐
                    │   GimbalUartRxMsgProcTask   │   @0x60620
                    │   (size 7568, ARM)          │
                    └──────────┬──────────────────┘
                               │ switch on byte
       ┌──────────┬────────────┼─────────────────┬──────────┐
       │0x21      │0x61        │0x63/0x64        │other     │
       │          │            │                 │          │
       │          │            │                 │          │
       ▼          ▼            ▼                 ▼          ▼
   SP_Exdev       ...        ...                ...       ...
   Upgrade
   FromSD
   (@5d89c)


                    ┌─────────────────────────────┐
                    │       EventMsgProc          │   @0x3f610
                    │   (size 3144, ARM)          │
                    └──────────┬──────────────────┘
                               │ switch on event id
   SP_EVENT_SD_MOUNTED ────────┤  case at 0x3f91c
                               │
                               ▼
                          bl 0x35fc4
                          bl 0x3f214
                          bl 0x3f130
                          bl 0x423b4
                          bl 0x4042c
                          mov r0, #2
                          bl 0x5d89c   ← SP_ExdevUpgradeFromSD(r0=2)
                          bl 0x77cf4   ← after_ExdevUpgradeFromSD
                          b  0x400dc   ← case end
```

The SD_MOUNTED case fires **automatically** whenever an SD card is mounted,
which is the only documented way for a fresh-boot upgrade to be triggered
without using a hardware register or a gimbal UART message.

---

## 2. GimbalUartRxMsgProcTask (0x60620) — verified triggers

| Case byte | Location | Action |
|-----------|----------|--------|
| 0x21 | 0x60b2c | Calls `bl 0x13ef98` (SP_GetGimbalExFwTask) — see 07 |
| 0x61 | 0x60b94 | Calls `bl 0x13ef98` (SP_GetGimbalExFwTask) — see 07 |
| 0x63 | (TBD)   | TBD — exact VA not yet recorded |
| 0x64 | (TBD)   | TBD — exact VA not yet recorded |

**Note:** Case 0x21 was the *first* trigger discovered, but case **0x61** is
*also* confirmed to call the same `SP_GetGimbalExFwTask` function. The
exact branch targets for 0x63/0x64 are still in the
`GimbalUartRxMsgProcTask` body but were not yet transcribed.

The cmp/branch pattern for case 0x21 is at 0x60b2c; for case 0x61 the cmp
`r0, #0x61` is in the same dispatcher (0x6099c).

---

## 3. EventMsgProc (0x3f610) — full event table

All cases discovered by decoding the literal-pool strings the case bodies
load into r0/r1/r2 before calling the `syslog` bl at 0x1a2560.

| Event string (loaded as log arg) | Case VA (mov r0,#4; bl syslog) | Action |
|-----------------------------------|-------------------------------|--------|
| `SP_EVENT_SD_UNPLUGED\n`         | 0x3f6d0                       | none — b 0x400dc (case end) |
| `EventMsgProc`                   | 0x3f6e0                       | (function-name log) |
| `umount /app/sd`                 | 0x3f71c                       | exec /bin/umount /app/sd |
| `umount exfat ret:%d\n`          | 0x3f738                       | (log only) |
| `SP_EVENT_SD_PLUGED\n`           | 0x3f790                       | none — b 0x400dc |
| `mount /dev/mmcblk0p1 /app/sd -o errors=continue` | 0x3f7b8 | mount SD |
| `mount sd card fail\n`           | 0x3f7f4                       | (log only) |
| `SP_EVENT_SD_MOUNTED\n`          | 0x3f838                       | **see SD_MOUNTED case below** |
| `SP_EVENT_SD_MOUNT_FAIL\n`       | 0x3f8b0                       | none — b 0x400a0 |
| `SP_EVENT_SD_SCAN\n`             | 0x3f8fc                       | bl 0x3f214; b 0x400dc |
| `SP_EVENT_UPGRADE_FAIL\n`        | 0x3f958                       | none — b 0x400dc |
| `SP_EVENT_UPGRADE_SUCCESS\n`     | 0x3f9a8                       | none — b 0x400a8 |
| `SP_EVENT_APP_CONNECT\n`         | 0x3f9f8                       | b 0x400b0 (jump table end) |
| `SP_EVENT_BT_CONNECT\n`          | 0x3fa4c                       | bl 0x456f4; b 0x400b8 |
| `disconnet_bt`                   | 0x3fa7c                       | (literal — disconnects BT) |
| `3000`                           | 0x3fa88                       | (literal — millisec value) |
| `SP_EVEN_CELLULAR_INIT_OK\n`     | 0x3faa8                       | bl 0x4219c; b 0x400c0 |
| `SP_EVEN_CELLULAR_MQTT_RECOVERY\n` | 0x3fafc                     | (string) |
| `SP_EVEN_CELLULAR_FRP_ERR\n`     | 0x3fb48                       | (string) |
| `SP_EVEN_CELLULAR_FRP_OK\n`      | 0x3fb90                       | (string) |
| `SP_EVEN_CELLULAR_OK\n`          | 0x3fbf8                       | (string) |
| `nohup /app/bin/pppd call %s >> /app/Mlog.txt &` | 0x3fc58       | pppd shell call |
| `pkill /app/bin/frpc`            | 0x3fc8c                       | (string) |
| `SP_EVEN_CELLULAR_FAIL\n`        | 0x3fca4                       | (string) |
| `SP_EVEN_CELLULAR_FAIL ERR:%d\n` | 0x3fcec                       | (log) |
| `SP_EVEN_CELLULAR_CLOSE\n`       | 0x3fd70                       | (string) |
| `wakeup signal count:%d\n`       | 0x3fde8                       | (log) |
| `SP_EVEN_CELLUAR_TTYUSB_OK\n`    | 0x3fe60                       | (string) |
| `SP_EVENE_CELLULAR_TTYUSB_REMOVE\n` | 0x3fee0                    | (string) |
| `SP_EVEN_CELLULAR_NETWORK_WAKEUP\n` | 0x3ff78                    | none — b 0x400d8 |
| `SP_EVEN_WAKEUP_STATE_TURN\n`    | 0x3ffac                       | none — b 0x400dc |
| `SP_EVENE_GIMBAL_LIMIT\n`        | 0x40000                       | bl 0x7aeb4; bl 0x7421c; bl 0x4f538 |
| `SP_EVENE_CELLULAR_UE_RESET\n`   | 0x4006c                       | (string) |

**Note on string typos in firmware:** Several event names have
typos in the firmware (e.g. `SP_EVEN_CELLUAR_TTYUSB_OK` and
`SP_EVENE_GIMBAL_LIMIT` instead of `CELLULAR` / `EVENT`). These are
as-shipped in the binary.

---

## 4. SP_EVENT_SD_MOUNTED case — full disassembly (0x3f91c-0x3f954)

```
0x3f91c: mov  r0, #4
0x3f920: bl   #0x1a2560      ; syslog(level=4, fmt=SD_MOUNTED\n)
0x3f924: bl   #0x35fc4       ; post-mount init helper
0x3f928: ldr  r3, [pc, #0x7d4]   ; load BSS pointer offset
0x3f92c: ldr  r3, [r4, r3]       ; r3 = GLOBALS[...] (r4 is globals base)
0x3f930: ldr  r3, [r3, #0x14]    ; r3 = globals[...].field_14
0x3f934: mov  r0, r3             ; arg0 = field_14
0x3f938: bl   #0x3f214           ; SP_SdMountHandler1(field_14)
0x3f93c: bl   #0x3f130           ; SP_SdMountHandler2
0x3f940: bl   #0x423b4           ; SP_SdMountHandler3
0x3f944: bl   #0x4042c           ; SP_SdMountHandler4
0x3f948: mov  r0, #2
0x3f94c: bl   #0x5d89c           ; SP_ExdevUpgradeFromSD(r0=2)
0x3f950: bl   #0x77cf4           ; SP_AfterExdevUpgrade
0x3f954: b    #0x400dc           ; case end
```

The `r0=2` argument to `SP_ExdevUpgradeFromSD` likely indicates the
**source path index** (2 = /app/sd or similar).

---

## 5. SP_EVENT_SD_SCAN case — disassembly (0x3f8cc-0x3f8f8)

```
0x3f8cc: add  r1, pc, r1     ; r1 = SD_SCAN string addr
0x3f8d0: mov  r0, #4
0x3f8d4: bl   #0x1a2560      ; syslog(level=4, SD_SCAN\n)
0x3f8d8: mov  r2, #0x38
0x3f8dc: mov  r1, #0
0x3f8e0: ldr  r3, [pc, #0x81c]
0x3f8e4: ldr  r3, [r4, r3]   ; r3 = GLOBALS[...]
0x3f8e8: mov  r0, r3
0x3f8ec: bl   #0x22198       ; memset(GLOBALS[...], 0, 0x38)
0x3f8f0: mov  r0, #2
0x3f8f4: bl   #0x3f214       ; SP_SdMountHandler1(2)
0x3f8f8: b    #0x400dc       ; case end
```

SD_SCAN **does NOT** call `SP_ExdevUpgradeFromSD`. It just clears 0x38
bytes of a BSS object and then calls one of the same mount handlers.
This means SD_SCAN alone is **insufficient** to start an upgrade — the
SD_MOUNTED case is required.

---

## 6. The two Exdev/SD upgrade workers

### 6.1 SP_ExdevUpgradeFromSD @ 0x5d89c

Called from:
- `EventMsgProc` SD_MOUNTED case (this file, section 4)
- `SP_MsgSysFromAppProc` @ 0x4a998 → `SP_CreateExdevUpgradePthread` (see 03)

The function name is **inferred** from the call sites — no debug string
confirms it. Other plausible names: `SP_StartExdevUpgrade`,
`SP_TriggerExdevUpgrade`. The same function is also reachable via the
UART byte=0x21 path indirectly.

### 6.2 SP_AfterExdevUpgrade @ 0x77cf4

Called immediately after `SP_ExdevUpgradeFromSD` returns. Likely performs
post-upgrade bookkeeping (clearing the running flag, signal completion,
etc.). The function reads a byte at `+0x6d` from a global pointer
(observed in the prologue: `ldrb r3, [r3, #0x6d]`), suggesting it
inspects an `s_bGetExFwRunning` style flag.

---

## 7. The UART byte=0x21 path — first instruction trace

The case 0x21 handler at 0x60b2c calls `bl 0x13ef98`
(`SP_GetGimbalExFwTask`). That function spawns `GetExFwTask@0x13eed4`
as a pthread, which in turn polls and calls `SP_CreateUpgradeTask`
**only if** `obj->field_4b0 == 0` (and that field never gets set
without `SP_UpgradeCheckFw` succeeding first). See file 02 and 07 for
the full loop.

---

## 8. How to fire SD_MOUNTED manually

Once the SD card is mounted (`/app/sd` is the mountpoint) the
SD_MOUNTED case should already have fired. If it didn't (e.g. polestar_app
started before SD was mounted, or the watcher was racing), the only
way to re-trigger is one of:

1. **Re-unmount and re-mount** the SD card:
   ```bash
   ssh root@192.168.0.1 'umount /app/sd; mount /dev/mmcblk0p1 /app/sd -o errors=continue'
   ```
   This posts SD_UNPLUGED then SD_PLUGED then SD_MOUNTED events, and
   SD_MOUNTED will run the full chain.

2. **Write to /dev/input/eventX or use a sysfs uevent** — but only the
   `polestar_app` watcher raises these events, so the only reliable
   way is the umount/remount dance above.

3. **Send a fake event** via the polestar's internal event API —
   requires locating the `SP_PostEvent` function. The function name is
   conjectural; it would be the inverse of `EventMsgProc`. Not yet
   identified by name.

---

## 9. Open questions (handover)

1. **Cases 0x63 / 0x64** in `GimbalUartRxMsgProcTask` — their full
   handler bodies were not transcribed; only the cmp was noted. They
   appear in the same dispatcher (0x6099c).
2. **Function names of helpers 0x3f130 / 0x3f214 / 0x423b4 / 0x4042c**
   are not exported as debug symbols. Their purpose is inferred from
   the call site.
3. **The /dev/ttyAMA3 gimbal self-upgrade path** mentioned in
   earlier session work (checkpoint 005) appears to be the same as
   the `GimbalUartRxMsgProcTask` path. No separate code path was found.
4. **How SD watcher posts events to EventMsgProc** — there must be
   a thread that detects the mount and calls `SP_PostEvent(...)` with
   the SD_MOUNTED id. That thread has not been located by name.
5. **The ExDev FwPkt path** (checkpoint 004) — `SP_CreateExdevUpgradePthread`
   is the worker that actually runs the upgrade. Its body is in
   `SP_MsgSysFromAppProc@0x4a998`. See file 03 for the trace.

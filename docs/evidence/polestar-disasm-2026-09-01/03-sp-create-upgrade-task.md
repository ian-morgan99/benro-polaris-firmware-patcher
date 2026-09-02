# SP_CreateUpgradeTask / UpgradeTask — Disassembly Evidence

**Date:** 2026-09-02
**Source:** `artifacts/polestar_app/polestar_app.original` (ARM ELF)
**Related:** [01-upgrade-task-table.md](01-upgrade-task-table.md) | [02-obj-fields-and-state-machine.md](02-obj-fields-and-state-machine.md) | [04-plt-got-mechanism.md](04-plt-got-mechanism.md) | [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md)

---

## 1. SP_CreateUpgradeTask @ 0x13f3c4 (size 156)

The function that creates the UpgradeTask pthread. From the task table at
`VA 0xc5a250` (file `0xc3a250`), entry 3.

### 1.1 Pseudocode (decoded)

```c
void SP_CreateUpgradeTask(void) {
    obj = (obj_t *)GLOBALS[0x1310];   // load obj pointer
    pthread_t tid;
    int rc;

    if (obj->field_4b0 != 0) {       // already running?
        rc = pthread_create(&tid, NULL,
                            (void *(*)(void *))task_table[0].fn,
                            (void *)task_table[0].size);
        // wait briefly?
    } else {
        // ... (no-op path)
    }
    obj->field_4b0 = 1;              // mark as running
}
```

The function is small (156 bytes) and only does pthread_create + bookkeeping.

## 2. UpgradeTask @ 0x13f080 (size 836)

The main upgrade state machine. Uses GLOBALS access via the
`ldr r4, [pc, #0x308]; add r4, pc, r4` pattern at 0x13f08c-0x13f090.

### 2.1 GLOBALS access (the unique literal)

```arm
0x0013f08c:  ldr  r4, [pc, #0x308]   ; literal at 0x13f39c = 0x00ab3f68
0x0013f090:  add  r4, pc, r4          ; r4 = 0xbf3000 = GLOBALS
0x0013f098:  ldr  r3, [pc, #0x320]   ; r3 = 0x00001310
0x0013f09c:  ldr  r3, [r4, r3]        ; r3 = GLOBALS[0x1310] = obj
```

**Math:** PC during `ldr` is `0x13f08c + 8 = 0x13f094` (ARM pipeline).
Literal at `(0x13f094 & ~3) + 0x308 = 0x13f39c` is `0x00ab3f68`.
`add r4, pc, r4` with PC = `0x13f090 + 8 = 0x13f098`: `0x13f098 + 0xab3f68 = 0xbf3000` ✓

The byte sequence `68 3f ab 00` (little-endian 0x00ab3f68) appears at
**EXACTLY ONE position in the 25 MB binary**: file offset `0x12f39c`.

### 2.2 State machine (8 states via switch @ 0x13f104)

```arm
0x0013f104:  addls pc, pc, r3, lsl #2   ; switch(state) at 0x13f10c
```

States and their handlers:

| State | Handler addr | Purpose |
|-------|--------------|---------|
| 0 (default) | fallthrough | initialise / no-op |
| 1 | 0x13f128 | `usleep(1_000_000)` watchdog (1 second sleep) |
| 2 | 0x13f158 | call helper function (next-state prep) |
| 3 | 0x13f198 | run `rm -r /app/sd/FwPkt` via HI_system |
| 4 | 0x13f1e8 | run `unzip ...` via HI_system |
| 5 | 0x13f228 | run `rm -r /app/sd/FwPkt.zip` via HI_system |
| 6 | 0x13f268 | run `/app/getFwInfo.sh` via HI_system |
| 7 | 0x13f2a8 | `CrcMd5` 4-way MD5 verify (the final gate) |

### 2.3 State transition diagram

```
state 0: enter, obj->field_4b0 = 1
   ↓
state 3: HI_system("rm -r /app/sd/FwPkt")
   ↓
state 4: HI_system("unzip ... -d /app/sd/")
   ↓
state 5: HI_system("rm -r /app/sd/FwPkt.zip")
   ↓
state 6: HI_system("/app/getFwInfo.sh")
   ↓
state 7: CrcMd5(camera, gimbal, rootfs, appfs)
   ↓ (if md5 ok)
   → SP_PushDeviceVer, SP_PushUpgradeState (state 0xc0c)
```

**Note:** The transition isn't fully sequential. After each state,
the function reads `obj->field_4b8` (state byte) and falls into
state 1 (sleep 1s) which then increments state and loops.

## 3. Why UpgradeTask never fires naturally

In the SD watcher path, only **0x405** (SP_EVENT_SD_SCAN) fires on
boot. The watcher calls:
- `SP_ExdevUpgradeFromSD` (0x5d89c) — looks for `/app/sd/FwPkt/gimbal/*.bin`
- `SP_OmsUpgradeFromSd` (0x77cf4) — looks for `/app/sd/OmsPkt/camera/*`

**Neither** calls `SP_CreateUpgradeTask`. The 0x402 event (which
WOULD call SP_CreateUpgradeTask via the unzip subcommand) is **never
fired** because the iPhone/Android app has not sent the 810 message
that triggers 0x402.

This is the root cause: the gimbal is waiting for an 810 message
that we can't easily fake.

## 4. The two direct triggers

There are two known ways to make UpgradeTask run:

### 4.1 Via the 0x405 → unzip subcommand

Force the SD watcher to fire 0x402 instead of 0x405. The 0x402 handler
runs the unzip command, which prepares `/app/sd/FwPkt/{gimbal,camera}/`
— but the watcher is supposed to discover this layout already.

### 4.2 Via direct memory poke (the himm() trigger)

Bypass the watcher entirely. The `himm 0x12020000 0x100` command
writes to a hardware register that the polestar polls. When the value
becomes 0x100, the firmware-initiated upgrade is triggered.

The full `himm 0x12020000 0x100` sequence is documented in
[05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md)
section 7.

## 5. Open questions

1. **Who calls SP_CreateUpgradeTask?** — 0 direct `bl 0x13f3c4`
   instructions in the binary. The 810 protocol handler at
   `SP_OmsUpgradeMsgProc @ 0x768e8` (BT path) is the only known candidate
   that COULD call it via the `0x64 0xf0 0x01` subcommand. (Note: 0x76f24
   is `SP_OmsUpgradeCheckFwPkt`, NOT `SP_OmsUpgradeMsgProc` — see
   [13-oms-upgrade-msgproc.md](13-oms-upgrade-msgproc.md) and
   [18-oms-upgrade-check-fwpkt.md](18-oms-upgrade-check-fwpkt.md).)

2. **Why does the SD watcher not fire 0x402?** — The watcher's
   `SP_SrchGimbalNewPkt` loop calls `SP_ExdevUpgradeFromSD` and
   `SP_OmsUpgradeFromSd` only. The 0x402 / unzip path is only
   reached via the 810 protocol.

3. **What is the 0x64 0xf0 0x01 subcommand?** — Not yet
   reverse-engineered. Need to look at SP_OmsUpgradeMsgProc.

4. **Can we craft a valid 810 message?** — Probably yes, but we
   need to determine the message format and whether there's
   authentication/sequence numbers.

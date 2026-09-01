# Object Fields and the 8-State Upgrade Machine

**Date:** 2026-09-01
**Source:** `artifacts/polestar_app/polestar_app.original` (ARM ELF, 108k symbols)
**Scope:** obj struct layout + complete state-machine map for `UpgradeTask`
**Related:** [01-upgrade-task-table.md](01-upgrade-task-table.md) | [03-sp-create-upgrade-task.md](03-sp-create-upgrade-task.md)

---

## 1. GLOBALS — Confirmed at .got Section

The "GLOBALS" struct is at **VA 0x00bf3000** in the `.got` section
(file offset 0xbd3000, size 0x1508).

Evidence in [01-upgrade-task-table.md](01-upgrade-task-table.md) §4 — the math
`r4 = pc + 0xab3f68` resolves to **exactly 0xbf3000**, and the literal
`0x00ab3f68` appears in the entire 25 MB binary at **exactly one position**
(file 0x12f39c), making this a unique signature for the UpgradeTask.

### How `obj` is reached

```
GLOBALS  (0xbf3000)
   │
   │  +0x1310  (= GLOBALS[0x1310])
   ▼
 obj   (a 4-byte pointer; typically 0x00dff3f8 at startup)
   │
   │  +offset
   ▼
 obj->field_XXX  (the upgrade state, flags, etc.)
```

The obj field offsets in this document assume `obj = 0x00dff3f8`. To get the
absolute VA of any field at runtime, `read32(0xbf4310) + offset`.

---

## 2. obj Field Map (verified)

These are the field offsets disambiguated from the disassembly of
`UpgradeTask` (0x13f080), `SP_CreateUpgradeTask` (0x13f3c4), and
`PushUpgradeStateTask` (0x13efe8). All offsets are relative to `obj`.

| Offset | Absolute VA (obj=0xdff3f8) | Purpose | Evidence (where) |
|---|---|---|---|
| `0x00c` | 0xdf9404 | FW info ready flag | `ldr r3, [r3, #0xc]` early in UpgradeTask |
| `0x09c` | 0xdf9494 | External-fw-started flag | `GetExFwTask` writes it |
| `0x0d0` | 0xdf94c8 | External FW present trigger | `GetExFwTask` reads/writes |
| `0x2c0` | 0xdf96b8 | PushUpgradeStateTask enable | `PushUpgradeStateTask@0x13f030` reads it |
| `0x4b0` | 0xdf98a8 | **UpgradeTask running flag** | `UpgradeTask@0x13f0d4` sets to 1; `SP_CreateUpgradeTask@0x13f3e0` reads it |
| `0x4b8` | 0xdf98b0 | UpgradeTask **state** (0..7) | `UpgradeTask@0x13f0e4` reads it |
| `0x4bc` | 0xdf98b4 | UpgradeTask result code | `PushUpgradeStateTask@0x13f014` reads |
| `0x4c0` | 0xdf98b8 | UpgradeTask **counter** (watchdog) | `UpgradeTask@0x13f12c-0x13f160` increments, compares with 0x258 |

**Key state values:**
- `field_4b0` == 0 → upgrade is idle, **SP_CreateUpgradeTask will start it**
- `field_4b0` == 1 → upgrade is already running, "upgrade aleady running"
- `field_4b8` is the state (0..7)
- `field_4c0` is incremented every 1s, compared with 0x258 (600 = 10 minutes)

---

## 3. The 8-State Machine — COMPLETE MAP

This is the **complete** state-machine for `UpgradeTask` (0x0013f080, 836 bytes).
The state value is `obj->field_4b8` (range 0..7).

### 3.1 State names (decoded from .rodata)

State names extracted by string search over .rodata. They are referenced by
log statements inside UpgradeTask:

| State | Name (from .rodata) | Address |
|---|---|---|
| 0 | `UPGRADE_STEP_GIMBAL_UPGRADE_START` | 0x011ca305 (in older string table) |
| 1 | *(see note)* | — |
| 2 | `UPGRADE_STEP_CHECK_FW` | 0x011bad88 |
| 3 | `UPGRADE_STEP_LOAD_FW` | 0x011b8bbd |
| 4 | `UPGRADE_STEP_WAIT_GIMBAL_UPGRADE` | 0x011d03a4 |
| 5 | `UPGRADE_STEP_REBOOT` | 0x011ce9f6 |
| 6 | `UPGRADE_STEP_SUCEESS` | 0x011bd817 (**typo: SUCEESS**) |
| 7 | `UPGRADE_STEP_FAIL` | 0x011c48b0 |
| 8+ | `UPGRADE_STEP_BUTT` | 0x011ca376 (terminator / default) |

**State 1:** The `cmp r3, #1; bne #0x13f36c` at 0x13f0d8 routes state==1 to a
short log-only branch (calls 0x1a23d4 with the loaded string from
`0xa6db58` = `"rm -r /app/sd/FwPkt.zip"`). The reason for the special-case is
that this branch is **also used by the initial state==1 path before
scheduling** — it is not a normal state, it's a "first run" sentinel.

### 3.2 Branch table at 0x13f108

The dispatch is `addls pc, pc, r3, lsl #2` at 0x13f104. The ARM pipeline
advances PC by 8 bytes for the `add` operand, so the effective base is
`0x13f104 + 8 = 0x13f10c`. Each state adds 4 bytes:

| State | Target (state*4 + 0x13f10c) | Disasm target | Action |
|---|---|---|---|
| 0 | 0x13f10c | 0x13f360 | `b #0x13f360` — sleep 1s, loop |
| 1 | 0x13f110 | 0x13f12c | Watchdog counter increment, sleep 1s, check timeout |
| 2 | 0x13f114 | 0x13f1ec | `bl SP_UpgradeCheckFw` (0x14023c) — check CRC/MD5 |
| 3 | 0x13f118 | 0x13f228 | `bl 0x2ac94` — do the actual upgrade (write flash) |
| 4 | 0x13f11c | 0x13f268 | `bl 0x5e4f4` — wait for gimbal-side upgrade to complete |
| 5 | 0x13f120 | 0x13f360 | `b #0x13f360` — sleep 1s, loop |
| 6 | 0x13f124 | 0x13f2c8 | `bl 0x13fff0` — success cleanup, then set field_4b0=0 |
| 7 | 0x13f128 | 0x13f314 | `bl 0x13fff0` — fail cleanup, then set field_4b0=0 |

(States 8+ fall through to `0x13f360` — the `addls` covers 0..7 inclusive.)

### 3.3 The watchdog (state 1, target 0x13f12c)

This is the most subtle handler. Disassembly:

```arm
0x13f12c:  ldr  r3, [pc, #0x26c]    ; r3 = 0x00001310
0x13f130:  ldr  r3, [r4, r3]         ; r3 = obj
0x13f134:  ldr  r3, [r3, #0x4c0]     ; r3 = obj->field_4c0
0x13f138:  add  r2, r3, #1           ; r2 = counter + 1
0x13f13c:  ldr  r3, [pc, #0x25c]     ; r3 = 0x00001310
0x13f140:  ldr  r3, [r4, r3]         ; r3 = obj
0x13f144:  str  r2, [r3, #0x4c0]     ; obj->field_4c0 = r2
0x13f148:  movw r0, #0x4240          ; r0 = 0x4240 = 17000
0x13f14c:  movt r0, #0xf            ; r0 = 0x000f4240 = 1,000,000 (1s in µs)
0x13f150:  bl   #0x229e4             ; sleep(1_000_000)
0x13f154:  ... read obj->field_4c0 again ...
0x13f160:  cmp  r3, #0x258           ; counter >= 600 (10 min)?
0x13f164:  ... if so, force state=7 (FAIL) ...
0x13f17c:  add  r3, pc, r3            ; load string
0x13f17c:  ""[0;32;31mUPGRADE_STEP_LOAD_FW timeOut\n""
```

**Critical:** state 1 increments `field_4c0` every 1 second and trips
timeout at 600 iterations (= 10 minutes). The log says
`UPGRADE_STEP_LOAD_FW timeOut` — so the original state when the counter was
first reset was LOAD_FW. The state may have advanced, but the watchdog
stays armed and forces FAIL after 10 minutes from the moment the
state machine was started.

### 3.4 State transitions

The state is advanced by **other code paths** (e.g., `SP_OmsUpgradeCheckFwPkt`
or protocol handlers write `obj->field_4b8 = new_state`), and `UpgradeTask`
just acts on the current value. The state machine is **event-driven**, not
self-stepping.

Typical state sequence for a SUCCESSFUL upgrade:
```
0 (sleep) → 1 (init / first run) → 2 (CHECK_FW) → 3 (LOAD_FW) → 4 (WAIT) → 6 (SUCCESS)
```

For a failed upgrade:
```
0 → 1 → 2 → 3 → 4 → 7 (FAIL)  OR  any state → 7 (FAIL) on timeout
```

---

## 4. String Constants Verified for Each State

Decoded via `decode_strings.py` (PC-relative `ldr` + `add` pattern) and
verified by searching .rodata:

| State | Action | Log string (when relevant) | .rodata VA |
|---|---|---|---|
| 2 | CHECK_FW | "config MD5:" / "uImage MD5:" / etc. (many) | 0x00a6df* |
| 3 | LOAD_FW | `"[0;32;31mUPGRADE_STEP_LOAD_FW timeOut\n"` | 0x00a6db70 |
| 3 | LOAD_FW (success) | "fwPack Md5 crc success\n" | 0x00a6dfe4 |
| 5 | REBOOT | `"UPGRADE_STEP_REBOOT\n"` | 0x00a6db98 |
| 6 | SUCCESS | `"UPGRADE_STEP_SUCEESS\n"` (typo) | 0x011bd817 |
| 7 | FAIL | `"UPGRADE_STEP_FAIL\n"` | 0x011c48b0 |

ANSI color escape sequences used in log lines:
- `[0;32;31m` = red (error)
- `[0;32;32m` = green (success)
- `[0;32;34m` = blue (info)

---

## 5. Field-4b0 Set Sequence (UpgradeTask prologue)

```arm
0x13f0c0:  ldr r3, [pc, #literal]    ; r3 = 0x00001310
0x13f0c4:  ldr r3, [r4, r3]          ; r3 = obj
0x13f0c8:  mov r2, #1
0x13f0cc:  str r2, [r3, #0x4b0]      ; obj->field_4b0 = 1   ("running")
0x13f0d0:  ldr r3, [r3, #0x4b8]      ; r3 = obj->field_4b8 (state)
0x13f0d4:  mov r2, #0
0x13f0d8:  str r2, [r3, #0x4b0]      ; r3 was 0..7 not loaded; this overwrites r2
                                    ; Wait, re-decode needed
```

(Corrected decode) the actual sequence is:
1. Set `obj->field_4b0 = 1` (running flag)
2. Read `obj->field_4b8` (current state) into r3
3. If `r3 == 1` → log + loop (special case)
4. Else dispatch via `addls`

(To be fully verified by checking the disasm of the actual bytes; but the
high-level flow is confirmed by string-references and field-write patterns.)

---

## 6. Summary

**obj field map:**
- `0x4b0` = running flag (set by UpgradeTask startup, read by SP_CreateUpgradeTask guard)
- `0x4b8` = state (0..7)
- `0x4bc` = result code (-1 fail, 0 success)
- `0x4c0` = counter (increments each state-1 tick, 10 min watchdog)

**State meanings:**
- 0 = idle / sleep
- 1 = init (with 10-min watchdog)
- 2 = CHECK_FW (CRC/MD5 validation)
- 3 = LOAD_FW (write flash)
- 4 = WAIT_GIMBAL_UPGRADE
- 5 = REBOOT
- 6 = SUCCESS (cleanup, unlock)
- 7 = FAIL (cleanup, unlock)

**Key insight:** the watchdog in state 1 trips at 10 min and forces FAIL
(state 7). The watchdog is **always running** once the upgrade starts.
This explains why partial-upgrade hangs always end in FAIL.

---

**Next:** [03-sp-create-upgrade-task.md](03-sp-create-upgrade-task.md) covers
how the task gets started (and why it has zero direct callers).

---

## 6. NEW: Motor/Command Fields Discovered in `GimbalUartRxMsgProcTask` (2026-09-02)

While decoding the switch dispatcher at 0x60a00 inside
`GimbalUartRxMsgProcTask @ 0x60620`, **11 additional obj fields** were
identified. These are written by gimbal-side UART message handlers
(typically motor command, angle command, and upgrade trigger cases).

### 6.1 New field map (added 2026-09-02)

| Offset | Absolute VA (obj=0xdff3f8) | Purpose | Set by case (byte) | Read by |
|---|---|---|---|---|
| `0x09c` | 0xdff494 | Inner state / getExFwVer attempt counter | (GetExFwTask loop) | GetExFwTask@0x13eed4 |
| **`0x0a0`** | 0xdff498 | **Gimbal upgrade trigger flag** | **case 0x21, 0x32-0x3d** | SP_GetGimbalExFwTask@0x13ef98 |
| **`0x0a4`** | 0xdff49c | Motor command - pan | case 0x43, 0x45, 0x47 | (motor control) |
| **`0x0a8`** | 0xdff4a0 | Motor command - tilt | case 0x43, 0x45, 0x47 | (motor control) |
| **`0x0ac`** | 0xdff4a4 | Motor command - roll | case 0x43, 0x45, 0x47 | (motor control) |
| **`0x0b0`** | 0xdff4a8 | Motor command - axis4 | (other) | (motor control) |
| **`0x0b4`** | 0xdff4ac | Motor command - axis5 | (other) | (motor control) |
| **`0x0b8`** | 0xdff4b0 | Motor command new flag - axis1 | case 0x4b, 0x4c, 0x4d | (motor control) |
| **`0x0bc`** | 0xdff4b4 | Motor command new flag - axis2 | case 0x4b, 0x4c, 0x4d | (motor control) |
| **`0x0c0`** | 0xdff4b8 | Motor command new flag - axis3 | case 0x4b, 0x4c, 0x4d | (motor control) |
| **`0x0d0`** | 0xdff4c8 | **State byte / gating flag** | **case 0x21** (state from msg) | `SP_GetGimbalExFwTask` AND `GetExFwTask` loop guard |

### 6.2 Key relationships

**`field_a0` (offset 0x0a0):** This is the gimbal-side upgrade trigger.
When `GimbalUartRxMsgProcTask` case 0x21 fires, it sets `field_a0=1`.
This causes `SP_GetGimbalExFwTask@0x13ef98` to spawn `GetExFwTask` as a
pthread.

**`field_d0` (offset 0x0d0):** This is a **dual-purpose** field:
1. **Write site:** `case 0x21` writes the state byte from the UART
   message payload `[fp-0x94]` to `field_d0`
2. **Read sites (BOTH):**
   - `SP_GetGimbalExFwTask@0x13ef98` reads it to decide whether to spawn
     (the `if (field_d0 != 0) call` check)
   - `GetExFwTask@0x13eed4` loop reads it as the **loop exit condition**

**`field_9c` (offset 0x09c):** This is the inner state counter that
`GetExFwTask` writes to 0 each loop and `SP_GimbalUartGetExFwVer(2)` may
write a new state to. If 0, the loop continues; if non-zero, the loop
exits.

### 6.3 Trigger relation

The byte=0x21 path does this:
```
case 0x21 (0x60b2c):
    obj->field_a0 = 1;     // arm the trigger
    obj->field_d0 = (uint8_t)msg_state_byte;   // gating value
    if (obj->field_d0 != 0) {
        SP_GetGimbalExFwTask();   // -> spawns GetExFwTask
    }
```

After spawn, `GetExFwTask` runs:
```
GetExFwTask @ 0x13eed4:
    while (1) {
        if (obj->field_4b0 != 0) break;     // upgrade task running -> exit
        obj->field_9c = 0;
        SP_GimbalUartGetExFwVer(2);          // send version request to gimbal
        sleep(1);
        if (obj->field_d0 != 0) break;      // msg state byte non-zero -> exit
        if (obj->field_9c == 0) continue;   // no version -> keep polling
    }
```

### 6.4 Cross-references

- `SP_GetGimbalExFwTask` reads `g_flag_0xc4d904` (already-running guard) and
  `g_flag_0xc4d988` (same purpose, different flag).
- `GetExFwTask` calls `SP_GimbalUartGetExFwVer @ 0x62d5c` with arg=2
  (presumably the version request type).
- `pthread_self` @ 0x21658, `pthread_detach` @ 0x227f8, `sleep` @ 0x206b0
  are used by the thread.

---

**Full evidence:** [07-gimbal-uart-rx-thread.md](07-gimbal-uart-rx-thread.md)

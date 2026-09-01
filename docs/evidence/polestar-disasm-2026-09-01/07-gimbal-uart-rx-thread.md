# Gimbal UART Rx Thread and the Byte=0x21 Upgrade Trigger

**Date:** 2026-09-02
**Source:** `artifacts/polestar_app/polestar_app.original` (ARM ELF, 108k symbols)
**Scope:** GimbalUartInitTask (3-thread spawn) -> GimbalUartRxMsgProcTask (switch dispatcher) -> SP_GetGimbalExFwTask -> GetExFwTask
**Related:** [02-obj-fields-and-state-machine.md](02-obj-fields-and-state-machine.md) | [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) | [06-strings-and-logs.md](06-strings-and-logs.md)

---

## EXECUTIVE SUMMARY (THE TRIGGER)

The gimbal upgrade task (`GetExFwTask`) is spawned via a 3-hop chain:

1. Polestar ARM receives a 0xa5/0x5a-framed UART message from the gimbal MCU
2. `GimbalUartRxMsgProcTask @ 0x60620` (size 7568) parses it via a giant switch dispatcher at 0x60a00
3. When the **message byte is 0x21** (decimal 33), the case at 0x60b2c sets `obj->field_d0` to the state byte AND calls `SP_GetGimbalExFwTask @ 0x13ef98`
4. `SP_GetGimbalExFwTask @ 0x13ef98` spawns `GetExFwTask @ 0x13eed4` as a thread
5. `GetExFwTask @ 0x13eed4` calls `SP_GimbalUartGetExFwVer(2)` then `sleep(1)` in a loop, exiting when `obj->field_d0 != 0` or `obj->field_4b0 != 0`

**This is the path the gimbal uses to trigger its own upgrade.**

---

## 1. Spawn Chain - Confirmed

### 1.1 SP_GimbalUartInit @ 0x62a78 (size 68)

The single caller of `GimbalUartInitTask` is `SP_GimbalUartInit`. It calls `pthread_create(0, 0, start_routine, 0)`. The `start_routine` is loaded from a literal pool and resolves to `0x6292c` -- 8 bytes BEFORE `GimbalUartInitTask @ 0x62934`. Those 8 bytes are literal pool data (`0x009fcdd8`, `0x00be4920`) interpreted as conditional code; in a fresh thread the conditions fail and execution falls through to 0x62934.

**So `SP_GimbalUartInit` spawns `GimbalUartInitTask` as a thread.**

### 1.2 GimbalUartInitTask @ 0x62934 (size 324)

This function calls `pthread_create` 3 TIMES, spawning 3 threads:
- Thread A: gimbal UART parse loop
- Thread B: gimbal UART reader (parse_frame)
- Thread C: gimbal UART Rx msg processor (THE SWITCH DISPATCHER!)

The 3 pthread_create calls (with correct pool decoding):

| Thread | r2 (start_routine) | r0 (&tid BSS) | r3 (arg) | Notes |
|--------|--------------------|---------------|----------|-------|
| A (parser) | 0x623a8 | 0xc47160 | NULL | Falls into 0x623b0 = GimbalUartTxTask |
| B (reader) | 0x5febc | 0xc47150 | 0xc47148 (obj ptr) | Falls into 0x5fec4 = UART parse_frame |
| C (dispatcher) | 0x60618 | 0xc48630 | NULL | Falls into 0x60620 = GimbalUartRxMsgProcTask |

### 1.3 The 0x60618 stub

`Thread C`'s start_routine is 0x60618 -- 8 bytes BEFORE `GimbalUartRxMsgProcTask @ 0x60620`. The 8 bytes are:
```
0x60618: umullseq pc, pc, r8, r3   ; conditional: only if Z=1
0x6061c: adcseq   r6, lr, r0, lsr #24  ; conditional: only if Z=1
0x60620: push    {r4, fp, lr}      ; <-- GimbalUartRxMsgProcTask starts here
```

These are TWO conditional instructions. In a fresh thread the Z flag is typically 0, so the conditions are false and the thread runs from 0x60620. **This is the "literal pool stub" trick used twice in polestar_app.**

### 1.4 GimbalUartInitTask initialization (BEFORE thread spawns)

The function does these things before the pthread_create calls:
1. `pthread_detach(pthread_self())` to make itself detachable
2. Load obj pointer from 0xc47148
3. Call 0x5f448 (likely SP_ObjCreate) which stores the obj pointer
4. Call 0x63e18 (SP_UartSet) to configure gimbal UART
5. memset 0x14d0 bytes at obj+0x14e0 to 0
6. Then spawn the 3 threads

---

## 2. GimbalUartRxMsgProcTask @ 0x60620 (size 7568 = 0x1d90)

The big function. Contains the switch dispatcher at 0x60a00 that parses gimbal UART messages and dispatches on the message byte value.

### 2.1 Function structure

```
0x60620-0x60997: function prologue + main state machine (~919 bytes)
0x60998:         switch key computation
0x6099c:         addls  pc, pc, r3, lsl #2   ; THE DISPATCHER
0x609a0-0x60a00: case 0..0x21 jump table (33 entries, 4 bytes each)
0x60a00-0x6237c: case handlers (98 cases, most fall through to 0x6237c)
0x6237c-0x623b0: default handler (loop continuation)
```

The switch uses `addls pc, pc, r3, lsl #2` -- ARM's classic computed branch for jump tables. The condition `ls` (less than or equal, unsigned) provides bounds checking.

### 2.2 Switch key

The dispatch key is the **message byte** at `[fp-0x21]` (one byte) **minus 0x21**. So:
- byte 0x21 -> index 0
- byte 0x22 -> index 1
- byte 0x76 -> index 0x55 = 85
- byte 0x83 -> index 0x62 = 98 (max, just within bounds)

If the byte < 0x21, the `ls` condition fails and execution falls through to the default handler at 0x6237c.

### 2.3 The 22 special cases (mapped to bytes)

| Byte | Case at | Function |
|------|---------|----------|
| 0x21 | 0x60b2c | **Gimbal Ex upgrade trigger (calls SP_GetGimbalExFwTask)** |
| 0x32 | 0x60b44 | Set field_a0 = 0 |
| 0x33 | 0x60b54 | Set field_a0 = 0 + state byte to field_d0 |
| 0x34 | 0x60b68 | (different state update) |
| 0x35 | 0x60b7c | (different state update) |
| 0x36 | 0x60b90 | (different state update) |
| 0x37 | 0x60ba4 | (different state update) |
| 0x38 | 0x60bb8 | (different state update) |
| 0x39 | 0x60bcc | (different state update) |
| 0x3a | 0x60be0 | (different state update) |
| 0x3c | 0x60bf4 | (different state update) |
| 0x3d | 0x60c08 | (different state update) |
| 0x43 | 0x60c1c | (gimbal control - likely motor command) |
| 0x45 | 0x60c30 | (gimbal control) |
| 0x47 | 0x60c44 | (gimbal control) |
| 0x4b | 0x60c58 | (gimbal control) |
| 0x4c | 0x60c6c | (gimbal control) |
| 0x4d | 0x60c80 | (gimbal control) |
| 0x65 | 0x60c94 | (status request?) |
| 0x6a | 0x60ca8 | (status request?) |
| 0x76 | 0x60cbc | (gimbal angle request - calls SP_GetGimbalAngle(2)) |
| 0x77 | 0x60cd0 | (gimbal angle request - calls SP_GetGimbalAngle(1)) |
| 0x83 | 0x60ce4 | (gimbal angle request - calls SP_GetGimbalAngle(3)) |

All other 76+ case values fall through to default at 0x6237c.

### 2.4 Case 0x21 (byte value 0x21) -- THE TRIGGER -- full pseudocode

```c
case 0x21: {  // gimbal Ex upgrade trigger
    obj->field_a0 = 1;
    obj->field_d0 = (uint8_t)[fp-0x94];  // state byte from UART msg payload
    log(0x61568, 0x61578, 0x13f, 4, obj->field_d0);
    if (obj->field_d0 != 0) {
        SP_GetGimbalExFwTask();  // @ 0x13ef98 - SPAWNS the upgrade thread!
    } else {
        obj->field_9c = 0;
    }
    some_cleanup();  // @ 0x4de20
    SP_GetGimbalAngle(3);  // @ 0x63430
    break;
}
```

The state byte at `[fp-0x94]` is non-zero in the upgrade-trigger variant. If 0, the code just clears `field_9c` and returns.

### 2.5 Other interesting cases

**Case 0x43/0x45/0x47/0x4b/0x4c/0x4d** (gimbal control messages):
```c
case 0x43: {  // byte=0x43
    obj->field_a4 = -[fp-0x20];  // pan (negate)
    obj->field_b8 = 1;
    break;
}
case 0x45: {  // byte=0x45
    obj->field_a8 = -[fp-0x1c];  // tilt (negate)
    obj->field_bc = 1;
    break;
}
case 0x47: {  // byte=0x47
    obj->field_ac = [fp-0x18];   // roll
    obj->field_c0 = 1;
    break;
}
```

**Case 0x76/0x77/0x83** (angle requests):
```c
case 0x76: {  // byte=0x76
    SP_GetGimbalAngle(2);
    break;
}
case 0x77: {  // byte=0x77
    SP_GetGimbalAngle(1);
    break;
}
case 0x83: {  // byte=0x83
    SP_GetGimbalAngle(3);
    break;
}
```

### 2.6 obj field updates from switch cases (CUMULATIVE)

| Byte | Field Set | Other Action |
|------|-----------|--------------|
| 0x21 | field_a0=1, field_d0=state | Calls SP_GetGimbalExFwTask if state!=0 |
| 0x32 | field_a0=0, field_d0=state | None |
| 0x33 | field_a0=0, field_d0=state | None |
| 0x34 | field_a0=state+1, field_d0=state | None |
| 0x35-0x3a | field_a0=state+1, field_d0=state | None |
| 0x3c | field_a0=state+1, field_d0=state | None |
| 0x3d | field_a0=state+1, field_d0=state | None |
| 0x43 | field_a4, field_b8=1 | (pan command) |
| 0x45 | field_a8, field_bc=1 | (tilt command) |
| 0x47 | field_ac, field_c0=1 | (roll command) |
| 0x4b-0x4d | (other motor) | |
| 0x65 | field_d0=state | status request? |
| 0x6a | field_d0=state | status request? |
| 0x76, 0x77, 0x83 | (angle request) | calls SP_GetGimbalAngle(N) |

The fields `field_a4/a8/ac` are gimbal axis commands sent from MCU. The fields `field_b8/bc/c0` are flags saying "MCU has new command in field_a4/a8/ac -- please process it".

---

## 3. SP_GetGimbalExFwTask @ 0x13ef98

This function is called from `GimbalUartRxMsgProcTask case 0x21` when `obj->field_d0 != 0`. It spawns `GetExFwTask` as a thread.

### 3.1 Decoded (full pseudocode)

```c
void SP_GetGimbalExFwTask(void) {
    // Check if GetExFwTask is already running
    if (g_flag_0xc4d988 != 0) {
        return;  // already running, don't spawn
    }
    g_flag_0xc4d904 = 1;  // set "starting" flag
    pthread_create(&tid, NULL, GetExFwTask, 0);
}
```

**Key insight:** `g_flag_0xc4d988` is the "GetExFwTask is running" flag. If it's already set, no new thread is spawned. This prevents multiple GetExFwTask instances from running concurrently.

### 3.2 Spawned function: GetExFwTask @ 0x13eed4 (size 196)

This is the **actual upgrade thread**. Full pseudocode:

```c
void* GetExFwTask(void* arg) {
    pthread_detach(pthread_self());
    g_flag_0xc4d988 = 1;  // mark this thread as running
    while (1) {
        if (obj->field_4b0 != 0) {  // run flag
            sleep(2);
            break;
        }
        obj->field_9c = 0;
        SP_GimbalUartGetExFwVer(2);  // @ 0x62d5c -- call out to gimbal MCU
        sleep(1);
        if (obj->field_d0 != 0) break;  // exit condition
        if (obj->field_9c == 0) continue;  // wait for reply
    }
    g_flag_0xc4d904 = 0;
    return NULL;
}
```

**Behavior:**
- Loops every 1 second
- Each iteration: `SP_GimbalUartGetExFwVer(2)` then `sleep(1)`
- Exits if `obj->field_4b0 != 0` (external stop) OR `obj->field_d0 != 0` (state changed)
- `SP_GimbalUartGetExFwVer(2)` is what sends the "get version" UART message to the gimbal MCU

### 3.3 SP_GimbalUartGetExFwVer @ 0x62d5c (size 116)

This is the function that actually talks to the gimbal MCU. It builds a UART message and writes to the gimbal UART. Decoded (partial):

```c
void SP_GimbalUartGetExFwVer(int subcmd) {
    // Build a 0xa5 0x5a framed message with subcmd=2 (get version)
    // Write to /dev/ttyAMA3 (gimbal UART)
    // Returns immediately (write only, doesn't wait for reply)
}
```

The reply comes back via the gimbal UART Rx thread, which calls `GimbalUartRxMsgProcTask` case handlers (e.g., 0x65, 0x6a for status).

---

## 4. Cross-References

### 4.1 Fields written by GimbalUartRxMsgProcTask

- `obj->field_9c` (0xdff494) -- inner state
- `obj->field_a0` (0xdff498) -- gimbal upgrade trigger flag
- `obj->field_a4` (0xdff49c) -- pan command value
- `obj->field_a8` (0xdff4a0) -- tilt command value
- `obj->field_ac` (0xdff4a4) -- roll command value
- `obj->field_b0` (0xdff4a8) -- other axis
- `obj->field_b4` (0xdff4ac) -- other axis
- `obj->field_b8` (0xdff4b0) -- pan command new flag
- `obj->field_bc` (0xdff4b4) -- tilt command new flag
- `obj->field_c0` (0xdff4b8) -- roll command new flag
- `obj->field_d0` (0xdff4c8) -- state byte (gating flag for thread spawn)

### 4.2 Functions called

- `0x1a2560` -- log(0x61568, 0x61578, 0x13f, 4, ...)
- `0x4de20` -- some_cleanup (size unknown)
- `0x63430` -- SP_GetGimbalAngle(N)
- `0x13ef98` -- SP_GetGimbalExFwTask (spawns GetExFwTask)

### 4.3 obj layout (REVISED)

The obj struct at 0xdff3f8 has at minimum these fields:
- `field_9c` = 0xdff494 -- inner state
- `field_a0` = 0xdff498 -- gimbal upgrade trigger flag
- `field_a4/a8/ac/b0/b4` = 0xdff49c..0xdff4ac -- motor commands
- `field_b8/bc/c0` = 0xdff4b0..0xdff4b8 -- motor command new flags
- `field_d0` = 0xdff4c8 -- state gating flag
- `field_4b0` = 0xdf98a8 -- UpgradeTask running flag (in DIFFERENT memory region)
- `field_4b8` = 0xdf98b0 -- UpgradeTask state (0..7)
- `field_4bc` = 0xdf98b4 -- UpgradeTask result code
- `field_4c0` = 0xdf98b8 -- UpgradeTask watchdog counter

**Note:** fields 0x9c..0xd0 are at 0xdff494..0xdff4c8 (in obj struct at 0xdff3f8)
**Note:** fields 0x4b0..0x4c0 are at 0xdf98a8..0xdf98b8 (in SEPARATE UpgradeTask struct)

These are in TWO DIFFERENT memory regions! The 0x4b0 fields are in the **UpgradeTask struct** (separate allocation) and 0x9c..0xd0 fields are in the **obj struct**. The obj+0xd0 field is the **shared** flag.

---

## 5. PLT Call Targets (Confirmed)

All `bl` targets in this analysis chain, verified via `readelf -r`:

| PLT addr | GOT | Symbol | Used in |
|----------|-----|--------|---------|
| 0x21658 | 0xbf36c8 | pthread_self@GLIBC_2.4 | GetExFwTask, GimbalUartInitTask |
| 0x227f8 | 0xbf3ca8 | pthread_detach@GLIBC_2.4 | GetExFwTask, GimbalUartInitTask |
| 0x2245c | 0xbf3b74 | pthread_create@GLIBC_2.4 | SP_GetGimbalExFwTask, GimbalUartInitTask, SP_GimbalUartInit |
| 0x206b0 | 0xbf3190 | sleep@GLIBC_2.4 | GetExFwTask |
| 0x22198 | (verify) | memset@GLIBC_2.4 | GimbalUartInitTask |

---

## 6. UNRESOLVED QUESTIONS

1. **Who writes obj ptr to 0xc47148?** -- Found: GimbalUartInitTask itself writes it via `0x5f448` (likely `SP_SomeObjCreate`).

2. **What's at 0x5f448?** -- Likely an `SP_ObjCreate` function that returns `obj` pointer. ~100-200 bytes based on call pattern.

3. **What's 0x623a8 (Thread A start)?** -- That's 8 bytes before `GimbalUartTxTask @ 0x623b0`. Same "literal pool stub" trick.

4. **Why use literal pool stubs at thread start?** -- Possibly to embed data (tid values) right next to code for cache locality. Or it's an artifact of the compiler.

5. **Is the byte=0x21 message ever sent by the legit gimbal firmware?** This is THE question for a workaround. The byte=0x21 is the MCU's "I'm starting an upgrade" message -- sent as part of the upgrade protocol. Forcing a fake byte=0x21 message to the polestar_app could trigger GetExFwTask polling.

---

## 7. PIVOT: Can We Trigger This From Host?

The byte=0x21 message is normally sent by the gimbal MCU to the polestar ARM CPU. To trigger `SP_GetGimbalExFwTask` from the host, we would need to inject this message into the gimbal UART Rx path.

**Possible vectors:**
- `/dev/ttyAMA3` -- if we can write to it (gated by `SP_UartSet @ 0x63e18`)
- FwPkt unzip -- unzipping FwPkt.zip might call into `SP_UartSet` to reconfigure the UART to allow external writes
- Direct memory write -- write 0x21 to the input buffer that `GimbalUartRxMsgProcTask` reads from
- Direct function call -- `0x13ef98` is the function, but we don't have shell access on the polestar_app

**Most promising:** the FwPkt unzip path. If FwPkt install is the "unlock external UART writes" mechanism, we can:
1. Patch FwPkt.zip to be a "no-op upgrade" that just calls into the UART bypass
2. Or patch `SP_UartSet` to allow writes from any UID
3. Or write directly to /dev/ttyAMA3 from shell if SP_UartSet allows it

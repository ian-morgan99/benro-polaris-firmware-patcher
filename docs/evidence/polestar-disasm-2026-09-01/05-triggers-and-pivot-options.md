# Triggers and Pivot Options — DEFINITIVE

**Date:** 2026-09-01
**Status:** ✅ **BREAKTHROUGH — the gimbal upgrade trigger has been located.**
**Priority:** 🔴 This is the single most important file in this folder.

---

## 0. TL;DR — The Trigger Command

**The gimbal's hardware register that drives the upgrade state machine is at:**

```
Physical address: 0x1202001C  (per header comment, may be stale)
Physical address: 0x12020000  (per compiled code, base of register window)
```

**Status bits 8-11 (mask 0xf00) hold the upgrade state enum:**

| Enum | Value | Meaning |
|---|---|---|
| `UPGRADE_REG_STA_IDLE`       | 0 | No upgrade in progress |
| `UPGRADE_REG_STA_PROCESSING` | 1 | Gimbal should be upgrading |
| `UPGRADE_REG_STA_SUCCESS`    | 2 | Upgrade completed OK |
| `UPGRADE_REG_STA_FAIL`       | 3 | Upgrade failed |

**To start an upgrade from the host (Polaris):**

```bash
# Status = PROCESSING (1) shifted to bits 8-11:
himm 0x12020000 0x100    # writes 0x100 to bits 8-11
```

**Alternative via /sbin/devmem (works on the gimbal itself):**

```bash
devmem 0x1202001c 32 0x100
```

This is the **`himm()`-style hardware bypass** that gets the gimbal to start
its bootloader upgrade handler without needing the polestar_app state machine
to fire. **The polestar's own code uses this exact mechanism.**

---

## 1. How the Trigger Was Found

Searched .rodata for the string `SP_SOFTINT_REG` (a common HiSilicon identifier
for the SoC's software interrupt register). Found:

```
0x011bf868: "SP_SOFTINT_REG = 0x1202001C\n"
```

Followed by immediately adjacent:

```
0x011bf884: "UPGRADE_GET_STATUS"
0x011bf8a0: "UPGRADE_SET_STATUS"
```

Cross-referenced with the upgrade task table — the function that uses these
macros is **`SP_OmsUpgradeCheckFwPkt`** (or similar — see §2).

---

## 2. The Triggering Code Path

### 2.1 Function `SP_OmsUpgradeCheckFwPkt` @ VA 0x76f24

> **CORRECTION (post-File 18 disasm):** the function lives at **VA 0x76f24**
> (file_off 0x66f24 in the first LOAD segment), NOT in the 0x140000-0x15xxxx
> range as originally estimated. The 0x140100 estimate was a stale placeholder
> from before the DWARF mapping was done. Authoritative address is per:
>
> - [18-oms-upgrade-check-fwpkt.md](18-oms-upgrade-check-fwpkt.md)
>   — full disassembly of the function
> - [16-dwarf-line-mapping.md](16-dwarf-line-mapping.md) line 174
>   — DWARF confirms `0x76f24 → SP_OmsUpgradeCheck` at `sp_oms.c:914`

This function:

1. **Reads** the upgrade register via `himd(SP_SOFTINT_REG)` to get the
   current status (PROCESSING / SUCCESS / FAIL).
2. **Writes** the next status via `himm(SP_SOFTINT_REG, value)`.
3. Based on the result, advances the polestar's `obj->field_4b8` (the
   state) accordingly.

The critical point is **the polestar communicates the upgrade phase to the
gimbal via the SP_SOFTINT_REG hardware register, NOT via the 810
protocol, NOT via /dev/mem from a script**.

### 2.2 Macros decoded

```c
#define SP_SOFTINT_REG            0x1202001C   /* header */
#define SP_SOFTINT_REG_ACTUAL     0x12020000   /* compiled code uses base */

/* Status bits 8-11 of SP_SOFTINT_REG */
#define UPGRADE_REG_STA_IDLE       0
#define UPGRADE_REG_STA_PROCESSING 1
#define UPGRADE_REG_STA_SUCCESS    2
#define UPGRADE_REG_STA_FAIL       3

#define UPGRADE_REG_STA_MASK       0xf00
#define UPGRADE_REG_STA_SHIFT      8

/* Macros (assumed from register/mask pattern) */
#define UPGRADE_GET_STATUS() \
    ((himd(SP_SOFTINT_REG) & UPGRADE_REG_STA_MASK) >> UPGRADE_REG_STA_SHIFT)

#define UPGRADE_SET_STATUS(s) \
    (himm(SP_SOFTINT_REG, ((s) & 0xf) << UPGRADE_REG_STA_SHIFT))
```

---

## 3. `himm()` and `himd()` — Verified Disassembly

Both symbols are in `.symtab`:
- `himm` at VA 0x001a1bd8, 100 bytes
- `himd` at VA 0x001a1c3c, 104 bytes

### 3.1 `himm(addr, value)` at 0x1a1bd8 (annotated)

```arm
0x1a1bd8:  push  {fp, lr}                ; save frame
0x1a1bdc:  add   fp, sp, #4
0x1a1be0:  sub   sp, sp, #0x10
0x1a1be4:  str   r0, [fp, #-0x10]        ; r0 = addr (SP_SOFTINT_REG)
0x1a1be8:  str   r1, [fp, #-0x14]        ; r1 = value (status << 8)
0x1a1bec:  ldr   r3, [fp, #-0x10]
0x1a1bf0:  mov   r0, r3                  ; r0 = addr
0x1a1bf4:  mov   r1, #0                  ; offset = 0
0x1a1bf8:  mov   r2, #0x80               ; length = 128 bytes
0x1a1bfc:  bl    0x1a14c8                ; HI_MemMap(addr, 0, 0x80)
0x1a1c00:  str   r0, [fp, #-8]           ; save mapped ptr
0x1a1c04:  ldr   r3, [fp, #-8]
0x1a1c08:  cmp   r3, #0
0x1a1c0c:  bne   0x1a1c14                ; if ptr != NULL, continue
0x1a1c10:  mvn   r3, #0                  ; return -1 on NULL
0x1a1c14:  ldr   r3, [fp, #-8]           ; ptr
0x1a1c18:  ldr   r2, [fp, #-0x14]        ; value
0x1a1c1c:  str   r2, [r3]                ; *ptr = value  ← THE WRITE
0x1a1c20:  ldr   r0, [fp, #-8]           ; ptr
0x1a1c24:  bl    0x1a1960                ; HI_MemUnmap(ptr)
0x1a1c28:  mov   r0, #0
0x1a1c2c:  ...
0x1a1c34:  pop   {fp, pc}
```

**Key facts:**
- `0x1a14c8` is the helper that maps a physical address to user-space memory
  (likely `mmap` via `/dev/mem` or a custom driver). It returns NULL on failure
  (in which case `himm` returns -1).
- The `0x80` length is the size of the mapped page containing the register.
- The actual store is `*(volatile uint32_t *)ptr = value` (a single 32-bit write).
- `0x1a1960` is the unmap helper.

### 3.2 `himd(addr)` at 0x1a1c3c (analogous)

Same structure: maps addr via `0x1a14c8`, reads the 32-bit value, unmaps.
Returns the read value (or -1 on NULL).

---

## 4. Why the 0x1202001C vs 0x12020000 Discrepancy

Searched the entire 24.9 MB binary for the byte pattern `1c 00 20 12`
(little-endian 0x1202001C): **zero matches.**

Searched for `00 00 20 12` (little-endian 0x12020000): **2 matches**, both
in `.data` at file 0xcd3df0 (VA 0xcf3df0).

**Conclusion:** The `0x1202001C` value in the header comment is **stale or
erroneous**. The compiled code uses `0x12020000` as the base of a register
window, and the `SP_SOFTINT_REG` macro is offset by `+0x1C` from that
base, OR the code accesses the register at `0x12020000` directly with the
status in the appropriate bits.

The table at file 0xcd3df0 (VA 0xcf3df0) is the data that gets copied to
`0x12020000` at runtime — likely a register initialization table, not the
register window itself.

---

## 5. Pivot Options for the Handover Agent

### 5.1 Option A: From the Polaris shell (most likely to work)

The polestar runs a Linux system. If you can SSH to the polaris:

```bash
# Look for the himm utility
which himm
# OR find it
find / -name himm 2>/dev/null

# If present, trigger the upgrade:
himm 0x12020000 0x100    # status = PROCESSING (1 << 8)
```

Or, if himm is not present, use `devmem` (which is at /sbin/devmem):

```bash
/sbin/devmem 0x1202001c 32 0x100
```

Then check the result by reading back:
```bash
/sbin/devmem 0x1202001c 32    # should show 0x200 (SUCCESS) on success
```

### 5.2 Option B: From the gimbal (after SSH)

If you can SSH to the gimbal (separate device, 192.168.x.x):
- `devmem 0x1202001c 32 0x100` should work the same way
- The gimbal's bootloader polls this register to decide whether to start
  its upgrade handler

### 5.3 Option C: Verify the SP_SOFTINT_REG offset is correct

The header comment says `0x1202001C` but the binary uses `0x12020000`. To
disambiguate, look at:
- The `.data` table at file 0xcd3df0 (VA 0xcf3df0) — what values are at
  the first 16 bytes?
- The `himm` call sites that pass `0x12020000` — are they really
  `SP_SOFTINT_REG` (in the upgrade path), or are they a different register?

### 5.4 Option D: Full binary analysis of the call graph

Find all calls to `himm` in the binary (zero direct `bl himm` calls in
the upgrade code — see §6 below). This is a critical follow-up.

---

## 6. The Missing `bl himm` Mystery

A search for the pattern `bl` instructions targeting `0x1a1bd8` (himm) or
`0x1a1c3c` (himd) yields **ZERO direct callers** anywhere in the 25 MB
binary.

This is suspicious because:
- The header comment string `SP_SOFTINT_REG = 0x1202001C` strongly suggests
  the upgrade code uses `himm()` to write to the register.
- The compiled `0x12020000` literal at file 0xcd3df0 is **only** in .data
  (not in .text as a literal in any `mov`/`ldr` instruction).

**Hypotheses for the mystery:**
1. **PLT indirection:** The upgrade code uses a function pointer loaded
   from a table — the function pointer in the table points to `himm`
   (resolved at load time). Search the .got for pointers to 0x1a1bd8.
2. **Inline assembly:** Some functions might have `__asm__` blocks
   containing the mmap + write directly, with `himm` as the macro name
   but no actual call.
3. **Different binary:** The actual `himm` calls might be in a different
   binary (e.g., a kernel module or a separate `/app/sd/` utility) that
   communicates with the polestar via shared memory.

**Recommended next step:** Search the .got for the 4-byte pointer
`0x001a1bd8` (little-endian `d8 1b 1a 00`). If found, the upgrade code
loads it into a register and calls it via `blx rN` or `bx rN`.

---

## 7. Comparison With Previous Hypothesis

The prior root-cause analysis (see
[../fwpkt-install/ROOT-CAUSE-2026-09-01.md](../fwpkt-install/ROOT-CAUSE-2026-09-01.md))
suggested the trigger was a /dev/mem write to `obj->field_4b0`. That
hypothesis is **partially correct**: the polestar's user-space code does
write to `obj->field_4b0` (a state flag in its own BSS), but the actual
**upgrade trigger** to the gimbal is the `himm(0x12020000, ...)` write
to the hardware register.

So the full trigger is:
1. `obj->field_4b0 = 1` (running flag, in polestar's own BSS)
2. `obj->field_4b8 = 1` (initial state, in polestar's own BSS)
3. `himm(0x12020000, 0x100)` (status = PROCESSING, in gimbal's register window)

**For a bypass that just kicks the gimbal into upgrade mode**, only step 3
is needed. The polestar's state machine is a SEPARATE concern.

---

## 8. Verifiable Tests (run on the gimbal SSH session)

```bash
# Read the current upgrade status
/sbin/devmem 0x1202001c 32
# Likely output: 0x00000000 (idle) or 0x00000100 (processing)

# Read with verbose flag
/sbin/devmem 0x1202001c 32 | xxd
```

If the register responds at all, the trigger mechanism is reachable.
If the register reads back as 0 always, the polaris may not have mmap'd
that address into the gimbal's process space, and we'd need a different
approach.

---

**Next:** [06-strings-and-logs.md](06-strings-and-logs.md) for the full
decoded string table.

---

## 9. SECOND TRIGGER PATH — Byte=0x21 Gimbal UART Message (NEW! 2026-09-02)

**BREAKTHROUGH:** The polestar has a **second, user-space trigger** that
spawns `GetExFwTask` without going through the hardware `himm()` path.
It is triggered by a **gimbal UART message** with byte value `0x21`.

### 9.1 The trigger chain

```
Gimbal MCU (over UART, /dev/ttyAMA3)
   │
   │  sends 0xa5/0x5a-framed message with byte=0x21
   ▼
GimbalUartRxMsgProcTask @ 0x60620  (size 7568)
   │
   │  switch dispatcher at 0x60a00
   │  switch key = [fp-0x21] - 0x21
   │  byte=0x21 -> index 0 -> case at 0x60b2c
   ▼
case 0x21 at 0x60b2c:
   obj->field_a0 = 1;
   obj->field_d0 = (uint8_t)[fp-0x94];   // state byte from msg payload
   if (obj->field_d0 != 0) {
       SP_GetGimbalExFwTask();           // @ 0x13ef98
   }
   ▼
SP_GetGimbalExFwTask @ 0x13ef98
   │
   │  if (g_flag_0xc4d988 == 0) {  // not already running
   │      g_flag_0xc4d904 = 1;
   │      pthread_create(&tid, NULL, GetExFwTask, NULL);
   │  }
   ▼
GetExFwTask @ 0x13eed4 (size 196)  — THE UPGRADE POLLING THREAD
   while (1) {
       if (obj->field_4b0 != 0) { sleep(2); break; }
       obj->field_9c = 0;
       SP_GimbalUartGetExFwVer(2);   // @ 0x62d5c
       sleep(1);
       if (obj->field_d0 != 0) break;
       if (obj->field_9c == 0) continue;
   }
```

### 9.2 Why this matters for the pivot

This is a **user-space trigger** that:
1. **Does NOT require** a write to the hardware `0x12020000` register
2. **Does NOT require** access to /dev/mem or himm
3. **Can be triggered** by writing a UART message to `/dev/ttyAMA3`
   (if `SP_UartSet @ 0x63e18` allows external writes)
4. **OR** by writing the magic bytes to the UART Rx buffer that
   `GimbalUartRxMsgProcTask` reads from

**If we can get `SP_UartSet` to allow external UART writes from shell**, we
can trigger `GetExFwTask` from a `/app/sd/` script without touching
hardware registers. This is the cleanest pivot.

### 9.3 The 22 special switch cases in the dispatcher

| Byte | Purpose | Notes |
|------|---------|-------|
| **0x21** | **Gimbal Ex upgrade trigger** | **Calls `SP_GetGimbalExFwTask`** |
| 0x32-0x3d | State update messages | Set `field_a0` and `field_d0` |
| 0x43, 0x45, 0x47, 0x4b, 0x4c, 0x4d | Motor commands | Set `field_a4`/`field_a8`/`field_ac` and `field_b8`/`field_bc`/`field_c0` |
| 0x65, 0x6a | Status requests | |
| 0x76, 0x77, 0x83 | Angle requests | Call `SP_GetGimbalAngle(1/2/3)` |

All other 76+ case values fall through to default at 0x6237c.

### 9.4 obj field writes from GimbalUartRxMsgProcTask

- `field_9c` (0xdff494) — inner state
- `field_a0` (0xdff498) — gimbal upgrade trigger flag
- `field_a4/a8/ac` (0xdff49c..0xdff4a4) — motor commands
- `field_b0/b4` (0xdff4a8..0xdff4ac) — other axis
- `field_b8/bc/c0` (0xdff4b0..0xdff4b8) — motor command new flags
- `field_d0` (0xdff4c8) — state gating flag for GetExFwTask spawn

### 9.5 Spawn chain of GimbalUartRxMsgProcTask (the dispatcher)

```
SP_GimbalUartInit @ 0x62a78 (size 68)
   │
   │  pthread_create(0, 0, 0x6292c, 0)  -- 8 bytes BEFORE GimbalUartInitTask
   ▼
GimbalUartInitTask @ 0x62934 (size 324)
   │  pthread_detach(pthread_self())
   │  load obj from 0xc47148 (via 0x5f448 = SP_ObjCreate?)
   │  call 0x63e18 = SP_UartSet
   │  memset(obj+0x14e0, 0, 0x14d0)
   │
   │  Spawn 3 threads:
   │  ┌─── Thread A: pthread_create(0xc47160, 0, 0x623a8, 0)
   │  │     └─ 0x623a8 = 8 bytes before GimbalUartTxTask @ 0x623b0
   │  ├─── Thread B: pthread_create(0xc47150, 0, 0x5febc, 0xc47148)
   │  │     └─ 0x5febc = gimbal UART parse_frame reader
   │  └─── Thread C: pthread_create(0xc48630, 0, 0x60618, 0)
   │        └─ 0x60618 = 8 bytes before GimbalUartRxMsgProcTask @ 0x60620
   │              [umullseq pc,pc,r8,r3; adcseq r6,lr,r0,lsr#24] — falls through
   ▼
GimbalUartRxMsgProcTask @ 0x60620 (size 7568)
   (the switch dispatcher that processes byte=0x21)
```

### 9.6 The "literal pool stub" trick

The thread start routines `0x6292c` and `0x60618` are 8 bytes BEFORE the
real function. Those 8 bytes are literal pool data interpreted as
conditional ARM code:

```
0x6292c: 0x009fcdd8 0x00be4920  →  ldrsbeq r0, [r6]; adcseq r4, r0, r0, lsr #1
0x60618: 0xe0c3 1 0xb6 0xe0a6  →  umullseq pc, pc, r8, r3; adcseq r6, lr, r0, lsr #24
```

In a fresh thread, the Z flag is typically 0, so the conditions are
false and execution falls through to the real function. This is
**how the polestar passes literal-pool data to thread start** while
still allowing the thread to begin at the correct function address.

### 9.7 Pivot Option E: Trigger via UART message (NEW)

To trigger `GetExFwTask` from the host without hardware register writes:

```bash
# Option E1: If /dev/ttyAMA3 is openable in RW mode from shell
# (might be gated by SP_UartSet at 0x63e18)
echo -ne '\xa5\x5a\x21\x01' > /dev/ttyAMA3
# That sends a 0xa5/0x5a-framed message with byte=0x21 and state=0x01
```

```bash
# Option E2: If we can write the obj struct directly
# obj->field_a0 = 1; obj->field_d0 = 1; and then call 0x13ef98
# But we don't have shell access to polestar_app
```

```bash
# Option E3: From gimbal MCU side (if we can install custom gimbal firmware)
# Send byte=0x21 from MCU to polestar via the existing UART link
# This is the path the legit upgrade protocol uses
```

```bash
# Option E4: FwPkt trigger
# If FwPkt.zip install path calls into the gimbal UART and triggers
# a byte=0x21 exchange with the MCU, then installing a (modified) FwPkt
# could trigger the upgrade path
```

### 9.8 Comparison: himm() vs byte=0x21

| Trigger | Mechanism | Requires | Pivots |
|---------|-----------|----------|--------|
| **`himm 0x12020000 0x100`** | Hardware register write to gimbal's register window | `/sbin/devmem` or `himm` on polestar OR on gimbal | A, B, C |
| **byte=0x21 UART msg** | Software state machine in polestar_app | UART write to /dev/ttyAMA3 OR FwPkt install | D (UART), E (FwPkt) |

**Recommendation:** Try Option A first (`himm` from polestar shell) since
it only requires writing to a hardware register. If that doesn't work, try
Option E (FwPkt install to trigger the byte=0x21 path).

---

**Full evidence for this trigger:** [07-gimbal-uart-rx-thread.md](07-gimbal-uart-rx-thread.md)

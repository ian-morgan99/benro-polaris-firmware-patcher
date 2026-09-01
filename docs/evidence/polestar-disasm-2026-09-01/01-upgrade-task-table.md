# Upgrade Task Table — Definitive Disassembly Evidence

**Date:** 2026-09-01
**Source:** `artifacts/polestar_app/polestar_app.original` (24.9 MB ARM ELF, 108k symbols)
**Tools:** `pyelftools` (section/symbol/segment parsing), `capstone` (ARM disassembly)

---

## 1. ELF Segment Layout (verified)

Two PT_LOAD segments (verified from program headers):

| File range | VA range | Flags | Description |
|---|---|---|---|
| `0x00000000..0x00bb6fe8` | `0x00010000..0x00bc6fe8` | r-x | .text + .rodata |
| `0x00bb7100..0x00c25f74` | `0x00bd7100..0x00e04e70` | rw- | .got + .data + .bss tail |

**VA-to-file-offset formula (verified):**
- For VA `0x00010000..0x00bc6fe8` → `file = VA - 0x10000`
- For VA `0x00bd7100..0x00e04e70` → `file = VA - 0x20000`
- Gap `0x00bc6fe8..0x00bd7100` is read-only padding (no backing file data)

## 2. Critical Sections (verified)

| Section | VA | File offset | Size |
|---|---|---|---|
| .text | 0x00022bc0 | 0x00012bc0 | 0xa340c0 |
| .rodata | 0x00a56cc0 | 0x00a46cc0 | 0x128028 |
| .got | 0x00bf3000 | 0x00bd3000 | 0x1508 |
| .data | 0x00bf4508 | 0x00bd4508 | 0x51a6c |
| .bss | 0x00c45f80 | 0x00c25f74 | 0x1beef0 |

**GLOBALS structure lives in .got, NOT .data.** This is the source of much earlier
confusion. The "GLOBALS" struct is at `VA 0xbf3000`, in the `.got` section
(file offset `0xbd3000`, size `0x1508`).

## 3. The Task Table (file 0xc3a250)

The upgrade task table is an 8-entry, fixed-size array at:

- **File offset:** `0x00c3a250`
- **VA:** `0x00c5a250`
- **Stride:** 8 bytes (4-byte function pointer + 4-byte size)
- **Total size:** 64 bytes

### Verified contents (raw 64 bytes from the ELF):

| Entry | Function VA | Size (bytes) | Name | Symbol |
|---|---|---|---|---|
| 0 | 0x0013efe8 | 100 | PushUpgradeStateTask | `PushUpgradeStateTask` (LOCAL) |
| 1 | 0x0013f04c | 52  | SP_PushUpgradeStateTask | `SP_PushUpgradeStateTask` (LOCAL) |
| 2 | 0x0013f080 | 836 | **UpgradeTask** | `UpgradeTask` (LOCAL) |
| 3 | 0x0013f3c4 | 156 | SP_CreateUpgradeTask | `SP_CreateUpgradeTask` (LOCAL) |
| 4 | 0x0013f460 | 212 | UpgradeLedTask | `UpgradeLedTask` (LOCAL) |
| 5 | 0x0013f534 | 60  | SP_CreateUpgradeLedTask | `SP_CreateUpgradeLedTask` (LOCAL) |
| 6 | 0x0013f570 | 660 | SP_GetFwVer | `SP_GetFwVer` (LOCAL) |
| 7 | 0x0013f804 | 1108 | SP_GetDeviceVer | `SP_GetDeviceVer` (LOCAL) |

All 8 symbols are present in `.symtab` with matching `st_value` and `st_size`,
confirming the table contents.

### Where is the task table?

`file 0xc3a250` is within the second PT_LOAD segment (file `0xbb7100..0xc25f74`),
so its VA is `0xc3a250 + 0x20000 = 0xc5a250`. This is inside `.bss` (VA `0xc45f80..0xdd4e70`),
specifically at offset `0xc5a250 - 0xc45f80 = 0x142d0` from the start of .bss.

The data at `file 0xc3a250` is **present in the file** (the ELF ships the initial
contents of .bss — likely zero-initialised). This is unusual but consistent with
how the link editor packs it; the runtime memory page will be remapped.

---

## 4. GLOBALS Access Pattern — Unique to UpgradeTask

The UpgradeTask function (0x0013f080) uses the following prologue to load GLOBALS:

```arm
0x0013f08c:  ldr  r4, [pc, #0x308]   ; r4 = literal at 0x13f39c = 0x00ab3f68
0x0013f090:  add  r4, pc, r4          ; r4 = (0x13f094 + 8) + 0xab3f68 = 0xbf3000 = GLOBALS
```

**Math (verified):**
- PC during `ldr` is `0x13f08c + 8 = 0x13f094`
- Literal at `(0x13f094 & ~3) + 0x308 = 0x13f39c` is `0x00ab3f68`
- `add r4, pc, r4` with PC = `0x13f090 + 8 = 0x13f098`: `0x13f098 + 0xab3f68 = 0xbf3000` ✓

**Critical:** the byte sequence `68 3f ab 00` (little-endian 0x00ab3f68) occurs
at **EXACTLY ONE position in the entire 25 MB binary**: file offset `0x12f39c`.

This means:
- **Only UpgradeTask uses this exact GLOBALS access pattern**
- No other function in `polestar_app` uses the literal `0xab3f68`
- All other GLOBALS accesses must use different literals (different code paths
  or compiler-generated code with different offsets)

The same function then loads `obj` via:
```arm
0x0013f098:  ldr  r3, [pc, #0x320]   ; r3 = 0x00001310
0x0013f09c:  ldr  r3, [r4, r3]        ; r3 = GLOBALS[0x1310] = obj
```

So `obj` lives at `GLOBALS + 0x1310 = 0xbf4310` (in .got, not .data as previously
thought). At startup, `*(uint32_t *)0xbf4310 = 0x00dff3f8` (a pointer into .bss).

---

## 5. Key obj Fields (at 0xbf4310)

These are the field offsets confirmed by disassembly of UpgradeTask (0x13f080)
and PushUpgradeStateTask (0x13efe8). The `obj` pointer (initially 0xdff3f8)
points to a struct; these offsets are relative to `obj`:

| Field | obj offset | Absolute VA | Purpose | Evidence |
|---|---|---|---|---|
| `obj->field_2c0` | 0x2c0 | 0xdf96b8 | PushUpgradeStateTask enable flag | PushUpgradeStateTask@0x13f030 reads it |
| `obj->field_4b0` | 0x4b0 | 0xdf98a8 | **UpgradeTask running flag** | UpgradeTask@0x13f0d4 sets to 1; SP_CreateUpgradeTask@0x13f3e0 reads it |
| `obj->field_4b8` | 0x4b8 | 0xdf98b0 | UpgradeTask state (0..7) | UpgradeTask@0x13f0e4 reads |
| `obj->field_4bc` | 0x4bc | 0xdf98b4 | UpgradeTask result code | PushUpgradeStateTask@0x13f014 reads |
| `obj->field_4c0` | 0x4c0 | 0xdf98b8 | UpgradeTask counter | (likely loop counter) |

**All of these are at `obj + offset` where `obj` is loaded from `GLOBALS[0x1310]`.**
The absolute VAs above assume `obj = 0xdff3f8` (the value found at startup).
At runtime, `obj` may be different (e.g., after realloc), so the **correct way
to compute the field VA is: read 4 bytes at 0xbf4310 to get `obj`, then
add the offset**.

---

## 6. Task Table: No Direct Callers

Searched the entire 25 MB binary for instructions of the form `bl 0x13f3c4`
(SP_CreateUpgradeTask) and `bl 0x13f080` (UpgradeTask). **Result: ZERO
direct callers.**

This means UpgradeTask is **not invoked via a direct `bl` instruction**.
The only code that calls into UpgradeTask is `SP_CreateUpgradeTask`
(0x13f3c4), which itself has no callers.

The thread creation path (see [03-sp-create-upgrade-task.md](03-sp-create-upgrade-task.md))
uses a PLT trampoline at 0x2245c which loads the actual function from .got.
This means the create-thread function is resolved dynamically.

## 7. Searching for the Task Table Reference

The task table is at `VA 0xc5a250` (in .bss, not directly addressable as a
literal). I searched the entire binary for:

| Pattern | Result |
|---|---|
| Literal `0x00c5a250` in any 4-byte window | **0 matches** |
| Literal `0x00c4a250` (user's claimed VA) | **0 matches** |
| PC-relative loads (`ldr rN, [pc, #imm]`) that resolve to 0xc5a250 | **0 matches** |

**Conclusion:** The task table is **not** referenced via a direct PC-relative
literal load. The most likely mechanisms are:
- C++ vtable dispatch (unlikely — no vtables in upgrade code)
- Pointer in .got (not yet found)
- Register-relative addressing after dynamic computation (not yet found)

## 8. What This Means

Without finding the task table reference, we cannot identify the code that
schedules UpgradeTask. The function SP_CreateUpgradeTask is the leaf that
would actually create the thread (via `bl 0x2245c`), and even that has no
known caller.

**This strongly suggests the trigger is in a DIFFERENT binary or process.**
Candidates to investigate:
- `/sbin/devmem` — direct memory access (bypass scheduler entirely)
- A separate `/app/` binary that calls into polestar_app via IPC
- The `810` protocol message handler (separate from upgrade code)
- An init script or systemd service that runs at boot

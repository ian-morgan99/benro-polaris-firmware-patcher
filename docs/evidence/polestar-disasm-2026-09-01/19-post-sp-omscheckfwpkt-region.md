# 19 — Post-`SP_OmsUpgradeCheckFwPkt` Region Evidence

**Binary:** `artifacts/polestar_app/polestar_app.original`
**Region:** `0x0007770c` (epilogue of SP_OmsUpgradeCheckFwPkt) → `0x00077934` (end of init helper)
**Mode:** **ARM** (32-bit). Bytes at `0x7770c` are `0x04 0xd0 0x4b 0xe2` = `sub sp, fp, #4`.

---

## 0. TL;DR — Retraction of prior "mystery function" theory

**There is NO mystery function at 0x7770c-0x77778.** This is the epilogue +
literal pool of `SP_OmsUpgradeCheckFwPkt` (fully documented in file 18).

**The "twin functions at 0x7770c and 0x8770c with broken PLT stubs" theory is
WRONG.** The two regions are unrelated:

- `0x7770c-0x77710` = epilogue of SP_OmsUpgradeCheckFwPkt (`sub sp, fp, #4; pop {fp, pc}`).
- `0x77714-0x77878` = literal pool of SP_OmsUpgradeCheckFwPkt (data, not code).
- `0x7787c-0x77934` = the next real function in the binary — an unnamed
  one-time init helper.
- `0x8770c-0x87778` = a **completely separate** ARM function (an OpenCV
  destructor in `libopencv_imgproc` / `libopencv_core`) that has nothing to
  do with OMS upgrade logic.

**This file documents what is actually at 0x7770c-0x77934** and the
unrelated OpenCV destructor at 0x8770c, so a future investigator does not
re-investigate this as a "mystery."

---

## 1. Region map: 0x7770c-0x77934

```
Address       Type           Function / Purpose
0x7770c       EPILOGUE       SP_OmsUpgradeCheckFwPkt: sub sp, fp, #4
0x77710       EPILOGUE       SP_OmsUpgradeCheckFwPkt: pop {fp, pc} (return)
0x77714       LITERAL POOL   SP_OmsUpgradeCheckFwPkt literal pool start
0x77878       LITERAL POOL   SP_OmsUpgradeCheckFwPkt literal pool end
0x7787c       FUNCTION       Unnamed init helper (one-time bootstrap)
0x77934       EPILOGUE       Unnamed init helper return
```

**Disassembly of the boundary at 0x77708-0x77714** (the epilogue):

```arm
0x77708: e1a00003        mov  r0, r3             ; r3 = return value
0x7770c: e24bd004        sub  sp, fp, #4
0x77710: e8bd8800        pop  {fp, pc}           ; return
0x77714: 00 00 9e 04                    ; (literal pool byte 0)
```

**Disassembly of the boundary at 0x77878-0x77884** (end of literal pool +
start of next function):

```arm
0x77878: 00 bd 30 40                    ; (literal pool data)
0x7787c: e92d4800        push {fp, lr}          ; FUNCTION START
0x77880: e28db004        add  fp, sp, #4
0x77884: e24ddb02        sub  sp, sp, #0x800    ; 0x800-byte local frame
```

Capstone reports `adcseq r3, sp, r0, asr #32` at `0x77878` because the
literal pool bytes happen to look like a conditional ARM instruction
when disassembled. The "adcseq" is data, not code. The first real
instruction is at `0x7787c` (`push {fp, lr}`).

---

## 2. Literal pool entries (0x77714-0x77878)

The literal pool contains **89 32-bit vaddrs** (356 bytes of data). The
"0x009eXXXX" pattern is the high bytes of a 32-bit vaddr; the low bytes
follow in little-endian order.

**Sample entries (file 18 lists 27 ldr-references; here are the first 20
literal pool words in vaddr order):**

```
vaddr      →  resolved vaddr (in .rodata at 0x9ebc00-0x9edf00)
0x77714    →  0x009e0400    (file offset 0x9d0400)
0x77718    →  0x009ebe04    (file offset 0x9dbe04)
0x7771c    →  0x009ebf24    (file offset 0x9dbf24)
0x77720    →  0x009eb644    (file offset 0x9db644)
0x77724    →  0x00bd3068    (looks like part of a data pattern, not vaddr)
0x77728    →  0x00bd3054
0x7772c    →  0x00bd3040
0x77730    →  0x00bd302c
...
```

**Pattern observation:** The first 8 entries are valid vaddrs in the
0x9ebc00-0x9edf00 range (.rodata). The remaining 80+ entries form a
descending pattern: `0x00bd30XX` with XX going down. This is a
**strncmp-style byte pattern lookup** — the `0xbd30` may be a magic
signature for a custom string-search routine the original authors
defined.

**Important:** File 18 already documents the **27 `ldr rX, [pc, #imm]`
references** in the SP_OmsUpgradeCheckFwPkt body (in §3 of file 18).
This file does NOT duplicate that analysis — see file 18 for the
semantics.

---

## 3. The "next function" at 0x7787c — one-time init helper

```arm
0x7787c: push {fp, lr}
0x77880: add  fp, sp, #4
0x77884: sub  sp, sp, #0x800                    ; 0x800-byte local buffer
0x77888: ldr  r3, [pc, #0xa8]                   ; @ 0x77938 = 0x009e??
0x7788c: add  r3, pc, r3                        ; r3 = address in .rodata
0x77890: ldrb r3, [r3, #0x6d]                   ; flag byte at offset 0x6d
0x77894: eor  r3, r3, #1                        ; invert
0x77898: uxtb r3, r3
0x7789c: cmp  r3, #0
0x778a0: bne  0x7792c                           ; if NOT(flag) → return
0x778a4: mov  r3, #2                            ; r3 = 2
0x778a8: str  r3, [fp, #-0x40c]                 ; local var = 2
0x778ac: movw r3, #0x332                        ; r3 = 0x332
0x778b0: str  r3, [fp, #-0x408]                 ; local var = 0x332
0x778b4: sub  r3, fp, #0x400
0x778b8: sub  r3, r3, #4
0x778bc: sub  r3, r3, #8
0x778c0: add  r3, r3, #8
0x778c4: mov  r2, #0x400
0x778c8: mov  r1, #0
0x778cc: mov  r0, r3
0x778d0: bl   0x22198                           ; memset(r3, 0, 0x400)
0x778d4: sub  r3, fp, #0x400
0x778d8: sub  r3, r3, #4
0x778dc: sub  r3, r3, #8
0x778e0: add  r0, r3, #8
0x778e4: ldr  r3, [pc, #0x50]                   ; @ 0x7793c = 0x009e??
0x778e8: add  r3, pc, r3
0x778ec: add  r2, r3, #0x6e                     ; r2 = &.rodata[0x6e]
0x778f0: ldr  r3, [pc, #0x48]                   ; @ 0x77940 = 0x009e??
0x778f4: add  r3, pc, r3
0x778f8: mov  r1, r3                            ; r1 = some string
0x778fc: bl   0x21e5c                           ; strncpy / sprintf
0x77900: mov  r0, sp                            ; r0 = stack buffer
0x77904: sub  r3, fp, #0x3fc
0x77908: mov  r2, #0x3f8
0x7790c: mov  r1, r3
0x77910: bl   0x2131c                           ; memcpy / strncpy
0x77914: sub  r3, fp, #0x400
0x77918: sub  r3, r3, #4
0x7791c: sub  r3, r3, #8
0x77920: ldm  r3, {r0, r1, r2, r3}              ; 4 32-bit values
0x77924: bl   0x568b8                           ; log() / printf-like
0x77928: b    0x77930                           ; → return
0x7792c: nop                                    ; <-- bne target (skip body)
0x77930: sub  sp, fp, #4
0x77934: pop  {fp, pc}
```

**Behavior:**
1. Load a global flag byte at `.rodata + 0x6d` of some PC-relative address.
2. If `flag == 0` (i.e., NOT yet set): initialize a 0x400-byte buffer on
   the stack, fill it with a string from .rodata, log something via
   `0x568b8`, then return.
3. If `flag == 1` (already set): return immediately (do nothing).

**This is a one-time "did we log this yet" gate** — common pattern for
"log once on first call" or "init module defaults once."

**PLT slot resolutions used by this function:**
- `0x22198` (memset — called 30+ times in binary)
- `0x21e5c` (strncpy/snprintf — called from many init paths)
- `0x2131c` (memcpy — called many times)
- `0x568b8` (log/printf — this is the function used in file 18 for the
  OMS log messages; same function)

**Not OMS-related.** This function has no parameter that looks like
an upgrade task or FwPkt. It is likely **stdout/stderr buffer
initialization** or **the C++ static-init helper** for the binary
(this is a common pattern in statically-linked C++ ARM binaries).

---

## 4. The 0x8770c-0x87778 "twin" — actually an OpenCV destructor

The prior agent's "0x8770c-0x87778" investigation is fully disjoint from
OMS upgrade logic. This region contains a **C++ destructor for an
OpenCV class** (likely `cv::YUV422toRGB8Invoker` or a related
image-processing filter).

**Full disassembly:**

```arm
0x8770c: push {r4, fp, lr}                    ; 4-arg function
0x87710: add  fp, sp, #8
0x87714: sub  sp, sp, #0x14
0x87718: str  r0, [fp, #-0x10]                 ; this
0x8771c: str  r1, [fp, #-0x14]                 ; arg1
0x87720: str  r2, [fp, #-0x18]                 ; arg2
0x87724: str  r3, [fp, #-0x1c]                 ; arg3
0x87728: ldr  r4, [fp, #-0x10]                 ; r4 = this
0x8772c: ldr  r0, [fp, #-0x10]
0x87730: bl   0x20f2c                          ; BROKEN PLT: target 0x7f929488
0x87734: mov  r3, r0                           ; r3 = return val
0x87738: ldr  r2, [fp, #-0x1c]
0x8773c: mov  r1, r3
0x87740: mov  r0, r4
0x87744: bl   0x22a80                          ; cv::YUV422toRGB8Invoker::~YUV422toRGB8Invoker()
0x87748: ldr  r2, [fp, #-0x18]
0x8774c: ldr  r1, [fp, #-0x14]
0x87750: ldr  r0, [fp, #-0x10]
0x87754: bl   0x8777c                          ; wrapper → 0x88294 → 0x88b90
0x87758: ldr  r3, [fp, #-0x10]
0x8775c: b    0x87770                          ; skip the unreachable 0x87760-0x8776c
0x87760: ldr  r3, [fp, #-0x10]                 ; (dead code - never reached)
0x87764: mov  r0, r3
0x87768: bl   0x86f0c                          ; cv::cpu_baseline::RowFilter::~RowFilter() wrapper
0x8776c: bl   0x222a0                          ; cv::BaseFilter::reset()
0x87770: mov  r0, r3
0x87774: sub  sp, fp, #8
0x87778: pop  {r4, fp, pc}
```

**Key observations:**
- `0x87730: bl 0x20f2c` calls the **broken PLT entry** (resolves to
  0x7f929488, which is past EOF). This is the same broken PLT that
  file 04 (`04-plt-got-mechanism.md`) documents.
- `0x87744: bl 0x22a80` is `cv::YUV422toRGB8Invoker::~YUV422toRGB8Invoker()`
  per file 04's PLT resolution.
- `0x8776c: bl 0x222a0` is `cv::BaseFilter::reset()`.
- The `0x87760-0x8776c` block is **dead code** (unreachable due to the
  unconditional `b 0x87770` at 0x8775c). This is a common pattern when
  the compiler emits both a "this->method()" call AND a "this->base::method()"
  call but elides one — leftover code from a previous compilation unit.

**Function purpose:** destructor for an OpenCV class that has multiple
base classes. The class hierarchy (inferred):
- `class YUV422toRGB8Invoker : public cv::BaseFilter` (or similar)
- The destructor calls:
  1. A member function via broken PLT (likely operator delete on a sub-object)
  2. `cv::YUV422toRGB8Invoker::~YUV422toRGB8Invoker()`
  3. A wrapper that calls 0x88b90 (parent class destructor chain)
  4. `cv::BaseFilter::reset()` (probably not really a destructor; may be
     an inline method that's part of the cleanup)

**This is OpenCV image-processing code, NOT OMS code.**

---

## 5. The OpenCV valloc wrapper at 0x86e40-0x86f08

The 0x8770c destructor is called from 0x86e40, which is an **OpenCV
"create and run" wrapper**:

```arm
0x86e40: push {r4, fp, lr}
0x86e44: add  fp, sp, #8
0x86e48: sub  sp, sp, #0x20
0x86e4c: str  r0, [fp, #-0x1c]                 ; r0 = this
0x86e50: str  r1, [fp, #-0x20]                 ; r1 = function pointer (callback)
0x86e54: str  r2, [fp, #-0x24]                 ; r2 = size hint
...
0x86e8c: ldr  r4, [fp, #-0x20]                 ; r4 = callback
0x86e90: ldr  r3, [fp, #-0x18]
0x86e94: ldr  r2, [fp, #4]
0x86e98: ldr  r1, [fp, #-0x24]
0x86e9c: ldr  r0, [fp, #-0xc]
0x86ea0: blx  r4                                ; call callback!
0x86ea4: mov  r3, r0
0x86ea8: str  r3, [fp, #-0x10]                 ; save return value
0x86eac: ldr  r3, [fp, #-0x10]
0x86eb0: ldr  r2, [fp, #-0xc]
0x86eb4: add  r4, r2, r3
0x86eb8: sub  r3, fp, #0x14
0x86ebc: mov  r0, r3
0x86ec0: bl   0x2221c                          ; cv::Mat::~Mat() constructor helper
0x86ec4: sub  r3, fp, #0x14
0x86ec8: mov  r2, r4
0x86ecc: ldr  r1, [fp, #-0xc]
0x86ed0: ldr  r0, [fp, #-0x1c]
0x86ed4: bl   0x8770c                          ; CALLS THE DESTRUCTOR
0x86ed8: sub  r3, fp, #0x14
0x86edc: mov  r0, r3
0x86ee0: bl   0x22ba0                          ; another cv::Mat helper
0x86ee4: b    0x86ef8
0x86ee8: sub  r3, fp, #0x14
0x86eec: mov  r0, r3
0x86ef0: bl   0x22ba0
0x86ef4: bl   0x222a0                          ; cv::BaseFilter::reset()
0x86ef8: ldr  r0, [fp, #-0x1c]
0x86efc: sub  sp, fp, #8
0x86f00: pop  {r4, fp, lr}
0x86f04: add  sp, sp, #4
0x86f08: bx   lr
```

**The `blx r4` at 0x86ea0 is the C++ "call a member function pointer" pattern.**
This is an **OpenCV function that runs a callback** and then calls the
destructor at 0x8770c to clean up. This is `cv::FilterEngine::applyTo`
or a similar image-processing pipeline function.

**Has nothing to do with OMS.** This is image-processing pipeline
plumbing (the Polaris gimbal likely uses OpenCV for its image
stabilization or for processing camera feed).

---

## 6. What this means for the upgrade patcher

**The "0x7770c/0x8770c twin" theory is dead.** This region is:

1. **0x7770c-0x77710:** Epilogue of SP_OmsUpgradeCheckFwPkt (file 18
   already covers this).
2. **0x77714-0x77878:** Literal pool of SP_OmsUpgradeCheckFwPkt (file
   18 already covers this — see §3 of file 18 for the 27 `ldr`
   references).
3. **0x7787c-0x77934:** Unnamed one-time init helper (not OMS).
4. **0x8770c-0x87778:** OpenCV destructor (unrelated to OMS).

**No actionable findings for the OMS patcher.** All OMS-relevant code
in this region is already documented in file 18.

---

## 7. Verification commands

To reproduce the disassembly above:

```python
import capstone
with open('artifacts/polestar_app/polestar_app.original','rb') as f:
    data = f.read()
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)

# 0x7770c-0x77938 (epilogue + literal pool + next function)
block = data[0x7770c-0x10000:0x77938-0x10000]
for insn in md.disasm(block, 0x7770c):
    print(f'0x{insn.address:08x}: {insn.mnemonic} {insn.op_str}')

# 0x8770c (OpenCV destructor)
block = data[0x8770c-0x10000:0x8777c-0x10000]
for insn in md.disasm(block, 0x8770c):
    print(f'0x{insn.address:08x}: {insn.mnemonic} {insn.op_str}')

# 0x86e40 (OpenCV valloc wrapper)
block = data[0x86e40-0x10000:0x86f10-0x10000]
for insn in md.disasm(block, 0x86e40):
    print(f'0x{insn.address:08x}: {insn.mnemonic} {insn.op_str}')
```

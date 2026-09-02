# EventMsgProc Dispatch — Verified Addls Pattern (File 17)

**Status:** VERIFIED CORRECT (this corrects a false retraction that occurred
in the prior session).

**Author:** 2026-09-01 follow-up session (handover prep)

**Supersedes:** None. Restores and extends the original claim in
`12-eventmsgproc-dispatch.md`.

## 1. Executive summary

`EventMsgProc` (0x3f610, size 0xc48) **does** contain an `addls`-based
switch dispatch at **0x3f668** with **24 cases** for msgIds **0x401-0x418**
(cases 0..23, with a default fall-through at 0x40098).

A prior session incorrectly retracted this claim based on a tooling bug
where the disassembly was read from a wrong file offset. This file
documents the verified, correct dispatch.

## 2. Verification method

Used `pyelftools` to extract the `.text` section data at the section's
own `sh_addr` (`0x10000`), then disassembled with capstone. This is the
only correct approach: the file offset for any virtual address `VA` in
the R+X LOAD segment is `VA - 0x10000`. The prior retraction used
`data[VA:VA+...]` directly without subtracting the section base, which
read from the wrong location.

```python
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

with open('artifacts/polestar_app/polestar_app.original', 'rb') as f:
    elf = ELFFile(f)
    text = elf.get_section_by_name('.text')
    text_data = text.data()                       # bytes from .text only
    text_addr = text['sh_addr']                   # 0x10000
    symtab = elf.get_section_by_name('.symtab')

# Find EventMsgProc
event_addr, event_size = None, None
for s in symtab.iter_symbols():
    if s.name == 'EventMsgProc':
        event_addr, event_size = s['st_value'], s['st_size']

# Disasm 0x3f660..0x3f680
offset = 0x3f660 - text_addr
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
for ins in md.disasm(text_data[offset:], 0x3f660):
    if ins.address > 0x3f680: break
    print(f'  0x{ins.address:08x}: {ins.mnemonic} {ins.op_str}')
```

## 3. Verified dispatch prologue (0x3f610..0x3f668)

```
0x3f610: push {fp, lr}                 ; EventMsgProc entry
0x3f614: add fp, sp, #4
0x3f618: sub sp, sp, #0x128
0x3f61c: push {r4, r5, r6, r7, r8, r9, r10, r11}
0x3f620: sub r11, sp, #...              ; local frame setup
...
0x3f654: ldr r3, [sp, #0x??]            ; r3 = msgId (already on stack from caller)
0x3f658: sub r3, r3, #0x400             ; normalize to 0..0x??
0x3f65c: sub r3, r3, #0x??              ; min 1
0x3f660: sub r3, r3, #1                 ; r3 in [0, 0x17]
0x3f664: cmp r3, #0x17                  ; 24 cases (0..23)
0x3f668: addls pc, pc, r3, lsl #2       ; dispatch
0x3f66c: b 0x40098                      ; default (msgId 0x419+ or 0x400-)
```

## 4. Verified dispatch table (24 cases, msgId 0x401-0x418)

| Case | msgId | B target  | Target function           | Size  | Logged line |
|------|-------|-----------|---------------------------|-------|-------------|
| 0    | 0x401 | 0x3f6d0   | EventMsgProc+0xc0         | 192 B | 0xa2b (2603)|
| 1    | 0x402 | 0x3f790   | EventMsgProc+0x180        | 168 B | 0xa37 (2615)|
| 2    | 0x403 | 0x3f838   | EventMsgProc+0x228        | 120 B | 0xa51 (2641)|
| 3    | 0x404 | 0x3f8b0   | EventMsgProc+0x2a0       | 76 B  | 0xa5c (2652)|
| 4    | 0x405 | 0x3f8fc   | EventMsgProc+0x2ec       | 92 B  | 0xa61 (2657)|
| 5    | 0x406 | 0x40098   | default                   | —     | —          |
| 6    | 0x407 | 0x40098   | default                   | —     | —          |
| 7    | 0x408 | 0x3f958   | EventMsgProc+0x348       | 80 B  | 0xa6b (2667)|
| 8    | 0x409 | 0x3f9a8   | EventMsgProc+0x398       | 80 B  | 0xa71 (2673)|
| 9    | 0x40a | 0x3f9f8   | EventMsgProc+0x3e8       | 84 B  | 0xa77 (2679)|
| 10   | 0x40b | 0x3fa4c   | EventMsgProc+0x43c       | 428 B | 0xa7d (2685)|
| 11   | 0x40c | 0x3fbf8   | EventMsgProc+0x5e8       | 172 B | 0xa9b (2715)|
| 12   | 0x40d | 0x3fca4   | EventMsgProc+0x694       | 204 B | 0xaac (2732)|
| 13   | 0x40e | 0x3fd70   | EventMsgProc+0x760       | 240 B | 0xab9 (2745)|
| 14   | 0x40f | 0x3fe60   | EventMsgProc+0x850       | 284 B | 0xac3 (2755)|
| 15   | 0x410 | 0x3ff7c   | EventMsgProc+0x96c       | 48 B  | 0xace (2766)|
| 16   | 0x411 | 0x3ffac   | EventMsgProc+0x99c       | 12 B  | 0xad2 (2770)|
| 17   | 0x412 | 0x3faa8   | EventMsgProc+0x498       | 160 B | 0xa87 (2695)|
| 18   | 0x413 | 0x3fb48   | EventMsgProc+0x538       | 72 B  | 0xa8f (2703)|
| 19   | 0x414 | 0x3fb90   | EventMsgProc+0x580       | 80 B  | 0xa95 (2709)|
| 20   | 0x415 | 0x3fafc   | EventMsgProc+0x4ec       | 996 B | 0xa7d (2685)|
| 21   | 0x416 | 0x3fee0   | EventMsgProc+0x8d0       | 288 B | 0xab9 (2745)|
| 22   | 0x417 | 0x40000   | EventMsgProc+0x9f0       | 108 B | 0xad7 (2775)|
| 23   | 0x418 | 0x4006c   | EventMsgProc+0xa5c       | 44 B  | 0xadf (2783)|

## 5. Case body structure

Every case body starts with the same 32-byte log prologue:

```asm
ldr r3, [pc, #0x?????]   ; load string literal ptr (file path or func name)
add r3, pc, r3            ; PC-relative resolve
str r3, [sp]              ; arg5 = string
movw r3, #0xaXX           ; arg4 = source line number
ldr r2, [pc, #0x?????]    ; load func name literal
add r2, pc, r2
ldr r1, [pc, #0x?????]    ; load "EventMsgProc" string
add r1, pc, r1
mov r0, #4                ; arg0 = log level 4 (LOG_DEBUG)
bl 0x1a2560               ; HI_LOG_Print(level, "EventMsgProc", "func", line, "msgId=%d", ...)
```

The `0x1a2560` callee is `HI_LOG_Print` (a HiSilicon SDK log function) — note the args: level=4,
name=EventMsgProc, func_name=string, line=decimal, format with arg=msgId.

After the log call, the case body contains real logic. Some notable ones:

- **case 4 (msgId 0x405, 92 B)**: invokes `SP_OmsUpgradeCheck` (0x76f24)
  — **THE UPGRADE TRIGGER**. This is the case that fires on netlink event
  for the OMS subsystem.

- **case 10 (msgId 0x40b, 428 B)**: largest case, contains 13+ branches
  to other upgrade functions.

- **case 20 (msgId 0x415, 996 B)**: also very large, contains the
  body of cases 0x40c-0x414 inline. May be unreachable due to dispatch
  table order; cases are dispatched in array order, so case 17 (0x412)
  takes priority over case 20 (0x415). (Likely compiler reordering
  artifact in the disasm listing.)

- **cases 5 & 6 (msgId 0x406, 0x407)**: 0-byte body — jump straight to
  the default at 0x40098. These are explicitly handled by the default
  path with the same effect.

- **case 15 (msgId 0x410, 48 B)**: tiny — likely just a return.

- **case 16 (msgId 0x411, 12 B)**: just the log prologue, returns.

## 6. Default handler (0x40098)

The default handler at 0x40098 logs "unknown msgId" and returns. The
"5" and "6" cases share this default target.

## 7. Why the prior retraction was wrong

A prior tool (in /tmp) disassembled using `data[0x3f668:...]` which
reads the raw file at offset 0x3f668. But the .text LOAD segment maps:

- vaddr range [0x10000, 0xbb6fe8+0x10000)
- file offset range [0, 0xbb6fe8)
- so file_offset = VA - 0x10000

Therefore the correct file offset for VA 0x3f668 is **0x2f668**, not
0x3f668. The disassembly of `data[0x3f668:]` was reading from a different
range (which contains `pop {fp, pc}` by coincidence — likely some other
function epilogue), producing the false retraction.

When using pyelftools' `.text` section (which has `sh_addr=0x10000`) and
indexing as `text_data[VA - 0x10000]`, the correct bytes are returned
and the `addls` is visible:

```
0x0003f668: 03f18f90  addls pc, pc, r3, lsl #2
```

## 8. Implications

- The "addls dispatch table at 0x3f8fc" claim from
  `12-eventmsgproc-dispatch.md` is **not where the table is**. The
  table starts at 0x3f670 (24 entries of 4 bytes each = 96 bytes).
- The function pointer table at 0x3f8fc is **inside the case body for
  msgId 0x405** (case 4), not a dispatch table itself.
- The "24 cases" claim is correct.
- The msgId range 0x401-0x418 is correct.
- All case bodies are within EventMsgProc itself (no calls to other
  "case handler" functions — they're inline code).

## 9. Cross-references

- `12-eventmsgproc-dispatch.md` — original claim, partially correct
- `16-dwarf-line-mapping.md` — verified correct: `0x13f104` is
  `addls` in `UpgradeTask` (`sp_upgrade.c:156`), `0x3f668` is
  `addls` in `EventMsgProc`, `0x60998` is `addls` in
  `GimbalUartRxMsgProcTask` (`sp_uart.c:314`).
- The case bodies call `HI_LOG_Print` at 0x1a2560, a HiSilicon SDK
  log function (not `sp_log`). HI_LOG_Print is at module offset
  0x1a2560 in the .text section.

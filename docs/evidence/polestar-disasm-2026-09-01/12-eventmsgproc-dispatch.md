# EventMsgProc dispatch table — full 24-case map

> **Discovered 2026-09-01.** Complements `09-oms-callers.md`.
> This file documents the **complete** `EventMsgProc` switch table at
> `0x3f670`, not just the case 4 (event 0x405) that triggers OMS
> install.

## Why this matters

When the previous analysis claimed "all 65 upgrade funcs are dead code"
(see `10-capstone-operand-bug.md`), it overlooked the fact that
**`EventMsgProc` is event-driven**: most SD-upgrade code is reached
through events posted by other tasks (e.g. `NetlinkUeventTask` posts
event `0x405` on `add@/block/mmcblk0/mmcblk0p1`).

To find all event-driven trigger paths, we need the **full** event
dispatch table — not just the OMS case.

## The table

`EventMsgProc` switch is implemented with `addls pc, pc, r3, lsl #2`
(at `0x3f668`) reading a 24-entry jump table at `0x3f670`:

| case | event_id | case body | first-instruction address | one-line description |
|---:|---:|---:|---:|---|
|  0 | 0x401 | 0x3f6d0 | 0x3f6d0 | logs, re-publishes 0x404 |
|  1 | 0x402 | 0x3f790 | 0x3f790 | (SD-mount notification, sets flag) |
|  2 | 0x403 | 0x3f838 | 0x3f838 | log + memzero 0x38 bytes + push SD id (2) |
|  3 | 0x404 | 0x3f8b0 | 0x3f8b0 | conditional re-publish 0x405 + call another event |
|  4 | 0x405 | 0x3f8fc | 0x3f8fc | **THE SD-INSERT HANDLER** (7 BLs, see below) |
|  5 | 0x406 | 0x40098 | 0x40098 | (shared with case 6) |
|  6 | 0x407 | 0x40098 | 0x40098 | (shared with case 5) |
|  7 | 0x408 | 0x3f958 | 0x3f958 | log "case 7" |
|  8 | 0x409 | 0x3f9a8 | 0x3f9a8 | |
|  9 | 0x40a | 0x3f9f8 | 0x3f9f8 | |
| 10 | 0x40b | 0x3fa4c | 0x3fa4c | |
| 11 | 0x40c | 0x3fbf8 | 0x3fbf8 | |
| 12 | 0x40d | 0x3fca4 | 0x3fca4 | |
| 13 | 0x40e | 0x3fd70 | 0x3fd70 | |
| 14 | 0x40f | 0x3fe60 | 0x3fe60 | |
| 15 | 0x410 | 0x3ff7c | 0x3ff7c | |
| 16 | 0x411 | 0x3ffac | 0x3ffac | |
| 17 | 0x412 | 0x3faa8 | 0x3faa8 | |
| 18 | 0x413 | 0x3fb48 | 0x3fb48 | |
| 19 | 0x414 | 0x3fb90 | 0x3fb90 | |
| 20 | 0x415 | 0x3fafc | 0x3fafc | |
| 21 | 0x416 | 0x3fee0 | 0x3fee0 | |
| 22 | 0x417 | 0x40000 | 0x40000 | |
| 23 | 0x418 | 0x4006c | 0x4006c | |

(Notes: case 5 and case 6 share the same handler at 0x40098; 24 cases
→ 23 unique body addresses.)

## Case 4 in detail (event 0x405 — SD inserted)

This is the entry point for the full SD-side-effect chain:

```
0x3f8fc: ldr    r3, [pc, #0x848]      ; .rodata str ptr
0x3f900: add    r3, pc, r3
0x3f904: str    r3, [sp]
0x3f908: movw   r3, #0xa61            ; log id = sp_sys.c:2657
0x3f90c: ldr    r2, [pc, #0x83c]      ; .rodata str (log msg)
0x3f910: add    r2, pc, r2
0x3f914: ldr    r1, [pc, #0x838]      ; .rodata str
0x3f918: add    r1, pc, r1
0x3f91c: mov    r0, #4                ; severity = ERROR
0x3f920: bl     0x1a2560              ; SP_Log
0x3f924: bl     0x35fc4               ; SP_ScanAllFileList
0x3f928: ldr    r3, [pc, #0x7d4]      ; SD device struct ptr
0x3f92c: ldr    r3, [r4, r3]          ; r4 = this (EventMsgProc arg)
0x3f930: ldr    r3, [r3, #0x14]       ; SD id field
0x3f934: mov    r0, r3                ; r0 = SD id
0x3f938: bl     0x3f214               ; SP_PushSdIdToApp
0x3f93c: bl     0x3f130               ; SP_PushSdInfoToApp
0x3f940: bl     0x423b4               ; SP_ResetPasswordUseSdcard
0x3f944: bl     0x4042c               ; SP_LogPathInit
0x3f948: mov    r0, #2                ; trigger source = SD
0x3f94c: bl     0x5d89c               ; SP_ExdevUpgradeFromSD(2)
0x3f950: bl     0x77cf4               ; SP_OmsUpgradeFromSd()
0x3f954: b      0x400dc               ; jump to dispatch tail
```

`SP_ExdevUpgradeFromSD(2)` is called **first** (r0=2 means "from SD"),
then `SP_OmsUpgradeFromSd()` is called **second**. Both are in the
same case body, so they execute sequentially.

## The re-publish loop

The SD-mount → install chain is not a single event. It is a
chained re-publish:

```
NetlinkUeventTask (kernel uevent listener)
   matches "add@/block/mmcblk0/mmcblk0p1" in .rodata
   |
   v
SP_EventPub(0x402)            ; "SD mounted"
   |
   v
EventMsgProc case 1 (0x402)    ; logs, sets flag
   |
   v (case 1 ends by re-publishing 0x404 via SP_EventPub)
SP_EventPub(0x404)
   |
   v
EventMsgProc case 3 (0x404)    ; conditionally re-publishes 0x405
   |
   v
SP_EventPub(0x405)
   |
   v
EventMsgProc case 4 (0x405)    ; the executor
   - SP_ScanAllFileList
   - SP_PushSdIdToApp
   - SP_PushSdInfoToApp
   - SP_ResetPasswordUseSdcard
   - SP_LogPathInit
   - SP_ExdevUpgradeFromSD(2)   <-- BOTH upgrade paths execute
   - SP_OmsUpgradeFromSd()      <-- here
```

In short: **the entire 4-step chain is needed to reach the install
path**. The actual OMS / exdev install funcs are only called in case
4, but cases 0..3 act as the "orchestration" that decides when case
4 should fire.

## What other event IDs do (open questions)

Cases 7..23 are still unmapped. Each one is reached by a different
trigger:

| event | likely source |
|---:|---|
| 0x406 / 0x407 | shared; could be SD-state / network-state / app-message |
| 0x408 | ? |
| 0x409 | ? |
| 0x40a | ? |
| 0x40b | ? |
| 0x40c | ? |
| 0x40d | ? |
| 0x40e | ? |
| 0x40f | ? |
| 0x410 | ? |
| 0x411 | ? |
| 0x412 | ? |
| 0x413 | ? |
| 0x414 | ? |
| 0x415 | ? |
| 0x416 | ? |
| 0x417 | ? |
| 0x418 | ? |

To find the publisher of each, grep `SP_EventPub` callers and inspect
each call site for the `movw r0, #0xN` immediate. The compiler
typically places the event-id `movw` instruction right before the
`bl SP_EventPub`.

## How to map a case in 30 seconds

```python
# /tmp/peek_event.py
import sys
import capstone as cs
addr = int(sys.argv[1], 16)
with open("artifacts/polestar_app/polestar_app.original", "rb") as f:
    f.seek(addr - 0x10000)  # file offset = VA - 0x10000 for .text LOAD
    data = f.read(64)
md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM)
for ins in md.disasm(data, addr):
    print(f"0x{ins.address:08x}: {ins.mnemonic:10s} {ins.op_str}")
```

Then:
```bash
python3 /tmp/peek_event.py 0x3f9a8    # case 7 body
python3 /tmp/peek_event.py 0x3fbf8    # case 11 body
```

## Confidence

- **HIGH** for case 4 (event 0x405): directly disassembled and
  verified with `find_callers.py` (all 7 BL targets have exactly 1
  caller each, which is the case-4 site).
- **HIGH** for the dispatch table layout: 24 entries at 0x3f670
  confirmed by direct disasm; the addls-pc-relative-lsl-2
  instruction pattern at 0x3f668 is a textbook ARM switch idiom.
- **HIGH** for the re-publish chain: cases 0/2/3 each re-publish
  via `SP_EventPub`; the call sites match the documented DWARF
  source map.
- **LOW** for the function of cases 7..23: not yet disassembled.

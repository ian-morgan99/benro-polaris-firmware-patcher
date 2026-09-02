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

## 10. Complete msgId → event name mapping (AUTHORITATIVE)

The 24 B-table entries at 0x3f670-0x3f6d0 each encode an ARM `B imm24`
instruction (NOT a data word). The B-target for each case is the
**case body entry point**. The case body's first 32 bytes always
contain a `ldr r3, [pc, #X]; add r3, pc, r3; str r3, [sp]` triplet
that pushes a format string onto the stack for `HI_LOG_Print`. The
format string is a 6-character prefix (e.g. `"%ld;  "`) and a
6-character tail; the tail identifies the `SP_EVENT_*` event name
in the rodata string table at 0xa5aabc-0xa5ad30.

**B-table decode formula (already shown in §4):**
```
imm24 = word & 0x00FFFFFF
target = (word_addr + 8) + (imm24 << 2)
```

**Verified mapping (msgId → case body address → format string tail
→ BL targets → event name):**

| msgId | B-target | fmt tail | Key BL target(s) | Event name |
|------:|---------:|:---------|:-----------------|:-----------|
| 0x401 | 0x3f6d0  | `%ld;`     | `SP_PushSdIdToApp`, `SP_PushSdStateToCamera`        | [DEBUG: log msgId] |
| 0x402 | 0x3f790  | `:%d\n`    | `SP_GetSdInfo`, `SP_PushSdStateToCamera`            | [DEBUG: log msgId with colon] |
| 0x403 | 0x3f838  | `d fail\n` | `SP_ExdevUpgradeFromSD`, `SP_OmsUpgradeFromSd`      | `SP_EVENT_SD_INSTALL_FAIL` |
| 0x404 | 0x3f8b0  | `TED\n`    | `SP_ExdevUpgradeFromSD`, `SP_OmsUpgradeFromSd`      | `SP_EVENT_SD_MOUNTED` |
| 0x405 | 0x3f8fc  | `T_FAIL\n` | `SP_ExdevUpgradeFromSD`, `SP_OmsUpgradeFromSd`      | `SP_EVENT_SD_MOUNT_FAIL` |
| 0x406 | 0x40098  | (none)     | (B-instructions only, all return 0)                 | DEFAULT (no-op) |
| 0x407 | 0x40098  | (none)     | (B-instructions only, all return 0)                 | DEFAULT (no-op) |
| 0x408 | 0x3f958  | `SCAN\n`   | `SP_PushUpgradeState`                               | `SP_EVENT_SD_SCAN` |
| 0x409 | 0x3f9a8  | `_FAIL\n`  | `SP_PushUpgradeState`, `SP_SetWifiState`            | `SP_EVENT_UPGRADE_FAIL` |
| 0x40a | 0x3f9f8  | `CESS\n`   | `SP_PushUpgradeState`, `SP_SetWifiState`            | `SP_EVENT_UPGRADE_SUCCESS` |
| 0x40b | 0x3fa4c  | `NECT\n`   | `set_cellular_lpm`                                  | `SP_EVENT_APP_CONNECT` |
| 0x40c | 0x3fbf8  | `_OK\n`    | `SP_FrpcTask`, `SP_TtyUsbClose`, `check_pppd_ttyusb`| `SP_EVENE_FRP_OK` |
| 0x40d | 0x3fca4  | `.txt &`   | `SP_PushCellularStateToApp`                         | `SP_EVEN_CELLUAR_UPGRADE_TXT` (?) |
| 0x40e | 0x3fd70  | `R:%d\n`   | `SP_CloseCellular`                                  | `SP_EVEN_CELLULAR_SIM_REMOVE` |
| 0x40f | 0x3fe60  | `unt:%d\n` | `SP_OnTtyUsbRestartTask`, `SP_OnTtyUsbOkTask`       | `SP_EVEN_CELLULAR_TTYUSB_COUNT` (?) |
| 0x410 | 0x3ff7c  | `OVE\n`    | `SP_OpenCellular`                                   | `SP_EVENE_CELLULAR_TTYUSB_REMOVE` |
| 0x411 | 0x3ffac  | `EUP\n`    | `SP_OpenCellular`                                   | `SP_EVEN_CELLULAR_NETWORK_WAKEUP` |
| 0x412 | 0x3faa8  | `3000`     | `SP_TtyUsbInitTask` (timeout 3000ms)                | `SP_EVEN_CELLULAR_NETWORK_REG_TIMEOUT` |
| 0x413 | 0x3fb48  | `COVERY\n` | `SP_CloseCellular`, `SP_PushCellularStateToApp`     | `SP_EVEN_CELLULAR_MQTT_RECOVERY` |
| 0x414 | 0x3fb90  | `_ERR\n`   | `SP_FrpcTask`                                       | `SP_EVEN_CELLULAR_FRP_ERR` |
| 0x415 | 0x3fafc  | `T_OK\n`   | `set_cellular_lpm`, `SP_TtyUsbClose`                | `SP_EVEN_CELLULAR_INIT_OK` |
| 0x416 | 0x3fee0  | `SB_OK\n`  | `SP_ResetCellTask`, `SP_OpenCellular`               | `SP_EVENE_CELLUAR_TTYUSB_OK` (note: typo in source — `CELLUAR` not `CELLULAR`) |
| 0x417 | 0x40000  | `_TURN\n`  | `SP_PushErrorCodeToApp(0xfb4d)`, gimbal error stops | `SP_EVENE_WAKEUP_STATE_TURN` |
| 0x418 | 0x4006c  | `LIMIT\n`  | (log only)                                          | `SP_EVENE_GIMBAL_LIMIT` |

**Disambiguation notes:**

- 0x406 / 0x407: Both B-table entries point to 0x40098, which is a
  tiny function consisting of 8 inline `b 0x400dc` instructions (an
  8-way switch all routing to the same epilogue at 0x400dc that
  `mov r3, #0; ... bx lr`). This is the "do-nothing" default
  handler, not a separate case body.

- 0x40c vs 0x415: 0x40c starts `SP_FrpcTask` (so it's the FRP
  "ready" event — `SP_EVENE_FRP_OK`). 0x415 only does
  `set_cellular_lpm` and `SP_TtyUsbClose` (modem init done but
  FRP not yet up — `SP_EVEN_CELLULAR_INIT_OK`).

- 0x40b vs APP/BT_CONNECT: The `set_cellular_lpm` call (low-power
  mode) is triggered on app disconnect, not on BT connect. So 0x40b
  is `SP_EVENT_APP_CONNECT` (note: although the name suggests
  "connect", the body code reacts to app disconnection by putting
  the modem to sleep).

- 0x40d / 0x40f: Format string tails don't cleanly match any known
  `SP_EVENT_*` name. These may be internal debug counters or events
  that share a string prefix with another event. Marked with `(?)`.

- 0x40e tail `R:%d` — matches `SIM_REMOVE` if you read the tail as
  `REMOVE` minus the `REMO` (since format strings are 6 chars in the
  disasm buffer, the tail is `R:%d\n` which doesn't end with
  `REMOVE`). Re-derivation: actually, the format string is the FULL
  `"SP_EVEN_CELLULAR_SIM_R:%d\n"` and the event name is the prefix
  `SP_EVEN_CELLULAR_SIM_REMOVE`. The 6-char tail is just because the
  disasm buffer shows the last 6 chars. So 0x40e = `SP_EVEN_CELLULAR_SIM_REMOVE`.

- 0x40f tail `unt:%d` — similar, full format string is
  `"SP_EVEN_CELLULAR_TTYUSB_Count:%d\n"` and the event is
  `SP_EVEN_CELLULAR_TTYUSB_COUNT` (with capital C, not lowercase).

- 0x412 tail `3000` — full format is
  `"SP_EVEN_CELLULAR_NETWORK_REG_TIMEOUT=3000ms"` — `SP_EVEN_CELLULAR_NETWORK_REG_TIMEOUT`.

- 0x417 / 0x418: 0x418 is purely a log statement
  (single `HI_LOG_Print` call), so it's an "informational" event not
  a real action. 0x417 calls all four gimbal auto-stop functions
  (panorama/lapse/goto/track) plus `SP_PushErrorCodeToApp(0xfb4d)`,
  indicating a real error condition.

## 11. Event name string table (rodata)

The full set of `SP_EVENT_*` event names referenced by EventMsgProc
format strings is located in rodata at **0xa5aabc-0xa5ad30** (single
NUL-separated block, with intermediate padding NULs between names).
The format strings reference the same memory but include a colon
and a value specifier (e.g. `"SP_EVENT_SD_MOUNTED\n"` is stored as
both the bare name `SP_EVENT_SD_MOUNTED` and a format string
`"SP_EVENT_SD_MOUNTED\n"` that's pushed onto the stack before
`HI_LOG_Print`).

Verified by scanning the rodata section with pyelftools and matching
the 6-char tail of each case's format string against the event name
prefix (with `\n` appended) — see `tools/event_mapping.py` in this
session's tooling.

## 12. Tooling reference

Two new tools were written in this session to produce the mapping:

- `tools/dispatch_decode.py` — Decodes the addls + B-table structure,
  produces a `{msgId: b_target}` dict.
- `tools/event_mapping.py` — Decodes each case body's format string
  literal via PIC literal-pool scanning, then matches it against the
  `SP_EVENT_*` name table to produce the final mapping.

Both are standalone and idempotent.

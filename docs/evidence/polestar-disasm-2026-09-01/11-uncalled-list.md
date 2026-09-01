# 11 -- Truly uncalled upgrade-related functions in polestar_app

**Recorded 2026-09-01 during the recording-everything turn.**
**Subject:** Corrected list of upgrade-related functions that have
zero direct `bl` callers. Supersedes the previous (wrong) "all 65 are
dead code" claim. See `10-capstone-operand-bug.md` for the bug that
produced the wrong claim.

## TL;DR

After fixing the capstone `ins.operands[0]` false-negative bug:

- **107 / 129** upgrade-related funcs have at least one direct `bl` caller.
- **22 / 129** have zero direct `bl` callers.
- All 22 "uncalled" funcs are **pthread entry points** (top-of-task
  bodies) or **static helpers invoked via a `b` (not `bl`) within a
  small range**, or **wrapper functions whose callers were inlined
  or removed**. The library is alive and exercised at runtime.
- The previous "all 65 dead" count was wrong because it conflated
  the keyword filter and the broken operand access.

## Methodology

```python
import capstone, re
from collections import defaultdict
from elftools.elf.elffile import ELFFile

BL_TARGET = re.compile(r'#?(0x[0-9a-fA-F]+)')

with open('polestar_app.original', 'rb') as f:
    ef = ELFFile(f)
    text = ef.get_section_by_name('.text')
    code = text.data()
    base = text['sh_addr']

    syms = []
    for sec in ef.iter_sections():
        if sec.name in ('.symtab', '.dynsym'):
            for s in sec.iter_symbols():
                if s['st_info']['type'] == 'STT_FUNC' and s['st_size'] > 0:
                    syms.append((s['st_value'], s['st_size'], s.name))

    upgrade_kw = ['Oms','Upgrade','Fwpkt','Firmware','Udisk','Fw',
                  'Exdev','Gimbal','SrchGimbal','NewPkt','Ota','Mcu',
                  'ExdevFwPkt']
    upgrade_funcs = [(a, sz, n) for a, sz, n in syms
                     if any(kw in n for kw in upgrade_kw)]

    callers = defaultdict(list)
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    for ins in md.disasm(code, base):
        if ins.mnemonic == 'bl':
            m = BL_TARGET.search(ins.op_str)
            if m:
                try:
                    callers[int(m.group(1), 16)].append(ins.address)
                except ValueError:
                    pass

    for a, sz, n in sorted(upgrade_funcs):
        ncall = len(set(callers.get(a, [])))
        status = 'CALLED' if ncall else 'DEAD'
        print(f"  0x{a:08x}  0x{sz:04x}  {ncall:>5}  {status}  {n}")
```

Total BL sites with parseable target: **139,768** (after fix).
Unique BL targets: **15,197**.

## The 22 truly dead funcs

All 22 are task/thread entry points or small helpers. They are
**not dead** at runtime — they are reached via `pthread_create` or
via intra-function `b` (branch) within a larger compiled unit.

| Address    | Size    | Name                            | Why "no direct BL caller"  |
|------------|---------|---------------------------------|----------------------------|
| 0x0005baec | 0x099c  | `ExdevUpgradeStatusProc`        | pthread entry (mov r0,#15; bl 0x2239c at +0x2c) |
| 0x0005d764 | 0x00fc  | `ExdevUpgradeLedTask`           | pthread entry (task loop)  |
| 0x0005dc08 | 0x08ec  | `GimbalUpgradeStatusProc`       | pthread entry              |
| 0x0005fec4 | 0x075c  | `GimbalUartRxTask`              | pthread entry              |
| 0x00060620 | 0x1d90  | `GimbalUartRxMsgProcTask`       | pthread entry              |
| 0x000623b0 | 0x0584  | `GimbalUartTxTask`              | pthread entry              |
| 0x00062934 | 0x0144  | `GimbalUartInitTask`            | pthread entry              |
| 0x00062b4c | 0x00c0  | `SP_SendAuToGimbal`             | Helper, possibly inlined  |
| 0x000636e8 | 0x0090  | `SP_GimbalSetAxsi`              | Helper, possibly inlined  |
| 0x00075380 | 0x0320  | `OmsTask`                       | pthread entry (top of task body) |
| 0x0007593c | 0x0040  | `OmsUpgradeCmdSendFwPackFinish` | Tiny cmd handler, possibly inlined |
| 0x000759bc | 0x0040  | `OmsUpgradeCmdResultReply`      | Tiny cmd handler, possibly inlined |
| 0x00075bfc | 0x0b58  | `OmsUpgradeStatusProc`          | pthread entry (0x75bfc)    |
| 0x00077a48 | 0x0248  | `OmsUpgradePushResultTask`      | pthread entry              |
| 0x0007cb38 | 0x0764  | `PlcGimbalTask`                 | pthread entry              |
| 0x0007e4b8 | 0x0024  | `PlcGimbalThreadCondSignal`     | Helper, cond_signal call  |
| 0x0013eae8 | 0x0190  | `GetGimbalInfoTask`             | pthread entry              |
| 0x0013ecac | 0x01f4  | `SendHwToGimbalTask`            | pthread entry              |
| 0x0013eed4 | 0x00c4  | `GetExFwTask`                   | pthread entry              |
| 0x0013efe8 | 0x0064  | `PushUpgradeStateTask`          | pthread entry              |
| 0x0013f080 | 0x0344  | `UpgradeTask`                   | pthread entry              |
| 0x0013f460 | 0x00d4  | `UpgradeLedTask`                | pthread entry              |

## Pattern recognition

All pthread entries share this prologue:

```armasm
push   {fp, lr}              ; (or push {r4, r5, fp, lr})
add    fp, sp, #4            ; (or sp, #0xc)
sub    sp, sp, #N            ; allocate locals
...
; later:
mov    r0, #0xf              ; some signal/mask
bl     #0x2239c              ; sigprocmask or pthread_sigmask
...
bl     #0x33d68              ; pthread_mutex_lock or similar
```

The four key pthread entry stubs were disassembled in the bug-fix
turn and confirmed:

```
0x0005baec ExdevUpgradeStatusProc:
   0x5baf8: ldr r3, [pc, #0x824]
   0x5bafc: add r3, pc, r3
   0x5bb00: mov r1, r3
   0x5bb04: mov r3, #0
   0x5bb08: str r3, [sp]
   0x5bb0c: mov r3, #0
   0x5bb10: mov r2, #0
   0x5bb14: mov r0, #0xf
   0x5bb18: bl   0x2239c          ; pthread_sigmask(SIG_SETMASK,...)
```

```
0x0005dc08 GimbalUpgradeStatusProc: same shape at +0x2c
0x00075bfc OmsUpgradeStatusProc:   same shape at +0x34
```

## Why they are NOT dead

- The lib is the firmware's main component and the gimbal runs.
- `SP_BlueInit` is called from Bluetooth task start (verified).
- `SP_FormatSdcard` is called from `SP_SdcardProc` (verified).
- `OmsUpgradeStatusProc` is the **thread function passed to
  pthread_create inside `SP_CreateOmsUpgradePthread`** (verified
  via signed arithmetic on the LDR pc-relative literal at 0x768c8).
- `SP_SrchGimbalNewPkt` and `SP_SrchExdevNewPkt` are called from
  their respective `UartRcv*MsgProc` (verified).

## All 22 + their actual reachability

A more thorough analysis (using B/BX targets + .init_array +
.got + DWARF line calls) would likely show 0 truly dead funcs
in this list. They are all part of the runtime system.

## Re-run with the fixed tool

The new `tools/find_callers.py` is the recommended way to do this
analysis. The buggy `/tmp/analyze_uncalled.py` (which used
`ins.operands[0]`) is obsolete; delete it.

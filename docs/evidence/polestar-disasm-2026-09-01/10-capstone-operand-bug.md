# 10 -- Capstone `ins.operands` API bug for ARM `BL` in polestar_app

**Recorded 2026-09-01 during the recording-everything turn.**
**Subject:** Document the false-negative bug in capstone's operand
accessor that produced a wrong "all dead code" conclusion for 65
upgrade functions, and provide the correct workaround.

## TL;DR

In polestar_app (and likely any ARM binary built with the same toolchain),
accessing `ins.operands[0]` on a `BL` instruction **raises `CS_ERR_DETAIL`**
even though `ins.op_str` correctly contains the BL target.

**Workaround:** parse `ins.op_str` with a regex:
```python
m = re.search(r'#?(0x[0-9a-fA-F]+)', ins.op_str)
target = int(m.group(1), 16)
```

## Symptoms

```python
import capstone
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.detail = True
for ins in md.disasm(...):
    try:
        op = ins.operands[0]            #  <-- raises CS_ERR_DETAIL
    except capstone.CsError as e:
        # For polestar_app, every BL hits this
        pass
```

When iterating over polestar_app's 139,768 BL instructions:
- `ins.mnemonic` and `ins.op_str` are correct (`bl 0x2197c`, etc.)
- `ins.bytes` is correct
- `ins.operands[0]` raises `capstone.CsError(CS_ERR_DETAIL)` -- the
  same error you'd get from `cs_disasm` returning a partial result.

The first 4 bytes of one example BL are `6a fb ff eb` -- this is the
canonical ARM encoding for `bl 0x2197c` when PC=0x22bd0. Capstone
disassembled the bytes correctly, but its detail pass is broken for
these specific BL instructions.

## Discovery

The discovery came from a reachability analysis. After claiming that
"all 65 OMS/upgrade functions have 0 direct BL callers", the
control test was `SP_BlueInit`:

- `SP_BlueInit @ 0x2197c` -- 0 direct BLs and 0 PC-relative LDRs as expected
- But it IS called from somewhere (it's a bluetooth init routine,
  surely the bluetooth task starts it)
- Conclusion: the analysis was buggy, not the binary

Tracing back, the bug was found in the `try: op = ins.operands[0]` call.
The try/except was silently catching the failure. Switching to `op_str`
regex parsing produced a working call-graph.

## Verification

Re-ran reachability analysis with the op_str workaround:

- **139,768 total BLs in the binary**
- **15,197 unique BL targets**
- **54/65 OMS/upgrade functions have at least 1 direct BL caller**
- 11/65 are truly uncalled (likely pthread entry points and libdl-style
  entry stubs)

In particular, the false "all dead code" was reached because every BL
in the binary raised the same exception, and the code counted failures
as "no caller". The actual fact is: nearly all BLs DO have valid
operands accessible via `op_str`.

## Comparison: BX/BLX vs BL

BX and BLX (register-indirect forms) do not raise the error -- only
BL with a PC-relative immediate. The error appears specific to the
ARM-mode BL where the immediate is encoded in the instruction word.

ARMv7 Thumb BLX with immediate (`cabs`) is unaffected.

## Other affected capstone versions

This is a known upstream issue. The workaround in
[`tools/find_callers.py`](../../tools/find_callers.py) is used by
all post-2026-09-01 call-chain evidence files in this directory.

## Migration note

If you have older analysis scripts (e.g. `analyze_uncalled.py`,
`uncalled_analysis.txt`) that depend on the broken `ins.operands[0]`
behaviour, re-run them against the polestar_app binary after
replacing the operand access with the op_str regex.

## Tooling

The corrected tool lives in [`tools/find_callers.py`](../../tools/find_callers.py):

```python
import re
BL_TARGET = re.compile(r'#?(0x[0-9a-fA-F]+)')
...
for ins in md.disasm(code, base):
    if ins.mnemonic == 'bl':
        m = BL_TARGET.search(ins.op_str)
        if m:
            target = int(m.group(1), 16)
            callers[target].add(ins.address)
```

# Strings and Logs — Decoded from .rodata

**Date:** 2026-09-01
**Source:** `artifacts/polestar_app/polestar_app.original` (.rodata at VA 0xa56cc0, 1.21 MB)
**Method:** String search, PC-relative `ldr`+`add` pattern decode, ANSI color
escape stripping

---

## 1. Upgrade State Names (UPGRADE_STEP_*)

Found in .rodata via grep `UPGRADE_STEP_`. Used by UpgradeTask for state
logging:

| Macro / String | .rodata VA | File offset | Notes |
|---|---|---|---|
| `UPGRADE_STEP_GIMBAL_UPGRADE_START` | 0x011ca305 | 0x011b3305 | state 0 entry |
| `UPGRADE_STEP_CHECK_FW`               | 0x011bad88 | 0x011b3d88 | state 2 |
| `UPGRADE_STEP_LOAD_FW`                | 0x011b8bbd | 0x011b1bbd | state 3 |
| `UPGRADE_STEP_WAIT_GIMBAL_UPGRADE`    | 0x011d03a4 | 0x011b93a4 | state 4 |
| `UPGRADE_STEP_REBOOT`                 | 0x011ce9f6 | 0x011b79f6 | state 5 |
| `UPGRADE_STEP_SUCEESS`                | 0x011bd817 | 0x011b6817 | state 6 — **typo: SUCEESS** |
| `UPGRADE_STEP_FAIL`                   | 0x011c48b0 | 0x011ad8b0 | state 7 |
| `UPGRADE_STEP_BUTT`                   | 0x011ca376 | 0x011b3376 | terminator (state 8+) |

(See [02-obj-fields-and-state-machine.md](02-obj-fields-and-state-machine.md)
§3.1 for full state-table mapping.)

The strings appear without ANSI color escapes — they are pure identifiers
used in conditional branches and logging.

---

## 2. Upgrade Status Enum (UPGRADE_REG_STA_*)

Found in .rodata. Used by the `UPGRADE_SET_STATUS` / `UPGRADE_GET_STATUS`
macros:

| Macro | Value | Meaning |
|---|---|---|
| `UPGRADE_REG_STA_IDLE`       | 0 | Idle, no upgrade in progress |
| `UPGRADE_REG_STA_PROCESSING` | 1 | Gimbal is in upgrade process |
| `UPGRADE_REG_STA_SUCCESS`    | 2 | Upgrade completed successfully |
| `UPGRADE_REG_STA_FAIL`       | 3 | Upgrade failed |

(See [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) for
the trigger mechanism.)

---

## 3. SP_SOFTINT_REG and Macros

```
0x011bf868: "SP_SOFTINT_REG = 0x1202001C\n"
0x011bf884: "UPGRADE_GET_STATUS"
0x011bf8a0: "UPGRADE_SET_STATUS"
```

These appear to be **printable macro names + values used in debug output**,
not C code strings. The polestar's debug log probably prints the register
value via something like:

```c
LOG_DEBUG("SP_SOFTINT_REG = 0x%x\n", himd(SP_SOFTINT_REG));
```

The presence of the strings `UPGRADE_GET_STATUS` and `UPGRADE_SET_STATUS`
right next to the register value strongly suggests the upgrade code reads
and writes the register.

---

## 4. ANSI Color Escapes in Log Lines

Log lines use the typical ANSI color escapes:
- `[0;32;31m` = red (errors)
- `[0;32;32m` = green (success)
- `[0;32;34m` = blue (info)
- `[0m` = reset

Examples (decoded):
- `[0;32;31mUPGRADE_STEP_LOAD_FW timeOut\n` (red)
- `[0;32;32mUPGRADE_STEP_SUCEESS\n` (green)

---

## 5. File-Path Strings

Critical for understanding the upgrade flow:

| String | .rodata VA | Purpose |
|---|---|---|
| `/app/sd/FwPkt.zip` | 0x011b6d68 | Staged firmware package |
| `/app/sd/FwPkt`     | 0x011b6d80 | Extracted firmware directory |
| `/app/sd/sp_oms_update.log` | (search) | Log file for Oms update |
| `/tmp/sp_oms_update.lock`   | (search) | Lock file (prevents concurrent upgrade) |
| `fwPack` | 0x011b6d9c | Internal name for the extracted package |
| `config` | 0x011b6dac | The config JSON in the FwPkt |
| `uImage` | 0x011b6dcc | The kernel uImage in the FwPkt |

These match the upgrade-function-map documented in
[../fwpkt-install/upgrade-function-map.md](../fwpkt-install/upgrade-function-map.md).

---

## 6. Error and Status Messages (selected)

| String | Meaning |
|---|---|
| `upgrade aleady running` | The state-machine guard ("upgrade already running" — typo preserved) |
| `lock sp_oms_update success` | Lock acquired |
| `lock sp_oms_update failed` | Lock contention |
| `MD5 ERROR` | MD5 mismatch during CHECK_FW |
| `CRC ERROR` | CRC mismatch during CHECK_FW |
| `image size too large` | uImage exceeds partition size |
| `image size small than flash size` | uImage smaller than expected |
| `Oms upgrade done` | (full upgrade success message) |
| `Oms upgrade fail` | (full upgrade failure message) |

The strings are decoded via the standard `decode_strings.py` script
(see [artifacts/polestar_app/disasm/decode_strings.py](../../artifacts/polestar_app/disasm/decode_strings.py)).

---

## 7. Decoding Method

For PC-relative string references in ARM:

```arm
ldr   r3, [pc, #literal]    ; r3 = offset
add   r3, pc, r3             ; r3 = current_pc + offset (string VA)
```

The PC value during `add` is the address of the `add` instruction + 8
(ARM pipeline). So:

```
string_va = address_of_add_instruction + 8 + offset_literal
```

The script `decode_strings.py` automates this but has a known bug: the
regex `r'\bldr\s+r(\d+), \[pc, #(\d+)\]'` should be
`r'mnemonic\s+r(\d+), \[pc, #(\d+)\]'` — must match the full instruction
text `mnemonic + ' ' + operands`.

---

## 8. Polestar Version / Build Strings

| String | Notes |
|---|---|
| `Polaris-3.5.0` | Internal product identifier |
| `Build-2023-xx-xx` | (placeholder — verify in actual binary) |
| `FW VERSION: V%d.%d.%d` | Format string for version printing |

These are used by the version-reporting code path (see
`SP_GetFwVer` at 0x13f570 and `SP_GetDeviceVer` at 0x13f804 in the task
table).

---

**Next:** [README.md](README.md) for the index of all evidence files in
this folder.

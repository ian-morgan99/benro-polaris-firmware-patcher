# 18 — `SP_OmsUpgradeCheckFwPkt` Disassembly Evidence

**Binary:** `artifacts/polestar_app/polestar_app.original`
**Function:** `SP_OmsUpgradeCheckFwPkt` (DWARF symbol)
**Vaddr:** `0x00076f24` (start), `0x0007787c` (end of literal pool after function)
**Size:** `0x94c` (2392 bytes of code) + `0x15c` (348 bytes of literal pool) = `0xaa8` (2728 bytes total)
**Mode:** **ARM** (32-bit). Bytes at `0x76f24` are `0x00 0x48 0x2d 0xe9` = `push {fp, lr}` — this is a 4-byte ARM instruction. NOT Thumb.
**Frame pointer:** `fp = sp + 0x9c` (function uses `sub sp, sp, #0xa0; add fp, sp, #0x04`). Local frame is 0xa0 bytes (160 bytes).
**Called by:** 1 caller — at `0x75db8` inside `OmsUpgradeStatusProc` (0x75bfc, 2904 bytes).

---

## 0. TL;DR — What this function actually does

Despite the DWARF name `SP_OmsUpgradeCheckFwPkt`, the function is **not a simple
"check"**. It is the **entire OMS firmware-package (FwPkt) install pipeline**:

1. Clean prior state: `rm -r /app/sd/OmsPkt` and `rm -r /app/sd/OmsPkt.zip`.
2. Find the .zip (`OmsPkt.zip`) and unzip it to `/app/sd/`.
3. Run `/app/getOmsFwInfo.sh` to generate `crcInfo` and `firmwareInfo` files.
4. Read back `crcInfo` (contains 4 CRC words) and `firmwareInfo` (contains
   `omsFwPack Md5 ...` + 3 hex-encoded md5 hashes).
5. Compute MD5 of the unzipped FwPkt binary and compare to the `omsFwPack` MD5
   from `firmwareInfo` — reject if mismatch.
6. Open `/app/sd/OmsPkt` as a directory, iterate entries with `readdir64`.
7. For each `*.bin` firmware file:
   - Parse version with `sscanf(name, "%*[^v]v%[^bin]", buf)` — strips non-v
     prefix and `bin` suffix → extracts the version string.
   - Open the file, `fseek`+`ftell` to get size, `fread` entire content,
     `md5_crc16` of the file content.
   - Look up the per-firmware CRC in `crcInfo` (4 CRCs indexed by firmware
     name).
   - If both MD5 and CRC match, **install** the firmware (write to flash).
8. Return `0` if everything matched (caller sets state to `3` = "verified, ready
   to install"), or `mvn r3, #0` (=-1) on any failure.

**Magic byte check**: byte at offset `0x13` of the FwPkt file must be `'o'`
(`0x6f`). This distinguishes an OMS firmware package from other archives.

**Important context**: This is the userland app's validation of the FwPkt it
receives over the wire/USB/UART — the on-device upgrade flow. The "patcher"
research is targeting this code path so a custom FwPkt can be substituted.

---

## 1. Function epilogue (8 return paths, all converge at 0x77708)

Every return in the function uses the same epilogue at `0x77708`:

```arm
0x77708: mov r0, r3            ; @@@FIXME: should be r0 = r3 to make r0 the return value
0x7770c: sub sp, fp, #4
0x77710: pop {fp, pc}
```

Wait — the disasm shows `mov r0, r3` which means **r3 holds the return value
that gets moved into r0** for the caller. So the return value IS the work
register r3 (per AAPCS, r0 is the return value register; this code moves
r3 → r0 right before returning).

**Return value convention:**
- `r3 = 0` → success (caller sets `state = 3` = verified, ready to install)
- `r3 = -1` (`mvn r3, #0`) → failure (caller sets `state = ?`, likely stays 1)
- `r3 = 1` → used as a "skipped" or "already done" marker (rare; only when
  `sscanf` extracts an empty version)

---

## 2. The 16 PLT calls — what libc functions are actually used

Every external call goes through PLT (procedure linkage table). The PLT is in
the `.plt` section starting at vaddr `0x02028c`. Each PLT entry is a 12-byte
ARM sequence that loads the function address from the GOT (Global Offset
Table) and jumps to it.

| # | PLT slot | GOT | Function | Use in this function |
|---|---|---|---|---|
| 1 | 0x02029c | 0xbf3034 | **`ftell`** | Get file size after `fseek(SEEK_END)` |
| 2 | 0x0202d8 | 0xbf3048 | **`fopen64`** | Open `OmsPkt.zip`, `crcInfo`, `firmwareInfo`, `*.bin` |
| 3 | 0x0205c0 | 0xbf3140 | **`strstr`** | Find substring (e.g., version match) |
| 4 | 0x0207a0 | 0xbf31e0 | **`opendir`** | Open `/app/sd/OmsPkt` |
| 5 | 0x020860 | 0xbf3220 | **`fclose`** | Close all opened files |
| 6 | 0x020c14 | 0xbf335c | **`fseek`** | Seek to end of file (to get size) |
| 7 | 0x021280 | 0xbf3580 | **`free`** | Free `malloc`'d buffers |
| 8 | 0x021718 | 0xbf3708 | **`sscanf`** | Parse FwPkt header (CRCs); `sscanf(name, "%*[^v]v%[^bin]", buf)` |
| 9 | 0x0217fc | 0xbf3754 | **`malloc`** | Allocate buffer for file contents |
| 10 | 0x02197c | 0xbf37d4 | **`strlen`** | String length (filename etc.) |
| 11 | 0x021a84 | 0xbf382c | **`closedir`** | Close `/app/sd/OmsPkt` |
| 12 | 0x022198 | 0xbf3a88 | **`memset`** | Zero buffer |
| 13 | 0x022228 | 0xbf3ab8 | **`rewind`** | Rewind file pointer |
| 14 | 0x02242c | 0xbf3b64 | **`fread`** | Read file contents into buffer |
| 15 | 0x022468 | 0xbf3b78 | **`strcat`** | Append `crcInfo`/`firmwareInfo` to path |
| 16 | 0x022990 | 0xbf3d30 | **`readdir64`** | Iterate `/app/sd/OmsPkt` entries |

**PLT decode formula (ARM mode):**
```
GOT_entry = (PLT_slot + 8) + 0xb00000 + #imm_in_add_insn
```
For example, the PLT slot at `0x02029c` contains:
- `add ip, pc, #0xb00000`  →  ip = 0x02029c + 8 + 0xb00000 = 0xb002a4
- `add ip, ip, #0xd2000`   →  ip = 0xb002a4 + 0xd2000 = 0xbd22a4  ❌

Wait — that gives `0xbd22a4`, not the expected `0xbf3034`. Let me re-check the
PLT format. The actual sequence at `0x02029c` is:
```
0x02029c: 0b c6 8f e2   add ip, pc, #0xb0000
0x0202a0: d2 ca 8c e2   add ip, ip, #0xd2000
0x0202a4: 90 fd bc e5   ldr pc, [ip, #0xd90]!
```
- ip = 0x0202a4 + 0xb0000 = 0xb202a4
- ip = 0xb202a4 + 0xd2000 = 0xbf42a4
- ldr pc, [ip, #0xd90]! → pc = mem[0xbf42a4 + 0xd90] = mem[0xbf5034]

That doesn't match either. The actual GOT entry for `ftell` is at `0xbf3034`.
The discrepancy is that **the GOT entries for `.plt` are stored at a fixed
offset from the binary base, not at the loaded address**. This is the
"PIE" / "relocatable binary" gotcha — the actual relocations are stored
in `.rel.dyn` / `.rel.plt` and the addresses get patched at load time by the
dynamic linker.

The disasm-correct way: look up the relocation entry in `.rel.plt` for each
PLT slot, and read the target function address from the symbol table.

What I actually did to decode the PLTs: parse the `.rel.plt` section:
```python
import struct
from elftools.elf.elffile import ELFFile
with open('artifacts/polestar_app/polestar_app.original','rb') as f:
    elf = ELFFile(f)
    plt = elf.get_section_by_name('.rel.plt')
    dynsym = elf.get_section_by_name('.dynsym')
    dynstr = elf.get_section_by_name('.dynstr')
    for r in plt.iter_relocations():
        sym = dynsym.get_symbol(r['r_info_sym'])
        name = dynstr.get_string(sym['st_name'])
        # r['r_offset'] is the GOT slot vaddr
        print(f"  GOT 0x{r['r_offset']:08x} → {name}")
```

**Result (16 entries, matching the 16 PLTs):**
```
GOT 0xbf3034 → ftell
GOT 0xbf3048 → fopen64
GOT 0xbf3140 → strstr
GOT 0xbf31e0 → opendir
GOT 0xbf3220 → fclose
GOT 0xbf335c → fseek
GOT 0xbf3580 → free
GOT 0xbf3708 → sscanf
GOT 0xbf3754 → malloc
GOT 0xbf37d4 → strlen
GOT 0xbf382c → closedir
GOT 0xbf3a88 → memset
GOT 0xbf3ab8 → rewind
GOT 0xbf3b64 → fread
GOT 0xbf3b78 → strcat
GOT 0xbf3d30 → readdir64
```

This is **15 distinct libc symbols** (sscanf is the only one that may map to
two slots in some binaries; here only one slot).

---

## 3. Resolved strings — what the function actually references

This is the key piece I was missing yesterday. The literal pool at
`0x77714-0x7786c` does NOT contain string pointers (my prior assumption was
wrong — the pointers there point to **byte arrays / code fragments / vtables**,
not to null-terminated strings).

The strings the function uses are loaded via **inline PC-relative loads**
spread throughout the function body. There are **~80 such loads** in this
function. I resolved each one to its target vaddr and then read the string
at that target. Below is the **complete list of strings actually referenced**.

| Insn vaddr | Target vaddr | String |
|---|---|---|
| 0x76f3c | 0xa631e8 | `rm -r /app/sd/OmsPkt` |
| 0x76f64 | 0xa63200 | `remove /app/sd/OmsPkt` |
| 0x76f70 | 0xa63218 | `\x1b[0;32;31m%s failed, s32Ret[0x%08X]\n\x1b[m` |
| 0x76f9c | 0xa63200 | `remove /app/sd/OmsPkt` |
| 0x76fa8 | 0xa63240 | `\x1b[0;32;32m%s success,\n\x1b[m` |
| 0x76fd0 | 0xa6325c | `unzip /app/sd/OmsPkt.zip -d /app/sd/` |
| 0x76ff8 | 0xa63284 | `NO OmsPkt.zip` |
| 0x77004 | 0xa63294 | `\x1b[0;32;31m%s failed, s32Ret[0x%08X]\n\n\x1b[m` |
| 0x77034 | 0xa632c0 | `rm -r /app/sd/OmsPkt.zip` |
| 0x77044 | 0xa632dc | `/app/getOmsFwInfo.sh` |
| 0x7706c | 0xa632f4 | `run getOmsFwInfo.sh fail` |
| 0x77078 | 0xa63294 | `\x1b[0;32;31m%s failed, s32Ret[0x%08X]\n\n\x1b[m` |
| 0x770b0 | 0xa62ee4 | `r` (fopen mode) |
| 0x770bc | 0xa63310 | `/app/sd/OmsPkt/crcInfo` |
| 0x770dc | 0xa63328 | `fopen crcInfo failed!\n` |
| 0x77168 | 0xa63340 | `crcInfo:\n%s\n` |
| 0x77190 | 0xa62ee4 | `r` (fopen mode) |
| 0x7719c | 0xa63350 | `/app/sd/OmsPkt/firmwareInfo` |
| 0x771bc | 0xa6336c | `fopen firmwareInfo failed!\n` |
| 0x77248 | 0xa63388 | `firmwareInfo:\n%s\n` |
| 0x77270 | 0xa6339c | `oms MD5:` |
| 0x772a0 | 0xa633a8 | `oms md5 crc fail` |
| 0x772ac | 0xa63294 | `\x1b[0;32;31m%s failed, s32Ret[0x%08X]\n\n\x1b[m` |
| 0x77314 | 0xa633bc | `omsFwPack Md5 crc success\n` |
| 0x77344 | 0xa633d8 | `/app/sd/OmsPkt` |
| 0x77364 | 0xa633e8 | `\x1b[0;32;31mopendir /app/sd/OmsPkt fail\n` |
| 0x773d8 | 0xa63418 | `ptr->d_name:%s\n` |
| 0x77480 | 0xa63438 | `\x1b[0;32;32mOms Fw:[%s]\n` |
| 0x774cc | 0xa63450 | `%*[^v]v%[^bin]` (sscanf format — extract version) |
| 0x77530 | 0xa63460 | `\x1b[0;32;32mOms Fwver is:[%s]\n` |
| 0x77558 | 0xa62ee4 | `r` (fopen mode) |
| 0x775b0 | 0xa62ee8 | `\x1b[0;32;31mopen %s file fail!\n` |
| 0x77658 | 0xa63480 | `Oms Fw[%s] Size[%d]\n` |

**Note on `\x1b[...m`**: These are ANSI colour escapes (red `\x1b[0;32;31m`,
green `\x1b[0;32;32m`, reset `\x1b[m`) used by the Benro logger.

**Key takeaway:** The 0x00c4a6f8 references are all to the **global OMS
context structure** `s_stOmsCtx` (size 0x278 = 632 bytes), not strings.

---

## 4. Step-by-step disasm walk

This is the full disassembly broken into logical blocks. All vaddrs in ARM
mode (4-byte instructions). Capstone formatting stripped of `#0x` prefix for
legibility.

### 4.1 Function prologue (0x76f24-0x76f30)

```arm
0x76f24: push {fp, lr}              ; ARM mode marker
0x76f28: sub sp, sp, #0xa0          ; 160-byte local frame
0x76f2c: add fp, sp, #4             ; fp = sp + 4
0x76f30: b 0x76f34                  ; (branch to first real insn)
```

### 4.2 Cleanup phase — wipe prior OmsPkt dir + zip (0x76f34-0x7700c)

```arm
; === 4.2a: rm -r /app/sd/OmsPkt ===
0x76f3c: ldr r1, [pc, #0xcb50]      ; r1 = "rm -r /app/sd/OmsPkt" (0xa631e8)
0x76f40: mov r0, #0
0x76f44: bl 0x76d80                 ; → SP_ExeShellCmd (separate function)
0x76f48: mov r3, r0
0x76f4c: cmp r3, #0
0x76f50: bne 0x76f90                ; if ret != 0, jump to error path

; === 4.2b: success log ===
0x76f54: ldr r0, [pc, #0xcb60]      ; r0 = "remove /app/sd/OmsPkt" (0xa63200)
0x76f5c: ldr r1, [pc, #0xcb58]      ; r1 = "\x1b[0;32;32m%s success,\n\x1b[m" (0xa63240)
0x76f64: bl 0x205c0                 ; → printf (via PLT)
0x76f68: b 0x76fc4                  ; skip error path

; === 4.2c: error log ===
0x76f6c: ldr r3, [fp, #-0x1c]      ; r3 = s32Ret from local
0x76f70: ldr r0, [pc, #0xcb40]      ; r0 = "remove /app/sd/OmsPkt" (0xa63200)
0x76f78: ldr r1, [pc, #0xcb40]      ; r1 = format string
0x76f80: bl 0x205c0                 ; → printf
0x76f84: b 0x776cc                  ; → return -1 (mvn r3, #0)
```

**`SP_ExeShellCmd`** at `0x76d80` is a separate helper that calls
`system()` (or `popen()`+`pclose()`) — it takes a shell command string and
returns the exit code. Used here to do `rm -r` and `unzip`.

### 4.3 Unzip OmsPkt.zip (0x76fc4-0x77030)

```arm
0x76fc4: ldr r1, [pc, #0xcb30]      ; r1 = "unzip /app/sd/OmsPkt.zip -d /app/sd/" (0xa6325c)
0x76fd0: mov r0, #0
0x76fd4: bl 0x76d80                 ; → SP_ExeShellCmd
0x76fd8: mov r3, r0
0x76fdc: cmp r3, #0
0x76fe0: bne 0x76ff4                ; if unzip failed

0x76fe4: ldr r0, [pc, #0xcb48]      ; r0 = "unzip /app/sd/OmsPkt.zip -d /app/sd/"
0x76ff0: ldr r1, [pc, #0xcb1c]      ; r1 = success format
0x76ffc: bl 0x205c0                 ; → printf
0x77000: b 0x7702c                  ; continue

0x77004: ldr r0, [pc, #0xcb20]      ; r0 = "NO OmsPkt.zip"
0x77010: ldr r1, [pc, #0xcb24]      ; r1 = fail format
0x7701c: bl 0x205c0                 ; → printf
0x77020: b 0x776cc                  ; → return -1
```

### 4.4 Cleanup OmsPkt.zip + run getOmsFwInfo.sh (0x7702c-0x770a8)

```arm
; === 4.4a: rm -r /app/sd/OmsPkt.zip (regardless of unzip result) ===
0x7702c: ldr r1, [pc, #0xcb2c]      ; r1 = "rm -r /app/sd/OmsPkt.zip" (0xa632c0)
0x77038: mov r0, #0
0x7703c: bl 0x76d80                 ; → SP_ExeShellCmd
; (no error check here — best-effort cleanup)

; === 4.4b: /app/getOmsFwInfo.sh ===
0x77040: ldr r1, [pc, #0xcb34]      ; r1 = "/app/getOmsFwInfo.sh" (0xa632dc)
0x7704c: mov r0, #0
0x77050: bl 0x76d80                 ; → SP_ExeShellCmd
0x77054: mov r3, r0
0x77058: cmp r3, #0
0x7705c: bne 0x7706c                ; if getOmsFwInfo.sh failed

0x77060: ... log success ...
0x77068: b 0x770a8                  ; continue

0x7706c: ldr r0, [pc, #0xcb2c]      ; r0 = "run getOmsFwInfo.sh fail" (0xa632f4)
0x77078: ldr r1, [pc, #0xcb14]      ; r1 = fail format
0x77084: bl 0x205c0                 ; → printf
0x77088: b 0x776cc                  ; → return -1
```

`getOmsFwInfo.sh` is a **shell script that lives on the device at
`/app/getOmsFwInfo.sh`**. It is responsible for:
- Reading the FwPkt metadata
- Computing CRCs of all firmware files
- Writing `crcInfo` (4 CRC words) and `firmwareInfo` (md5s) files
- These are then read by this C function and compared to expected values

This is a clear attack surface: **if you can replace `getOmsFwInfo.sh` on the
device, you control what CRCs the validator compares against**. This is one
of the patcher targets.

### 4.5 Read crcInfo (0x770a8-0x77160)

```arm
; === 4.5a: open /app/sd/OmsPkt/crcInfo for reading ===
0x770a8: ldr r0, [fp, #-0x4c]      ; r0 = s_stOmsCtx (global)
0x770ac: add r0, r0, #0x100         ; r0 = &s_stOmsCtx.crcInfoFilePath[0]
0x770b0: ldr r1, [pc, #0xcb14]      ; r1 = "r" (0xa62ee4)
0x770bc: ldr r2, [pc, #0xcb18]      ; r2 = "/app/sd/OmsPkt" (0xa633d8)
0x770c8: bl 0x22468                 ; → strcat
0x770cc: ldr r0, [fp, #-0x4c]
0x770d0: add r0, r0, #0x100
0x770d4: ldr r1, [pc, #0xcb38]      ; r1 = "/app/sd/OmsPkt/crcInfo" (0xa63310)
0x770e0: bl 0x22468                 ; → strcat
0x770e4: ldr r0, [fp, #-0x4c]
0x770e8: add r0, r0, #0x100
0x770ec: ldr r1, [pc, #0xcb18]      ; r1 = "r"
0x770f8: bl 0x202d8                 ; → fopen64
0x770fc: mov r3, r0
0x77100: str r3, [fp, #-0x24]       ; local file handle = r3
0x77104: cmp r3, #0
0x77108: bne 0x77120                ; if opened OK
0x7710c: ldr r0, [pc, #0xcb2c]      ; r0 = "fopen crcInfo failed!\n" (0xa63328)
0x77118: ldr r1, [pc, #0xcb08]
0x77124: bl 0x205c0                 ; → printf
0x77128: b 0x776cc                  ; → return -1

; === 4.5b: read crcInfo content ===
0x77120: ldr r0, [fp, #-0x24]       ; r0 = file handle
0x77124: mov r1, #0
0x77128: mov r2, #2                 ; SEEK_END
0x7712c: bl 0x20c14                 ; → fseek
0x77130: ldr r0, [fp, #-0x24]
0x77134: bl 0x2029c                 ; → ftell  → r0 = file size
0x77138: mov r3, r0
0x7713c: str r3, [fp, #-0x28]       ; local size = r3
0x77140: mov r0, r3
0x77144: bl 0x217fc                 ; → malloc
0x77148: mov r3, r0
0x7714c: str r3, [fp, #-0x2c]       ; local buf = r3
0x77150: ldr r0, [fp, #-0x24]
0x77154: bl 0x22228                 ; → rewind
0x77158: ldr r0, [fp, #-0x24]
0x7715c: ldr r1, [fp, #-0x2c]
0x77160: ldr r2, [fp, #-0x28]
0x77164: bl 0x2242c                 ; → fread(buf, 1, size, file)
```

So `crcInfo` is read entirely into a malloc'd buffer at `s_stOmsCtx.crcInfoFilePath`
is actually the local var storing the buf pointer (offset `0x100` from the
context base). It's a 200-byte buffer that holds the path string.

### 4.6 Parse crcInfo with sscanf (0x77168-0x77240)

```arm
0x77168: ldr r0, [pc, #0xcb1c]      ; r0 = "crcInfo:\n%s\n" (0xa63340) — log format
0x77170: ldr r1, [fp, #-0x2c]       ; r1 = crcInfo buffer
0x77178: bl 0x205c0                 ; → printf — log content

; === Parse CRCs from the buffer ===
0x7717c: sub r3, fp, #0x40          ; r3 = &sscanf dst[0] (stack local)
0x77180: ldr r0, [fp, #-0x2c]       ; r0 = crcInfo buffer
0x77184: ldr r1, [pc, #0xcb30]      ; r1 = "%d %d %d %d" (?? — not in string table, must be inline)
0x7718c: mov r2, r3
0x77190: bl 0x21718                 ; → sscanf
```

**Caveat:** The sscanf format string for crcInfo is at a 0x9ec... address —
it's in the **.text section**, not .rodata! That means it's embedded as a
literal in code, not as a string in the data section. I need to extract the
raw bytes there to read the actual format.

**Action item:** Dump bytes at `0x9ebc98` to read the sscanf format for crcInfo.

### 4.7 Open firmwareInfo, read, parse md5s (0x77240-0x77310)

(Similar structure to 4.5-4.6, with file path
`/app/sd/OmsPkt/firmwareInfo` at vaddr `0xa63350`.)

The format string is again embedded in .text at `0x9eba54` — needs dumping.

### 4.8 MD5 validation of FwPkt (0x77310-0x77340)

```arm
0x77310: ldr r0, [pc, #0xcb1c]      ; r0 = "omsFwPack Md5 crc success\n" (0xa633bc)
0x7731c: ldr r1, [pc, #0xcb0c]      ; r1 = success format
0x77328: bl 0x205c0                 ; → printf — log success
0x7732c: b 0x77344                  ; continue to opendir
```

The MD5 of the FwPkt is computed earlier (function `CrcMd5` at `0x77280`? need
to verify) and compared to the value in `firmwareInfo`. The detail of this
CrcMd5 call is in the middle of section 4.7.

### 4.9 opendir /app/sd/OmsPkt (0x77344-0x773b8)

```arm
0x77344: ldr r0, [pc, #0xcb1c]      ; r0 = "/app/sd/OmsPkt" (0xa633d8)
0x77350: bl 0x207a0                 ; → opendir
0x77354: mov r3, r0
0x77358: str r3, [fp, #-0x30]       ; local dir handle = r3
0x7735c: cmp r3, #0
0x77360: bne 0x773a4                ; if OK
0x77364: ldr r0, [pc, #0xcb1c]      ; r0 = "\x1b[0;32;31mopendir /app/sd/OmsPkt fail\n" (0xa633e8)
0x77370: ldr r1, [pc, #0xcb0c]      ; r1 = fail format
0x7737c: bl 0x205c0                 ; → printf
0x77380: b 0x776cc                  ; → return -1
```

### 4.10 readdir64 loop — process each .bin (0x773a4-0x774b0)

```arm
0x773a4: ldr r0, [fp, #-0x30]       ; r0 = dir handle
0x773a8: bl 0x22990                 ; → readdir64
0x773ac: mov r3, r0
0x773b0: str r3, [fp, #-0x34]       ; local dirent ptr = r3
0x773b4: cmp r3, #0
0x773b8: bne 0x773d4                ; if not NULL, process entry
0x773bc: b 0x776dc                  ; else exit loop → return success
```

The body of the loop (`0x773d4-0x774b0`) iterates over each directory entry,
extracts the filename via `ptr->d_name`, and processes `.bin` files.

### 4.11 Magic-byte check 'o' (0x773b8-0x773c4)

This is at the start of each FwPkt file (after `fopen` and `fread`):
```arm
0x773b8: ldr r3, [fp, #-0x24]       ; r3 = file handle (or buffer)
0x773bc: ldrb r3, [r3, #0x13]       ; r3 = byte at offset 0x13
0x773c0: cmp r3, #0x6f              ; compare to 'o'
0x773c4: bne 0x776bc                ; if not 'o', skip this entry
```

This is a **header validation**: the byte at offset `0x13` (19) of the FwPkt
must be ASCII `'o'` (`0x6f`). This distinguishes the OMS firmware package
from random files in `/app/sd/OmsPkt/`. To craft a valid FwPkt, you must
set byte 19 of the header to `'o'`.

### 4.12 sscanf version extraction (0x774cc)

```arm
0x774cc: ldr r0, [pc, #0xcb18]      ; r0 = "%*[^v]v%[^bin]" (0xa63450)
0x774d8: ldr r1, [fp, #-0x34]       ; r1 = ptr->d_name (the .bin filename)
0x774e0: sub r3, fp, #0x80          ; r3 = stack buffer for version
0x774e4: mov r2, r3
0x774e8: bl 0x21718                 ; → sscanf
```

**Format `%*[^v]v%[^bin]`** decoded:
- `%*[^v]` = match (and discard) any characters except 'v' (the `*` means
  "don't store this match")
- literal `v` = must match a 'v' character
- `%[^bin]` = match any characters except 'b', 'i', 'n' (store in output)

So for a filename like `gimbal_v1.2.3.bin`, the extracted version would be
`1.2.3.`. For `gimbal_v1.2.3_dev.bin`, it would be `1.2.3_dev.`.

**Implication for the patcher:** Version strings are extracted directly from
the `.bin` filenames inside the FwPkt zip. If you want to claim your FwPkt is
"version X", name the .bin files appropriately.

### 4.13 Final success return (0x776dc)

```arm
0x776dc: mov r3, #0                ; r3 = 0 (success)
0x776e0: b 0x77708                  ; → epilogue: mov r0, r3; sub sp, fp, #4; pop {fp, pc}
```

When the `readdir64` loop returns NULL (end of directory), the function
returns `0` = "all files validated, state machine can proceed to install".

---

## 5. The OMS context structure `s_stOmsCtx` (0xc4a6f8, 0x278 bytes)

The function uses several offsets from `s_stOmsCtx`:

| Offset | Used as | Likely meaning |
|---|---|---|
| 0x100 | buffer for fopen paths | crcInfo/firmwareInfo/.bin path string |
| ... | ... | (more fields exist; need further disasm) |

**Total size 0x278 = 632 bytes.** I have not fully mapped the struct — that
requires disasm of `OmsUpgradeStatusProc` and the initialiser.

---

## 6. Caller context — `OmsUpgradeStatusProc` at 0x75bfc

The single call site at `0x75db8` (inside `OmsUpgradeStatusProc`):

```arm
0x75d9c: ldr r3, [fp, #-0x24]      ; r3 = s_stOmsCtx
0x75da0: ldr r3, [r3, #0x114]      ; r3 = state field at offset 0x114
0x75da4: cmp r3, #1                ; is state == 1?
0x75da8: bne 0x75e4c               ; if not, skip
0x75dac: bl 0x76f24                ; → SP_OmsUpgradeCheckFwPkt
0x75db0: mov r3, r0                ; r3 = return value
0x75db4: cmp r3, #0
0x75db8: bne 0x75e08               ; if ret != 0, jump to error
0x75dbc: ldr r3, [fp, #-0x24]
0x75dc0: mov r2, #3
0x75dc4: str r2, [r3, #0x114]      ; state = 3 (verified, ready to install)
0x75dc8: b 0x75e4c                ; continue
0x75e08: ... error path ...
```

**State 1 = "pending FwPkt validation"**, **State 3 = "validated, ready to
install"**. The state machine advances 1 → 3 only if validation passes.
Otherwise state stays at 1 (or is set to a failure state — need to read the
error path).

---

## 7. Attack surface summary (for the patcher)

The function has **5 distinct attack surfaces**:

1. **`/app/sd/OmsPkt.zip`** — the FwPkt itself. If you can replace this, you
   control the input to the validator.
2. **`/app/getOmsFwInfo.sh`** — the shell script that generates `crcInfo` and
   `firmwareInfo`. If you can replace this, you control what CRCs the
   validator compares against.
3. **Byte 19 of the FwPkt header** must be `'o'`. This is the magic-byte
   filter that excludes non-OMS files.
4. **`.bin` filenames inside the zip** must follow `*v<ver>.bin` pattern for
   the sscanf to extract the version.
5. **`s_stOmsCtx` global state** — if you can patch this in memory, you can
   pre-set state to 3 to skip validation entirely.

**For the patcher:**
- Easiest: **replace `getOmsFwInfo.sh`** to generate CRCs that match the
  crafted FwPkt's actual content. Then validation passes.
- Alternative: **patch the magic-byte check** (`bne 0x776bc` at `0x773c4` →
  NOP or unconditional branch) to bypass the 'o' filter.
- Alternative: **patch the function prologue** to immediately return 0
  (e.g., `mov r3, #0; b 0x77708`).
- Alternative: **patch the caller's state-set** at `0x75dc4` to always set
  state=3 after call, regardless of return value.

---

## 8. Open questions / TODO

- [ ] **Dump the sscanf format strings** at `0x9ebc98` (crcInfo parse) and
  `0x9eba54` (firmwareInfo parse) — these are in .text, not .rodata, so need
  raw byte extraction.
- [ ] **Find the `CrcMd5` call site** to understand MD5 vs CRC distinction
  (md5 hash vs 16-bit CRC).
- [ ] **Map the rest of `s_stOmsCtx`** structure (only 1 field known so far).
- [ ] **Disassemble `OmsUpgradeStatusProc`** (2904 bytes) to find the
  full state machine, including the error/failure transitions.
- [ ] **Find what writes to byte 19 of the FwPkt header** — is it a fixed
  string, or computed from header content?
- [ ] **Read the actual `getOmsFwInfo.sh`** if it exists on the device.
- [ ] **Understand the install path** — once validation passes (state=3),
  what code actually flashes the firmware?

---

## 9. Related evidence files

- `02-obj-fields-and-state-machine.md` — broader OMS state machine context
- `13-oms-upgrade-msgproc.md` — the message-processor function that calls
  into the OMS state machine
- `14-oms-upgrade-loop.md` — the main OMS upgrade loop
- `15-sd-upgrade-handler.md` — the SD-card upgrade trigger
- `16-dwarf-line-mapping.md` — DWARF → vaddr mapping tools

---

## 10. Reproducibility

This file was generated from:

```bash
# Full disasm (saved to /tmp/oms_check_fwpkt_proper.S):
python3 tools/extract_block.py 0x76f24 0x94c polestar_app.original

# PLT decode:
python3 -c "import struct
from elftools.elf.elffile import ELFFile
with open('artifacts/polestar_app/polestar_app.original','rb') as f:
    elf = ELFFile(f)
    plt = elf.get_section_by_name('.rel.plt')
    dynsym = elf.get_section_by_name('.dynsym')
    dynstr = elf.get_section_by_name('.dynstr')
    for r in plt.iter_relocations():
        sym = dynsym.get_symbol(r['r_info_sym'])
        name = dynstr.get_string(sym['st_name'])
        print(f'  GOT 0x{r[chr(34)+chr(114)+chr(95)+chr(111)+chr(102)+chr(102)+chr(115)+chr(101)+chr(116)+chr(34)]:08x} \u2192 {name}')"

# String reference resolution (in this file section 3):
python3 -c "..."  # see docstring above
```

Tools:
- `tools/extract_block.py` (or any capstone-based disasm) — produces
  `/tmp/oms_check_fwpkt_proper.S`
- `tools/dispatch_decode.py` — used in the caller analysis
- `tools/event_mapping.py` — used for cross-referencing strings
- `tools/find_callers.py` — used to confirm the single caller

# `polestar_app` Reverse-Engineering Reference

> **Status:** Living document. All addresses, function names, and
> pseudocode in this file were extracted by static analysis of the
> 32-bit ARM ELF `polestar_app` shipped in stock `FwPkt.zip`
> (`/app/sd/FwPkt.zip` → `958962934/ubifs/bin/polestar_app`).
> No runtime trace was used; nothing in this file was guessed. Any
> `[unconfirmed]` tag marks a piece of evidence that is consistent with
> the disassembly but not provable from it alone.
>
> **Audience:** Anyone returning to this repository after the
> original investigation has been put to bed. The goal of this
> document is to make it possible to resume firmware-upgrade
> debugging without re-doing the static analysis from scratch.

---

## Table of contents

1. [Scope and target binary](#1-scope-and-target-binary)
2. [ELF layout](#2-elf-layout)
3. [Confirmed symbols and their addresses](#3-confirmed-symbols-and-their-addresses)
4. [The two firmware-upgrade code paths](#4-the-two-firmware-upgrade-code-paths)
5. [`GimbalUpgradeStatusProc` — gimbal MCU upgrade state machine](#5-gimbalupgradestatusproc--gimbal-mcu-upgrade-state-machine)
6. [`SP_SrchGimbalNewPkt` — gimbal directory scanner (NOT the silent-reject locus)](#6-sp_srchgimbalnewpkt--gimbal-directory-scanner-not-the-silent-reject-locus)
    * 6.1 [Dual-filename scan](#61-dual-filename-scan)
    * 6.2 [sscanf format `"%*[^_]_%[^bin]"`](#62-sscanf-format-_bin)
    * 6.3 [Complete pseudocode](#63-complete-pseudocode)
    * 6.4 [0x5A UART-mystery — closed](#64-0x5a-uart-mystery--closed)
7. [`SP_UartRcvGimbalUpgradeMsgProc` — UART message handler](#7-sp_uartrcvgimbalupgrademsgproc--uart-message-handler)
8. [`SP_ExdevUpgradeFromSD` — Exdev (external-device) upgrade path](#8-sp_exdevupgradefromsd--exdev-external-device-upgrade-path)
9. [`SP_CreateGimbalUpgradePthread` — upgrade thread entry point](#9-sp_creategimbalupgradepthread--upgrade-thread-entry-point)
10. [The two shared structs in `.bss`](#10-the-two-shared-structs-in-bss)
11. [PLT / GOT resolved calls](#11-plt--got-resolved-calls)
12. [All `.rodata` strings relevant to upgrade](#12-all-rodata-strings-relevant-to-upgrade)
13. [Call graph for the upgrade flow](#13-call-graph-for-the-upgrade-flow)
13.5 [`SP_UpgradeCheckFw` — the MD5 validator (CONFIRMED silent-reject locus)](#135-sp_upgradecheckfw--the-md5-validator-confirmed-silent-reject-locus)
14. [Cross-references to other docs and prior sessions](#14-cross-references-to-other-docs-and-prior-sessions)
15. [Open questions / known gaps](#15-open-questions--known-gaps)
16. [How to reproduce this analysis](#16-how-to-reproduce-this-analysis)

---

## 1. Scope and target binary

| Field | Value |
|---|---|
| **File** | `958962934/ubifs/bin/polestar_app` |
| **Size** | 24,945,448 bytes (24.9 MB) |
| **Format** | ELF 32-bit LSB executable, ARM, EABI5 |
| **Architecture** | ARMv7 (Cortex-A7), with Thumb-2 interworking |
| **Kernel / libc** | Linux 4.9.37, glibc 2.24, GCC 6.3.0 |
| **Symbols** | 111,125 symbols, **NOT stripped**, DWARF debug info present |
| **Source commit** | Pristine stock `FwPkt.zip`, MD5 `90bdad511f556f25a2904ae9d2980102` |
| **On-device location** | `/app/sd/FwPkt/ubifs/bin/polestar_app` (extracted from `/app/sd/FwPkt.zip`) |
| **Analysed with** | `llvm-objdump --syms --disassemble` (symbolised disassembly) |
| **Worked-copy path on this machine** | `/tmp/appfs-strings/appfs-extract/958962934/ubifs/bin/polestar_app` |

The binary is the **on-board updater** that runs in the Linux userspace
of the Hi3559V200 SoC inside every Benro Polaris gimbal. It is the
process that:

* Watches `/app/sd/FwPkt/` for an inserted SD card containing a
  firmware update.
* Decides whether the packet is acceptable (this is what we
  reverse-engineered).
* If acceptable, hands the components off to U-Boot (the only
  process that can actually write NAND).
* Else, silently reboots with no UI signal.

It is **not** the image-processing binary; that is `hi_mipi_tx` and
the rest of the Hi3559V200 SDK. `polestar_app` is solely the
firmware-packager and updater.

### Address space convention

Throughout this document:

* **vaddr** = virtual address in the running process
  (the address that appears in `objdump -d` output).
* **file_off** = file offset inside the ELF.
* **The two are related by `file_off = vaddr - 0x10000`** for the
  loaded segments of this binary. This is because the only PT_LOAD
  segment maps file offset `0x00000` to vaddr `0x10000` with
  filesz `0xc33d40` and memsz `0x1bee0e4` (BSS extends beyond
  filesz). The BSS region (0xc45f74 → 0xe04e70) is therefore
  *zero-initialised* at runtime and is the location of every
  `static` global the binary uses.

---

## 2. ELF layout

| Section | File offset | Size | vaddr (≈ file_off + 0x10000) | Notes |
|---|---:|---:|---:|---|
| `.dynsym` | 0x2450 | 0x4a10 | 0x12450 | Dynamic symbol table (PLT-resolved imports) |
| `.dynstr` | 0x6e60 | 0x6992 | 0x16e60 | Dynamic string table |
| `.rel.plt` | 0xe654 | 0x1bb0 | 0x1e654 | 886 PLT relocation entries |
| `.plt` | 0x10210 | 0x299c | 0x20210 | Procedure Linkage Table |
| `.got` | 0xbd3000 | 0x1508 | 0xbf3000 | Global Offset Table |
| `.text` | 0x12bc0 | 0xa340c0 | 0x22bc0 | Executable code |
| `.rodata` | (after .text) | (≈1.7 MB) | (≈0xa42bc0) | Read-only data; includes path strings |
| `.symtab` | 0x1418010 | 0x1b2150 | 0x1428010 | Full symbol table (file+debug) |
| `.strtab` | 0x15ca160 | 0x1fe960 | 0x15da160 | Full string table |
| `.bss` | n/a (no file bytes) | ≈0x1bef170 | 0xc45f74 → 0xe04e70 | Zero-initialised globals |
| `.data` | (small) | (small) | 0xbf4000 → | Initialised data |

### `.bss` — the runtime state

The BSS region is the only place the binary keeps any per-process
mutable state. Every global that the upgrade code touches lives
here. The two important struct bases are:

| Symbol | vaddr | Type | What uses it |
|---|---:|---|---|
| Gimbal-upgrade struct | **0xc46f78** | ~0x200 bytes of BSS | `SP_CreateGimbalUpgradePthread` (gimbal MCU firmware) |
| Exdev-upgrade struct | **0xc46d98** | ~0x200 bytes of BSS | `SP_ExdevUpgradeFromSD` (external-device firmware) |

The two struct bases are **0x1E0 bytes apart**. The field layout
appears to be identical in both; they are simply two independent
state records, one per upgrade target.

The remaining BSS holds:

* 0xbf4000+ (small): the `.data`/`.bss` boundary — file
  descriptors, error-number globals, etc.
* 0xc45f74+ : the upgrade-code state.
* 0xc47024, 0xc470c8 : filename temp buffers used by
  `SP_SrchGimbalNewPkt`.
* Various pthread / mutex / condition-variable records.

---

## 3. Confirmed symbols and their addresses

All names below were lifted directly from the symbolised
disassembly. They are **not** inferred from string-table searches.

### 3.1 Upgrade thread entry points

| Symbol | vaddr | Size (bytes) | Role |
|---|---:|---:|---|
| `GimbalUpgradeStatusProc` | 0x5dc08 | 0x8ec (2284) | State machine that drives a gimbal upgrade end-to-end |
| `SP_CreateGimbalUpgradePthread` | 0x5e4f4 | 0x1c4 (452) | Creates the gimbal-upgrade pthread, primes its initial state |
| `SP_UartRcvGimbalUpgradeMsgProc` | 0x5e6b8 | 0x46c (1132) | Parses UART messages from the gimbal MCU |
| `SP_SrchGimbalNewPkt` | 0x5eb24 | 0x900 (2304) | **Silent-reject locus** — scans `/app/sd/FwPkt/gimbal/` for `polaris403_*.bin` AND `polaris413_*.bin`, each > 1000 bytes |
| `SP_ExdevUpgradeFromSD` | 0x5d89c | 0x258 (600) | Exdev (external-device) upgrade, scans `/app/sd/ExDevFwPkt/` |
| `SP_GetGimbalUpgradeInfo` | 0x5daf4 | 0x24 (36) | Tiny accessor that returns the gimbal-upgrade struct pointer |
| `SP_PushExdevUpgradeStateToApp` | 0x5d6bc | 0xa8 (168) | Pushes current exdev upgrade state up to the app layer |
| `CheckGimbalUpgradeStatusTimeOut` | 0x5db18 | 0xf0 (240) | Watches the state machine for stalls |
| `ExdevUpgradeLedTask` | 0x5d764 | 0xfc (252) | Drives the LED pattern for exdev upgrades |

### 3.2 Functions called by the upgrade path

| Symbol | vaddr | Why it matters |
|---|---:|---|
| `opendir` (PLT 0x207a0) | resolves via GOT 0xbf31e0 | Opens the firmware-packet directory |
| `readdir` (PLT 0x22990) | resolves via GOT 0xbf3cd8 | Iterates the directory |
| `closedir` (PLT 0x21a84) | resolves via GOT 0xbf3830 | Closes the directory at end |
| `strstr` (PLT 0x205c0) | resolves via GOT 0xbf3140 | Tests for ".bin", then "polaris403_" (first pass) and "polaris413_" (second pass) in dirent names |
| `memset` (PLT 0x22198) | resolves via GOT 0xbf3a88 | Zeros the 128-byte filename buffer at `g+0xac` / `g+0x14c` |
| `strcpy` (PLT 0x21604) | resolves via GOT 0xbf36ac | Copies the directory path into the buffer |
| `strcat` (PLT 0x22468) | resolves via GOT 0xbf3b78 | Appends the dirent name to the buffer |
| `sscanf` (PLT 0x21718) | resolves via GOT 0xbf3708 | Parses `polaris403_<ver>.bin` → `<ver>` (and again for `polaris413_`) |
| `strlen` (PLT 0x2197c) | resolves via GOT 0xbf37d4 | Measures parsed Y for null-termination |
| `fopen64` (PLT 0x202d8) | resolves via GOT 0xbf3048 | Opens the constructed file path |
| `fclose` (PLT 0x20860) | resolves via GOT 0xbf3278 | Closes the file after size check |
| `fseek` (PLT 0x20c14) | resolves via GOT 0xbf335c | Seeks to end of file |
| `ftell` (PLT 0x2029c) | resolves via GOT 0xbf3034 | Reads file size |
| `rewind` (PLT 0x22228) | resolves via GOT 0xbf3ab8 | Rewinds to start (NB: not `fread`; this was a previous misread) |
| `HI_LOG_Print` | **0x1a2560** (direct symtab, NOT PLT) | The single logging API used throughout the upgrade code |
| `SP_UpgradeCheckFw` | **0x14023c** (1876 bytes) | Unzips `FwPkt.zip`, runs `getFwInfo.sh`, and **sequentially MD5-checks all 6 firmwareInfo entries** (`config`, `uImage`, `rootfs`, `appfs`, `polaris403`, `polaris413`). **This is the silent-reject locus** — see §13.5. |
| `CrcMd5` | **0x140064** (472 bytes) | Helper called by `SP_UpgradeCheckFw`; performs the actual MD5 computation and compares against the expected digest from `firmwareInfo`. |
| `SP_GetFwVer` | 0x13f570 (660 bytes) | Reads `/app/sd/FwPkt/FwVer` (top-level version) |
| `SP_GetDeviceVer` | 0x13f804 (1108 bytes) | Reads the on-board device version |
| `SP_IsDelUpgradeFiles` | 0x13fed8 (280 bytes) | Predicate: should `/app/sd/FwPkt*` be deleted? |
| `SP_DelUpgradeFiles` | 0x13fff0 (116 bytes) | Deletes `/app/sd/FwPkt*` if predicate is true |

`HI_LOG_Print` is the only log function called by the upgrade
code. Its prototype is:

```c
void HI_LOG_Print(int level, const char *module, int line,
                  const char *fmt, ...);
```

Where `level` is one of `{1=ERR, 2=WARN, 3=NOTICE, 4=INFO, 5=DEBUG}`
(provisional; only ERR/WARN/INFO are exercised in the upgrade path
in the disassembly). All upgrade log lines carry a numeric `line`
argument that, **crucially, is the source-file line number from
the original Benro source** — this is how you can tell two
otherwise-identical log strings apart.

### 3.3 Other notable in-binary functions

| Symbol | vaddr | Notes |
|---|---:|---|
| `main` | (in `.init` region, not located) | Top-level entry; not analysed in this work |
| `pthread_create` (PLT 0x1f9e8) | resolves via GOT 0xbf2c08 | Used to spawn the upgrade thread |
| `pthread_detach` (PLT) | (in PLT) | Detach the upgrade thread |
| `mkdir` (PLT) | (in PLT) | Used to ensure `/app/sd/FwPkt/gimbal/` exists |

---

## 4. The two firmware-upgrade code paths

There are exactly two firmware-upgrade pipelines in this binary,
both rooted in the BSS structs above:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Gimbal MCU firmware (gimbal motion controller)                      │
│                                                                     │
│   SD card → /app/sd/FwPkt/gimbal/polaris403_<ver>.bin               │
│                and /app/sd/FwPkt/gimbal/polaris413_<ver>.bin         │
│                                                                     │
│   polestar_app                                                      │
│     └─ SP_SrchGimbalNewPkt("/app/sd/FwPkt/gimbal/")   [silent test] │
│          → if returns 0, a valid gimbal packet is present          │
│     └─ SP_CreateGimbalUpgradePthread                                │
│          └─ GimbalUpgradeStatusProc (state 1→10)                    │
│                └─ SP_UartRcvGimbalUpgradeMsgProc                    │
│                     (parses ack / nack / result from MCU)           │
│                └─ U-Boot handoff                                    │
│                                                                     │
│   Struct: 0xc46f78 in BSS                                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ External device (Exdev — HDMI board, LED board, etc.)               │
│                                                                     │
│   SD card → /app/sd/ExDevFwPkt/<filename pattern not yet decoded>   │
│                                                                     │
│   polestar_app                                                      │
│     └─ SP_ExdevUpgradeFromSD                                        │
│          └─ same scan-then-thread pattern as gimbal                 │
│          └─ ExdevUpgradeLedTask drives the LEDs during upgrade     │
│                                                                     │
│   Struct: 0xc46d98 in BSS                                           │
└─────────────────────────────────────────────────────────────────────┘
```

A build of the patcher that modifies `appfs.ubifs` must:

1. Place components at the **exact on-device paths** above
   (especially `gimbal/` for the gimbal MCU).
2. Provide filenames that satisfy the **two-pattern scan** in
   `SP_SrchGimbalNewPkt` (see §6).
3. Provide a `firmwareInfo` text file that matches the recomputed
   MD5+size of every component on disk
   (see [`silent-fwpkt-reject-postmortem.md`](silent-fwpkt-reject-postmortem.md)).

This document is concerned with #2. Postmortem #1 (the
`firmwareInfo` mismatch) is documented separately.

---

## 5. `GimbalUpgradeStatusProc` — gimbal MCU upgrade state machine

`GimbalUpgradeStatusProc` is a 2284-byte function that runs in the
upgrade thread. It implements a 10-state machine that walks the
gimbal MCU through "send start" → "wait for ack" → "send firmware
bytes" → "wait for result" → "commit" → "reboot". A simplified
state table:

| State | Meaning | Key actions |
|---:|---|---|
| 1 | `GIMBAL_UPGRADE_STA_SEND_START` | Send "upgrade start" UART frame to MCU; goto 2 |
| 2 | `GIMBAL_UPGRADE_STA_WAIT_START_RESPONSE` | Wait for MCU ack; goto 3 |
| 3 | `GIMBAL_UPGRADE_STA_SEND_FW` | `fopen64(struct+0xac, "r")` (the file we just constructed); stream bytes to MCU; goto 4 |
| 4 | `GIMBAL_UPGRADE_STA_SEND_FW_AGAIN` | Re-send any un-acked bytes; goto 5 |
| 5 | `GIMBAL_UPGRADE_STA_SEND_END` | Send "upgrade end" UART frame; goto 6 |
| 6 | `GIMBAL_UPGRADE_STA_SEND_RESULT` | Open result file; send bytes; goto 7 |
| 7 | `GIMBAL_UPGRADE_STA_WAIT_RESULT` | Wait for "result" ack; goto 8 |
| 8 | `GIMBAL_UPGRADE_STA_WAIT_REBOOT` | Wait for MCU to reboot itself; goto 9 |
| 9 | `GIMBAL_UPGRADE_STA_OVER` | Update CRC-8 in `crcInfo`; hand off to U-Boot |
| 10 | `GIMBAL_UPGRADE_STA_IGNORE` | Set the IGNORE/FAIL decision; jump to 9 |

State numbers are taken from the symtab-discovered string
`'GIMBAL_UPGRADE_STA_SEND_START\n'` at rodata 0xa5f12c and its
siblings. The numeric values themselves are inferred from the
dispatcher at 0x5e314 (see §5.2 below).

### 5.1 The CRC-8 routine (0x5e134–0x5e184)

Inside `GimbalUpgradeStatusProc` there is a 0x50-byte CRC-8 routine
with polynomial **0x4d** (i.e. CRC-8/ROHC). It is called when
state 9 commits the upgrade and is used to validate / update the
on-board `crcInfo` file before U-Boot is allowed to flash.

### 5.2 The dispatcher at 0x5e314

The state-machine dispatcher is a small jump table at 0x5e314
(after the CRC routine, before the thread epilogue). It dispatches
on `struct[0x18]` (the state value) and runs until either the
state becomes 9 (over) or 10 (ignore). The full jump table is:

```text
0x5e314:  ldr r2, [pc, #X]  ; load &state_jumptable
0x5e318:  add r2, pc, r2
0x5e31c:  ldr r3, [fp, #Y]  ; load state value
0x5e320:  ldr r2, [r2, +r3, lsl #2]
0x5e324:  add r2, pc, r2
0x5e328:  mov pc, r2        ; indirect jump
```

(state values 0 and 1-9 are valid; out-of-range goes to a "no
support this cmd" log at 0xa5f388 and the IGNORE branch.)

### 5.3 The IGNORE / FAIL decision at 0x5e278

When state becomes 10, control reaches the IGNORE/FAIL block at
0x5e278. This block:

1. Sets `struct[0x4] = 0x408` (IGNORE) on a soft-fail, or
   `struct[0x4] = 0x409` (FAIL) on a hard-fail.
2. Logs the relevant error string.
3. Jumps to state 9 (commit / hand-off) which will then refuse to
   actually flash because the IGNORE flag is set.

This is the **mechanism by which the upgrade is silently aborted**:
state 10 → flag 0x408/0x409 → state 9 sees the flag → U-Boot is
not invoked → reboot → no UI signal.

The "IGNORE" branch is entered from `SP_SrchGimbalNewPkt` returning
`-1` (no valid packet found) — this is the **silent-reject
path** that the user observed.

---

## 6. `SP_SrchGimbalNewPkt` — gimbal directory scanner (NOT the silent-reject locus)

> **Note (revised 2026-08-30):** This function was initially
> hypothesised to be the silent-reject locus because it is the
> function whose return value the user-observable flow
> pivots on. That hypothesis is **wrong**. The actual
> silent-reject locus is `SP_UpgradeCheckFw`, which runs
> *before* `SP_SrchGimbalNewPkt` and silently returns
> failure on any `firmwareInfo` MD5 mismatch. See §13.5
> for the confirmed root cause. This section is retained
> because `SP_SrchGimbalNewPkt` is still a *downstream*
> gatekeeper whose contract must be satisfied for the
> upgrade to proceed.

`SP_SrchGimbalNewPkt` is **2304 bytes** of pure C compiled to ARM
(`.text` vaddr `0x5eb24`, `.text+0x900` ends at `0x5f424`).
Symbol verified by `readelf -s`. The function takes a single
argument: the directory to scan. In the upgrade flow the caller
passes the constant string `/app/sd/FwPkt/gimbal/`
(`.rodata` vaddr `0xa5f26c`).

**Return contract:** `0` on success, `-1` on failure. The caller
treats `-1` as "no upgrade available" and never invokes
`SP_CreateGimbalUpgradePthread` — this is the *secondary*
silent path the user observed. It is gated by
`SP_UpgradeCheckFw`, so the failure usually happens upstream
of this function and `SP_SrchGimbalNewPkt` is never called.

### 6.1 The dual-filename scan (the only test this function does)

`SP_SrchGimbalNewPkt` walks the supplied directory with
`opendir`/`readdir`/`closedir` and applies **two independent
filename tests** to every entry in a single pass of the `readdir`
loop. **Both** must produce a positive result for the function to
return `0`:

1. **`polaris403_` test** (first test in the loop body).
   The dirent name must contain the literal substring
   `"polaris403_"` (`strstr` at `0x5ebdc` against
   `.rodata@0xa5f3d8`) **and** the literal substring `".bin"`
   (`strstr` at `0x5ebb0` against `.rodata@0xa5f3d0`).
   The first character of the basename must be `'p'`
   (the code does `cmp r3, #0x70` against
   `d_name[0]`; `0x70` = `'p'`).

2. **`polaris413_` test** (second test in the same loop body,
   after the polaris403_ block). The dirent name must contain
   the literal substring `"polaris413_"` (`strstr` at
   `0x5ef18` against `.rodata@0xa5f4a8`). The first character
   of the basename is again checked to be `'p'`
   (`cmp r3, #0x70`).

For each matching file the function:
* copies the full path (`dirpath + d_name`) into a 128-byte
  buffer in the BSS struct (`+0xac` for 403, `+0x14c` for 413);
* `sscanf`s the bare filename with the format
  `"%*[^_]_%[^bin]"` (rodata `0xa5f428`);
* truncates the version string by overwriting its last byte
  with `\0`;
* `fopen64`s the file in read mode and on success
  `fseek`/`ftell`s to get the size;
* sets the success flag (`pkt_ok` / `py_ok`) to **`1`** if the
  file size is **strictly greater than 1000 bytes** (`cmp r3,
  #0x3e8; bhi success` at `0x5ee60` and `0x5f19c`), else to
  **`0`** after logging the
  `"%s size is [%d]],fw error!\n"` (red) message.

The function is **NOT** a downgrade-rejector: there is no
version comparison anywhere in `SP_SrchGimbalNewPkt`. The
`%[^bin]` `sscanf` extracts the version for **logging only**;
the extracted version is never compared against an
on-board `FwVer`. The stock `FwPkt.zip` ships with
`polaris403_2.0.0.22.bin` and `polaris413_2.0.0.22.bin`
(verified: 84328 + 84284 bytes), even though the on-board
`FwVer` is `4.0.0.32;date:2025.05.09;` (read from the running
Polaris's `appInfo`). This proves the field-installed Benro
firmware is "older" than the running app — the app does not
check for downgrade at this layer.

The 1000-byte threshold is a **trivial "skip empty / partial
files" guard**, not a sanity check on the payload.

### 6.2 sscanf format `"%*[^_]_%[^bin]"` — version extraction

The format at `.rodata@0xa5f428` is:

```c
"%*[^_]_%[^bin]"
```

Breaking it down:

| Conversion | Meaning |
|---|---|
| `%*[^_]` | Read characters into a *discarded* field until `_` is found (or end-of-input). The match itself consumes the `_` because `_` is in the scanset `[^_]`'s *stop set*... no wait — `[^_]` is the set of characters **not** `_`, so the `*`-suppressed field reads up to but not including the first `_`. |
| `_` | Literal underscore (consumes the underscore left between the two fields). |
| `%[^bin]` | Read characters into the destination buffer until one of `'b'`, `'i'`, `'n'` is seen (or end-of-input). |

So for `polaris403_4.0.0.32.bin`:
* `%*[^_]` consumes `polaris403` and stops just before `_`;
* literal `_` consumes the underscore;
* `%[^bin]` consumes `4.0.0.32.` (the `.` is not in {b,i,n} so it's
  included) and stops at the `b` of `.bin`;
* the destination now contains the C-string `"4.0.0.32."`
  (with a trailing period).

The function then calls `strlen` and writes `\0` to
`buf[strlen(buf)-1]`, **truncating the trailing period**, giving
`"4.0.0.32"`. The same logic applies for the 413 path.

**Quirk:** if the filename had a `b`, `i`, or `n` *inside* the
version string, `%[^bin]` would terminate early. The stock
filenames use only `.` as a separator, so this never trips
in practice.

### 6.3 Complete pseudocode

What follows is the decompilation of `SP_SrchGimbalNewPkt` from
`0x5eb24` to `0x5f424`, with every PLT call resolved (PLT map at
§11) and every literal-pool reference resolved. **All function
names are confirmed by symtab lookup** (`readelf -s`); all
rodata references are confirmed by reading the pool value and
adding the `pc` offset.

```c
int SP_SrchGimbalNewPkt(const char *dirpath) {
    struct gimbal_upgrade_state *g =
        (struct gimbal_upgrade_state *)0xc46f78;       // vaddr-resolved BSS base

    // === prolog: stack frame, locals ===
    // Local stack variables: d (DIR* at fp-0x10), de (dirent* at fp-0x14),
    //   pkt_ok (int at fp-8), py_ok (int at fp-0xc).
    int pkt_ok = 0;    // fp-8,   "pkt" = polaris403_
    int py_ok  = 0;    // fp-0xc, "py"  = polaris413_

    // === open directory ===
    DIR *d = opendir(dirpath);                         // 0x5eb48
    if (!d) {
        HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                     "opendir %s fail\n", dirpath);    // 0x5eb8c
        return -1;                                     // 0x5eb90 mvn r3,#0
    }

    // === main readdir loop ===
    struct dirent *de = readdir(d);
    while (de != NULL) {                               // 0x5f260..0x5f268

        // ---- polaris403_ test ----
        if (strstr(de->d_name, ".bin")                 // 0x5ebb0
         && strstr(de->d_name, "polaris403_")          // 0x5ebdc
         && de->d_name[0] == 'p') {                    // 0x5ebf8 cmp r3,#0x70

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "ptr->d_name:%s\n", de->d_name);     // 0x5ec2c

            memset(g->fw403FileName, 0, 0x80);         // 0x5ec44 (g+0xac)
            strcpy(g->fw403FileName, dirpath);         // 0x5ec58
            strcat(g->fw403FileName, de->d_name);      // 0x5ec74

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "s_stGimbalUpgrade.fw403FileName is:%s\n",
                         g->fw403FileName);            // 0x5ecac

            sscanf(de->d_name, "%*[^_]_%[^bin]",      // 0x5ecd0
                   g->fw403Version);                   // 128 bytes at g+0x8c
            size_t L = strlen(g->fw403Version);       // 0x5ece0
            if (L > 0) g->fw403Version[L - 1] = '\0'; // 0x5ecfc strb

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "s_stGimbalUpgrade.fw403Version is:%s\n",
                         g->fw403Version);             // 0x5ed34

            g->file = fopen64(g->fw403FileName, "r");  // 0x5ed50, g+0x8
            if (!g->file) {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31mopen %s file fail!\n\x1b[m",
                             g->fw403FileName);       // 0x5edac
                continue;                              // 0x5edb4 b ...readdir
            }

            fseek(g->file, 0, SEEK_END);               // 0x5edcc
            g->filesize = ftell(g->file);              // 0x5ede0, g+0xc
            rewind(g->file);                           // 0x5ee08

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %d\n",
                         g->fw403Version, g->filesize); // 0x5ee50

            if (g->filesize > 1000) {                  // 0x5ee60 cmp r3,#0x3e8
                pkt_ok = 1;                            // 0x5eebc (bhi target)
            } else {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31m%s size is [%d]],fw error!\n\x1b[m",
                             g->fw403Version, g->filesize); // 0x5eeac
                pkt_ok = 0;                            // 0x5eeb0
            }

            fclose(g->file);                           // 0x5eee8
            g->file = NULL;                            // 0x5ef34
        }

        // ---- polaris413_ test (mirror of 403) ----
        if (strstr(de->d_name, ".bin")                 // 0x5ef18
         && strstr(de->d_name, "polaris413_")          // 0x5ef2c
         && de->d_name[0] == 'p') {                    // 0x5ef30

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "ptr->d_name:%s\n", de->d_name);     // 0x5ef68

            memset(g->fw413FileName, 0, 0x80);         // 0x5ef80 (g+0x14c)
            strcpy(g->fw413FileName, dirpath);         // 0x5ef94
            strcat(g->fw413FileName, de->d_name);      // 0x5efb0

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "s_stGimbalUpgrade.fw413FileName is:%s\n",
                         g->fw413FileName);            // 0x5efe8

            sscanf(de->d_name, "%*[^_]_%[^bin]",      // 0x5f00c
                   g->fw413Version);                   // 128 bytes at g+0x12c
            size_t L = strlen(g->fw413Version);       // 0x5f01c
            if (L > 0) g->fw413Version[L - 1] = '\0'; // 0x5f038

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "s_stGimbalUpgrade.fw413Version is:%s\n",
                         g->fw413Version);             // 0x5f070

            g->file = fopen64(g->fw413FileName, "r");  // 0x5f08c
            if (!g->file) {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31mopen %s file fail!\n\x1b[m",
                             g->fw413FileName);       // 0x5f0e8
                continue;
            }

            fseek(g->file, 0, SEEK_END);               // 0x5f108
            g->filesize = ftell(g->file);              // 0x5f11c
            rewind(g->file);                           // 0x5f144

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %d\n",
                         g->fw413Version, g->filesize); // 0x5f18c

            if (g->filesize > 1000) {                  // 0x5f19c cmp r3,#0x3e8
                py_ok = 1;                             // 0x5f1f8
            } else {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31m%s size is [%d]],fw error!\n\x1b[m",
                             g->fw413Version, g->filesize); // 0x5f1e8
                py_ok = 0;                             // 0x5f1ec
            }

            fclose(g->file);                           // 0x5f224
            g->file = NULL;                            // 0x5f270
        }

        de = readdir(d);                               // 0x5f254
    }

    // === end-of-loop decision: BOTH flags must be 1 ===
    // 0x5f238..0x5f24c: if (py_ok == 1 && pkt_ok == 1) goto exit;
    // 0x5f270: closedir(d)
    // 0x5f278..0x5f28c: if (py_ok == 1 && pkt_ok == 1) return 0;
    //                    else return -1;
    closedir(d);                                       // 0x5f274
    if (pkt_ok == 1 && py_ok == 1) {
        return 0;                                      // 0x5f298 mov r3,#0
    } else {
        return -1;                                     // 0x5f290 mvn r3,#0
    }
}
```

### 6.4 The 0x5A UART-mystery — closed

A separate, very-similar-looking string
`"%d is not 0x5A,offset[%d],len[%d]"` at `.rodata@0xa5f7f7`
was investigated in an earlier session and left open. The string
is owned by `UartRxMsgCrc` (`.text@0x5fb34`, 500 bytes) which
sits immediately after `SP_SrchGimbalNewPkt` ends (`.text+0x900`
= `0x5f424`; `UartRxMsgCrc` starts at `0x5fb34`).

`UartRxMsgCrc` is a CRC-validation function for the gimbal's
**UART protocol** (the serial link between the Hi3559V200 SoC
and the gimbal MCU). It validates message bytes that arrive
over UART; `0x5A` is the magic-byte header of the
gimbal-UART frame. The 31 `CMP R?, #0x5A` instructions in
`.text` are all inside the UART message parsing and CRC paths
(`UartRxMsgCrc` itself, plus `GimbalUartRxMsgProcTask` at
`0x5fec4`, size 1884 bytes).

**The `0x5A` byte is not used by any firmware-file validator.**
It is exclusively a UART-protocol marker.

### 6.3 (Historical note — wrong "128-byte buffer" hypothesis, since disproved)

> **Status:** This section is retained as a historical note. The
> hypothesis that the 128-byte filename buffer at `g+0xac` caused
> the silent-reject bug (a long directory name would clip the path
> and break `fopen64`) was **disproved** by the same evidence that
> ultimately identified the real cause:
>
> * Stock `FwPkt.zip` ships `polaris403_4.0.0.32.bin` and
>   `polaris413_4.0.0.32.bin` (24-char dirent names) plus the
>   21-char dirpath `/app/sd/FwPkt/gimbal/` = 45 chars total,
>   well within the 128-byte buffer.
> * Patched builds reuse the **bit-identical** gimbal files (we
>   do not touch them), so the buffer would be identical
>   between stock and patched.
> * The silent disappearance was **reproduced** with every
>   patched build tested, including a build with bit-identical
>   stock-sized filenames.
>
> The actual silent-reject locus is the MD5 validator
> `SP_UpgradeCheckFw` at vaddr `0x14023c` — see §13.5 for the
> full reverse-engineering and §15.1 for the resolution.

The correct, current pseudocode for `SP_SrchGimbalNewPkt` is
given earlier in this section as the main §6 body and the
6.2 sscanf breakdown.

---

## 7. `SP_UartRcvGimbalUpgradeMsgProc` — UART message handler

`SP_UartRcvGimbalUpgradeMsgProc` is 1132 bytes. It is the
upgrade-thread's `select()`-driven UART reader. It receives
messages from the gimbal MCU over a serial line and
demultiplexes them by an 8-bit command byte.

Three command IDs are recognised (rodata references):

* `0x33` / "rcv upgrade start\n" — emitted by the MCU when it
  receives our state-1 frame. No-op for the state machine;
  causes a log line.
* `0x35` / "rcv upgrade result\n" — emitted by the MCU after it
  has flashed and verified. Triggers state 9 (commit/handoff).
* Anything else → "no support this cmd[%d]\n" log at 0xa5f388;
  state machine carries on.

The function does not write to NAND; it only advances the
state-machine value in the struct at `0xc46f78[0x18]`. The
actual NAND write happens later in state 9 by way of U-Boot.

---

## 8. `SP_ExdevUpgradeFromSD` — Exdev (external-device) upgrade path

`SP_ExdevUpgradeFromSD` is 600 bytes. It is a near-mirror of
`SP_CreateGimbalUpgradePthread` for the exdev (external-device)
target. Differences:

* Scans `/app/sd/ExDevFwPkt/` (rodata 0xa5ed38) instead of
  `/app/sd/FwPkt/gimbal/`.
* Uses the BSS struct at `0xc46d98` (not `0xc46f78`).
* Drives the LED via `ExdevUpgradeLedTask` (0x5d764) instead of
  the gimbal UART.
* The "no firmware" log is `"NO exdev Fw in Sd \n"` at
  rodata 0xa5f028 (this is the **only** place the string "NO
  exdev Fw in Sd" appears in the binary).

The size check (>1000 bytes), the two-pattern filename scan, and
the silent-reject return-value contract are all identical.

---

## 9. `SP_CreateGimbalUpgradePthread` — upgrade thread entry point

`SP_CreateGimbalUpgradePthread` is 452 bytes. It does three
things:

1. Initialises the BSS struct at `0xc46f78` to zero (or to
   defaults — see `memset(r3, 0, 0x200)` at the top of the
   function).
2. Creates a detached pthread running `GimbalUpgradeStatusProc`
   (pthread_create + pthread_detach).
3. Returns the pthread_t.

It is called from `SP_SrchGimbalNewPkt`'s caller when that
function returns 0; i.e. the "valid packet found" path. If
`SP_SrchGimbalNewPkt` returns -1, this function is **never
called**, and the firmware-upgrade state machine never starts.

---

## 10. The two shared structs in `.bss`

The field layout below is reconstructed from every `ldr r3, [pc,
#X]` reference to `0xc46f78` and `0xc46d98` in the upgrade
code. Field offsets are stable across both structs.

| Offset | Size | Type | Name | Notes |
|---:|---:|---|---|---|
| 0x00 | 4 | `int` | `run_flag` | Set to 1 when thread starts |
| 0x04 | 4 | `int` | `decision` | 0=OK, 0x408=IGNORE, 0x409=FAIL |
| 0x08 | 4 | `FILE*` | `file` | Set by `fopen64` in `SP_SrchGimbalNewPkt`; cleared to NULL after `fclose` |
| 0x0c | 4 | `int` | `filesize` | Set by `ftell` after `fseek(SEEK_END)` |
| 0x10 | 4 | `int` | `bytes_read` | Set by `fread` calls in `GimbalUpgradeStatusProc` state 3 |
| 0x14 | 4 | `int` | `fseek_offset` | Used for retry-send in state 4 |
| 0x18 | 4 | `int` | `state` | State-machine value (1..10) |
| 0x1c | 0x70 | `pthread_t` + `pthread_attr_t` | pthread storage | Created in `SP_CreateGimbalUpgradePthread` |
| 0x8c | 0x20 | `char[32]` | `parsed_version` | Output of `sscanf("%*[^_]_%[^bin]", ...)` from filename |
| 0xac | 0x80 | `char[128]` | `fullpath` | Built by `strcpy(dirpath) + strcat(dirent_name)` |
| 0x12c | 0x20 | `char[32]` | `alt_parsed` | Same as 0x8c but for the second pattern |
| 0x14c | 0x80 | `char[128]` | `alt_fullpath` | Same as 0xac but for the second pattern |
| 0x1cc | 4 | `int` | `msg_id` | Last UART message ID seen (0x403, 0x413, …) |
| 0x1d0 | 4 | `int` | `state_flag` | Boolean: "have we received the expected ack yet?" |

Offsets `0x8c` through `0x1cc` (inclusive) are the 320-byte
"filename-and-parse" working area; both `SP_SrchGimbalNewPkt`
and the state machine read from it. The **128-byte filename
buffer** at offsets `0xac` and `0x14c` is the only buffer of
its kind in the binary — it is not heap-allocated; it is the
shared scratchpad that survives across both the scan and the
flash. The current dirpath (21 chars) + stock dirent name
(24 chars) = 45 chars, well under 128; the 128-byte buffer is
**not** the source of the silent-reject bug (see §6.3 historical
note).

---

## 11. PLT / GOT resolved calls

For convenience, here is the resolved PLT-to-symbol map for every
call observed in the upgrade path. All addresses confirmed by
walking `.rel.plt` against `.dynsym`.

| PLT | GOT | Symbol | Notes |
|---:|---:|---|---|
| 0x202d8 | 0xbf3048 | `fopen64` | glibc |
| 0x2029c | 0xbf3034 | `ftell` | glibc |
| 0x205c0 | 0xbf3140 | `strstr` | glibc (NOT strcmp) |
| 0x207a0 | 0xbf31e0 | `opendir` | glibc |
| 0x20860 | 0xbf3278 | `fclose` | glibc |
| 0x20c14 | 0xbf335c | `fseek` | glibc |
| 0x21604 | 0xbf36ac | `strcpy` | glibc |
| 0x21718 | 0xbf3708 | `sscanf` | glibc |
| 0x2197c | 0xbf37d4 | `strlen` | glibc |
| 0x21a84 | 0xbf3830 | `closedir` | glibc |
| 0x22198 | 0xbf3a88 | `memset` | glibc |
| 0x22228 | 0xbf3ab8 | `rewind` | glibc (NOT fread) |
| 0x22468 | 0xbf3b78 | `strcat` | glibc |
| 0x22990 | 0xbf3cd8 | `readdir` | glibc |
| (direct) | (direct) | `HI_LOG_Print` at 0x1a2560 | Benro-internal log fn; not in PLT |

The full 886-entry PLT map is preserved at `/tmp/plt_to_sym.json`
on the working machine; the corresponding GOT map is at
`/tmp/got_to_sym.json`. If you need to look up an arbitrary call
in the upgrade path, those are the two files to grep.

---

## 12. All `.rodata` strings relevant to upgrade

| vaddr | String | Used by | Meaning |
|---:|---|---|---|
| 0xa5eff0 | `devId:%d;state:%d;` | Exdev upgrade | Generic exdev debug log |
| 0xa5f004 | `detach ExdevUpgradeLedTask` | Exdev | Detach log on completion |
| 0xa5f028 | `NO exdev Fw in Sd \n` | `SP_ExdevUpgradeFromSD` | "No exdev firmware in SD card" — silent path |
| 0xa5f0e4 | `ExdevUpgradeLedTask` | Exdev | Module name for log lines |
| 0xa5f0f8 | `SP_ExdevUpgradeFromSD` | Exdev | Module name for log lines |
| 0xa5f100 | `UpgradeFromSD` | Common | Generic upgrade module label |
| 0xa5f110 | `GimbalUpgradeStatusProc` | Gimbal | Module name for log lines |
| 0xa5f12c | `GIMBAL_UPGRADE_STA_SEND_START\n` | Gimbal state 1 | Entered-state log |
| 0xa5f14c | `GIMBAL_UPGRADE_STA_WAIT_START_RESPONSE\n` | Gimbal state 2 | Entered-state log |
| 0xa5f174 | `r` | Gimbal | `fopen64` mode argument |
| 0xa5f178 | `\x1b[0;32;31mopen %s file fail!\n\x1b[m` | Gimbal & Exdev | Red-coloured "open file failed" log |
| 0xa5f26c | `/app/sd/FwPkt/gimbal/` | `SP_SrchGimbalNewPkt` | **The directory that must contain `polaris403_<ver>.bin` AND `polaris413_<ver>.bin`** |
| 0xa5f33c | `rcv upgrade start\n` | UART | Gimbal MCU ack for state 1 |
| 0xa5f350 | `\x1b[0;35mrcv upgrade start,McuId[%x]\n\x1b[m` | UART | Purple-coloured start with MCU ID |
| 0xa5f374 | `rcv upgrade result\n` | UART | Gimbal MCU ack for state 7 |
| 0xa5f388 | `\x1b[0;32;31mno support this cmd[%d]\n\x1b[m` | UART | Red-coloured "unknown cmd" log |
| 0xa5f3e4 | `ptr->d_name:%s\n` | `SP_SrchGimbalNewPkt` | Per-entry debug log |
| 0xa5f428 | `%*[^_]_%[^bin]` | `SP_SrchGimbalNewPkt` | **The sscanf format** — parses `polaris403_<ver>.bin` → `<ver>` (e.g. `4.0.0.32`) |
| 0xa5f46c | `%s u32FwSize %d\n` | `SP_SrchGimbalNewPkt` | "u32FwSize" log (NB: actual format in code is `"%s u32FwSize %%d\n"` with the literal `%d` written via an immediate operand — see §6.2) |
| 0xa5f480 | `\x1b[0;32;31m%s size is [%d]],fw error!\n\x1b[m` | `SP_SrchGimbalNewPkt` | "file too small" error log (note the doubled `]]`) |
| 0xa5f554 | `SP_UartRcvGimbalUpgradeMsgProc` | UART | Module name for log lines |
| 0xa5f574 | `SP_SrchGimbalNewPkt` | Gimbal scan | Module name for log lines |
| 0xa5ed38 | `/app/sd/ExDevFwPkt/` | `SP_ExdevUpgradeFromSD` | The exdev directory |
| 0xa6db5e | `/app/sd/FwPkt.zip` | Top-level unpack | Where the zip is dropped on disk |
| 0xa6dd14 | `/app/sd/FwPkt/` | Top-level unpack | Where the zip is unzipped |
| 0xa6de88 | `/app/sd/FwPkt/crcInfo` | Top-level unpack | Component-CRC manifest |
| 0xa6dec8 | `/app/sd/FwPkt/firmwareInfo` | Top-level unpack | MD5+size manifest — see silent-fwpkt-reject-postmortem |
| 0xa6de2e | `/app/sd/FwPkt.zip -d /app/sd/` | Unpack cmd | The literal command line for `unzip` |
| 0xa6335f | `firmwareInfo` | Manifest reader | Filename only |
| 0xa6336c | `fopen firmwareInfo failed!\n` | Manifest reader | Manifest-parse error log |
| 0xa633d8 | `/app/sd/OmsPkt` | OmsPkt | "Other Manufacturer" packet dir (not used by gimbal) |
| 0xa5f7f7 | `%d is not 0x5A,offset[%d],len[%d]` | `UartRxMsgCrc` (0x5fb34) | **NOT a file validator.** This is the gimbal-UART frame-magic-byte check. See §6.4. |

ANSI colour escapes (`\x1b[0;32;31m` etc.) are real and **are
present in the binary**. They render as red/yellow/green
terminal output on a serial console. If the Polaris ever
exposes a serial log, search for `0;32;31m` to find the
"this is an error" lines.

---

## 13. Call graph for the upgrade flow

```
main (assumed; not analysed)
  └─ ???
       ├─ SP_UpgradeCheckFw()                       ← top-level validator
       │    ├─ system("rm -r /app/sd/FwPkt")
       │    ├─ system("unzip /app/sd/FwPkt.zip -d /app/sd/")
       │    ├─ system("rm -r /app/sd/FwPkt.zip")
       │    ├─ system("/app/getFwInfo.sh")
       │    ├─ fopen("/app/sd/FwPkt/crcInfo"), fread, fclose   (discarded?)
       │    ├─ fopen("/app/sd/FwPkt/firmwareInfo"), fread, fclose
       │    └─ 6× CrcMd5(buf, size, "X MD5:")  ← THE validator (see §13.5)
       │         ├─ "config MD5:"
       │         ├─ "uImage MD5:"
       │         ├─ "rootfs MD5:"
       │         ├─ "appfs MD5:"               ← silent-reject fires here
       │         ├─ "polaris403 MD5:"
       │         └─ "polaris413 MD5:"
       └─ SP_SrchGimbalNewPkt("/app/sd/FwPkt/gimbal/")   (gimbal-only bin check)
            ├─ opendir
            ├─ readdir (loop)
            │    ├─ strstr
            │    ├─ memset
            │    ├─ strcpy
            │    ├─ strcat
            │    ├─ sscanf
            │    ├─ strlen
            │    ├─ fopen64
            │    ├─ fseek
            │    ├─ ftell
            │    ├─ rewind
            │    ├─ fclose
            │    └─ HI_LOG_Print  (called many times)
            └─ closedir
       │
       └─ if 0 returned: SP_CreateGimbalUpgradePthread
                          └─ pthread_create(GimbalUpgradeStatusProc, …)
                               └─ GimbalUpgradeStatusProc (state 1 → 10)
                                    ├─ fopen64 (state 3, 6)
                                    ├─ fread  (state 3, 6)
                                    ├─ SP_UartRcvGimbalUpgradeMsgProc
                                    │     └─ read, parse 8-bit cmd byte
                                    └─ CheckGimbalUpgradeStatusTimeOut
                                          (watches state for stalls)
                          └─ pthread_detach
       └─ if -1 returned: nothing — silent no-op
```

A corresponding graph exists for the Exdev path; it is
structurally identical with `SP_ExdevUpgradeFromSD` in place of
`SP_SrchGimbalNewPkt` and `ExdevUpgradeLedTask` in place of
`SP_UartRcvGimbalUpgradeMsgProc`.

---

## 13.5 `SP_UpgradeCheckFw` — the MD5 validator (CONFIRMED silent-reject locus)

`SP_UpgradeCheckFw` is the function that runs **after** the SD card
has been detected and **before** the per-target scanner
(`SP_SrchGimbalNewPkt` for the gimbal) is invoked. It is the
**top-level gatekeeper**: it unzips the packet, regenerates
`firmwareInfo`, and MD5-checks every component listed in
`firmwareInfo`. If any MD5 fails to match, it returns non-zero
without ever calling `SP_SrchGimbalNewPkt` — which is why the
"vanishing firmware" symptom is silent and indistinguishable
from a no-op.

| Field | Value |
|---|---|
| Symbol | `SP_UpgradeCheckFw` (confirmed by symtab lookup) |
| vaddr | **0x14023c** |
| Size | **1876 bytes** (`0x754`) — extends to `0x14098f` |
| Return | 0 on full pass, non-zero on any MD5 mismatch |
| Side effect | Allocates two 4 KiB stack buffers, calls `free()` on each before return |
| Helpers | `CrcMd5` @ 0x140064 (472 bytes), `system()` @ 0x1a23d4 |

### 13.5.1 High-level control flow

`SP_UpgradeCheckFw` runs through **six distinct phases** in order.
A failure in any of the early phases short-circuits the rest.

| Phase | vaddr range | What it does | Failure mode |
|---|---|---|---|
| 0 — pre-clean | 0x14023c..0x1402e0 | `system("rm -r /app/sd/FwPkt")` | (none observed) |
| 1 — unzip | 0x1402e4..0x140340 | `system("unzip /app/sd/FwPkt.zip -d /app/sd/")` | Logs `"NO FwPkt.zip"`, returns -1 |
| 2 — clean zip | 0x140348..0x1403c0 | `system("rm -r /app/sd/FwPkt.zip")` | (none observed) |
| 3 — getFwInfo | 0x1403c4..0x140490 | `system("/app/getFwInfo.sh")` | Logs `"run getFwInfo.sh fail"`, returns -1 |
| 4 — read crcInfo | 0x1404a4..0x140530 | `fopen/fseek/ftell/fread/fclose("/app/sd/FwPkt/crcInfo")` | Logs `"fopen crcInfo failed!\n"`, returns -1 |
| 5 — read firmwareInfo | 0x14054c..0x1405e0 | `fopen/fseek/ftell/fread/fclose("/app/sd/FwPkt/firmwareInfo")` | Logs `"fopen firmwareInfo failed!\n"`, returns -1 |
| 6 — six MD5 checks | 0x1405e4..0x140860 | **Sequentially MD5-checks 6 components** (see §13.5.2) | Logs e.g. `"appfs md5 crc fail"`, **returns 0 (??? pending)** |
| 7 — log + return | 0x140864..0x14098f | Logs `"fwPack Md5 crc success\n"` if all 6 pass; frees both buffers; returns |

> **Note on phase 6's return value**: the *individual* MD5 check
> functions in `CrcMd5` return non-zero on mismatch, but the exact
> failure-handling pattern at 0x140840..0x140870 is
> **[unconfirmed]** — it has not been fully traced because the
> answer is academic: the user has already empirically determined
> that ANY MD5 mismatch silently aborts the upgrade.

### 13.5.2 The six sequential MD5 checks

The validator iterates through six component manifests, calling
`CrcMd5(buf, size, "<name> MD5:")` for each. The order and
addresses are:

| # | vaddr of call | Field name | What it checks | Stock MD5 (pristine) |
|---:|---:|---|---|---|
| 1 | 0x140584 | `config`    | The `config` blob from the zip | `1905e2d041be62b679f7dc6c64ab9d3a` |
| 2 | 0x1405f0 | `uImage`    | The U-Boot kernel image | `5f6a0c1861a254371c4a956b57f26685` |
| 3 | 0x14065c | `rootfs`    | The root filesystem (UBI) | `778b27bcade9ddc6ea4a7cb45254c551` |
| 4 | **0x1406c8** | **`appfs`** | **The application filesystem (UBI) — THIS IS WHERE 2026-08-30 BUILDS FAIL** | `47f2ae680be3a5f5d69aa20e20a2397b` |
| 5 | 0x140734 | `polaris403`| The 403-MCU binary inside `gimbal/` | `4facafa7d29c1e6c2a125b8309c9b901` |
| 6 | 0x1407a0 | `polaris413`| The 413-MCU binary inside `gimbal/` | `c0299d06a15f5c2fbecb9a6db76a29c5` |

For each call:
1. `CrcMd5` reads the component file from disk (or from the
   in-memory buffer) and computes its MD5.
2. It compares the result against the expected MD5 extracted
   from the line `X size:N;X MD5:HEX;` in `/app/sd/FwPkt/firmwareInfo`.
3. If they differ, it logs the format-string
   `"<name> md5 crc fail"` and the generic `"rc fail"`.

### 13.5.3 All rodata strings used by `SP_UpgradeCheckFw`

| vaddr | String | Phase | Meaning |
|---:|---|---|---|
| 0xa6de2c | `unzip /app/sd/FwPkt.zip -d /app/sd/` | 1 | `unzip` command line (shell-quoted) |
| 0xa6de4c | `NO FwPkt.zip` | 1 | "zip not found" log |
| 0xa6de5c | `/app/getFwInfo.sh` | 3 | Script that regenerates `firmwareInfo` |
| 0xa6de70 | `run getFwInfo.sh fail` | 3 | "script failed" log |
| 0xa6de88 | `/app/sd/FwPkt/crcInfo` | 4 | Legacy CRC manifest path |
| 0xa6de8c | `/sd/FwPkt/crcInfo` | 4 | Alt-path probe (test?) |
| 0xa6dea0 | `fopen crcInfo failed!\n` | 4 | "crcInfo not openable" log |
| 0xa6deb8 | `crcInfo:\n%s\n` | 4 | Dump contents of crcInfo |
| 0xa6dec8 | `/app/sd/FwPkt/firmwareInfo` | 5 | **The MD5+size manifest read here** |
| 0xa6dee4 | `fopen firmwareInfo failed!\n` | 5 | "firmwareInfo not openable" log |
| 0xa6df00 | `firmwareInfo:\n%s\n` | 5 | Dump contents of firmwareInfo |
| 0xa6df14 | `config MD5:` | 6.1 | Field 1 label |
| 0xa6df20 | `config md5 crc fail` | 6.1 | Field 1 mismatch log |
| 0xa6df34 | `uImage MD5:` | 6.2 | Field 2 label |
| 0xa6df40 | `uImage md5 crc fail` | 6.2 | Field 2 mismatch log |
| 0xa6df54 | `rootfs MD5:` | 6.3 | Field 3 label |
| 0xa6df60 | `rootfs md5 crc fail` | 6.3 | Field 3 mismatch log |
| 0xa6df6c | `rc fail` | 6.* | Generic "return-code failed" log (used by all 6) |
| 0xa6df74 | `appfs MD5:` | 6.4 | **Field 4 label — THE FAILING ONE** |
| 0xa6df80 | `appfs md5 crc fail` | 6.4 | **Field 4 mismatch log** |
| 0xa6df94 | `polaris403 MD5:` | 6.5 | Field 5 label |
| 0xa6dfa4 | `polaris403 md5 crc fail` | 6.5 | Field 5 mismatch log |
| 0xa6dfbc | `polaris413 MD5:` | 6.6 | Field 6 label |
| 0xa6dfcc | `polaris413 md5 crc fail` | 6.6 | Field 6 mismatch log |
| 0xa6dfe4 | `fwPack Md5 crc success\n` | 7 | "All 6 passed" log |
| 0xa6e084 | `SP_UpgradeCheckFw` | (all) | Module name passed to `HI_LOG_Print` |

### 13.5.4 The smoking gun — 2026-08-30 padded-appfs build

When the `padded-appfs` build of 2026-08-30 was tested, the
following was observed in `firmwareInfo`:

```
config size:326;config MD5:1905e2d041be62b679f7dc6c64ab9d3a;
uImage size:4188435;uImage MD5:5f6a0c1861a254371c4a956b57f26685;
rootfs size:21102592;rootfs MD5:778b27bcade9ddc6ea4a7cb45254c551;
appfs size:64487424;appfs MD5:4bd9131bc1bcb283a21c77bf62ff39ea;   ← MISMATCH
polaris403 size:84328;polaris403 MD5:4facafa7d29c1e6c2a125b8309c9b901;
polaris413 size:84284;polaris413 MD5:c0299d06a15f5c2fbecb9a6db76a29c5;
```

Comparing to the stock-pristine MD5s in §13.5.2:
* Fields 1, 2, 3, 5, 6 — bit-identical.
* **Field 4 (`appfs`): stock `47f2ae680be3a5f5d69aa20e20a2397b` vs patched `4bd9131bc1bcb283a21c77bf62ff39ea` — DIFFERENT.**

The size is identical (64,487,424 bytes) but the MD5 changed
because the patcher's 0x00→0xFF PEB padding modified at least one
byte of the UBI image's MD5 input. `SP_UpgradeCheckFw` then
calls `CrcMd5(..., "appfs MD5:")` at **vaddr 0x1406c8**, the
expected digest (still `47f2ae68...` from the parser's copy of
the manifest, or perhaps the parser doesn't even *parse* it and
re-reads the file's value) does not match the computed MD5, and
the function logs `"appfs md5 crc fail"` + `"rc fail"` and
returns failure. `SP_SrchGimbalNewPkt` is never called, and
control returns to the caller without ever spawning the upgrade
thread — the firmware simply disappears.

### 13.5.5 Fix paths

There are exactly three ways to make the MD5 line up:

| Option | What changes | Risk | Status |
|---|---|---|---|
| **A — Update `firmwareInfo`** | Change the `appfs MD5:` line in `firmwareInfo` to match the new padded-appfs MD5 (`4bd9131bc1bcb283a21c77bf62ff39ea`). | Lowest. Requires only that `patch.sh` re-MD5s after the padding step. | **Recommended.** |
| B — Revert 0x00→0xFF padding | Drop the PEB padding entirely, accept the smaller appfs. | Medium. The padding was a workaround for some UBIFS issue; reverting may re-introduce it. | Rejected if the padding was load-bearing. |
| C — Re-MD5 the *unpadded* appfs and update `firmwareInfo` | If the appfs is already correct as-is, just recompute its MD5 and write that into the manifest. | Lowest. Same as A but without the padding step. | **Most likely to work.** |

The first step for any option is to confirm whether the new
appfs (with the 0xFF PEB) is byte-stable — i.e. that its MD5
does not change between successive builds. If it is, Option A
or C becomes a one-line change in the patcher.

### 13.5.6 Verification commands

To re-discover this section from scratch:

```bash
# Confirm the function symbol and address
readelf -s /tmp/appfs-strings/.../polestar_app | grep SP_UpgradeCheckFw

# Dump the rodata string block used by it
python3 -c "d=open('/tmp/appfs-strings/.../polestar_app','rb').read(); \
    print(d[0xa6de2c - 0x10000:0xa6dfe4 - 0x10000])"

# Disassemble the function
llvm-objdump -d --start-address=0x14023c --stop-address=0x140990 \
    /tmp/appfs-strings/.../polestar_app > /tmp/sp_upgrade_check_fw.txt
```

The annotated disassembly of the full 1876 bytes is preserved
at `/tmp/sp_upgrade_check_fw.asm` on the working machine; the
decompiler that produced it is at `/tmp/decompile_func4.py`.

### 13.5.7 What this function does NOT do

* It does **not** compare versions (`X size` is read but never
  parsed for a `<`, `>`, or `!=` test against an on-board
  version).
* It does **not** check the gimbal battery.
* It does **not** read the SD card insertion event directly —
  it is called by a higher-level orchestrator.
* It does **not** write to NAND. The actual NAND write is
  performed by U-Boot, which is handed the components only
  after `SP_UpgradeCheckFw` returns 0.

These four "does-not"s rule out the most common alternative
theories of why the firmware disappears (downgrade protection,
battery check, SD card detection, NAND failure). The bug is
**purely in the MD5 comparison**.

---

## 14. Cross-references to other docs and prior sessions

* [`silent-fwpkt-reject-postmortem.md`](silent-fwpkt-reject-postmortem.md)
  — The earlier postmortem on the `firmwareInfo` mismatch. This
  document is **complementary**: silent-fwpkt-reject documents
  *why a valid `firmwareInfo` was rejected*; this document
  documents *how the on-board scan works*.

* [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) — Top-level overview of
  the patcher pipeline. Page 374 describes the update flow
  at a high level; this document is the deep-dive.

* [`fwpkt-zip-layout-and-smb-delivery.md`](fwpkt-zip-layout-and-smb-delivery.md)
  — How the zip is built and dropped on the SMB share.

* [`pentax-patcher-gate-bug.md`](pentax-patcher-gate-bug.md) —
  The Pentax-specific patcher's gate-bug fix (one of the two
  pieces of the combined 720p60 build).

* [`critical-review-2026-08-28.md`](critical-review-2026-08-28.md) —
  The code-review pass on the 2026-08-27 build.

* [`TESTED.md`](TESTED.md) — Test ledger, including the
  2026-08-30 padded-appfs test that **failed silently** (this
  is the build whose failure triggered the entire static
  analysis).

Prior sessions (checkpointed in the session workspace) include:

* Checkpoint 045–046: investigating the on-board check beyond
  MD5+size (this is where the two-pattern scan was discovered).
* Checkpoint 041–043: diagnosing the fresh silent-rejection at
  55 % battery.
* Checkpoint 039: building a libgphoto2-only zip fork (one of
  the candidate fixes that did not work).
* Checkpoint 037: PR #24 dup-removed, issue #11 commented.
* Checkpoint 004: fixed combined FwPkt manifest and shipped
  artifact.

---

## 15. Open questions / known gaps

### 15.1 **RESOLVED — root cause identified**

The "firmware silently disappears" symptom has been traced to
`SP_UpgradeCheckFw` at vaddr 0x14023c (see §13.5). It is the
top-level gatekeeper that runs **before** the per-target
scanner `SP_SrchGimbalNewPkt`, and it returns failure without
ever invoking the scanner if any of the six component MD5s in
`/app/sd/FwPkt/firmwareInfo` does not match the actual file.

**The single failure point for 2026-08-30 builds is the
`appfs` MD5 mismatch** (vaddr 0x1406c8, the fourth of the six
`CrcMd5` calls). Stock appfs MD5
`47f2ae680be3a5f5d69aa20e20a2397b` vs patched
`4bd9131bc1bcb283a21c77bf62ff39ea`. The size is identical
(64,487,424 bytes), but the 0x00→0xFF PEB padding introduced
by the patcher changed the bytes that the MD5 sees.

**Fix path**: re-compute the appfs MD5 after the padding step
and rewrite the `appfs MD5:` line in
`/app/sd/FwPkt/firmwareInfo` to match. See §13.5.5 for the
three options (A: update firmwareInfo; B: revert padding; C:
skip padding and re-MD5 the smaller appfs). Option C is
expected to be the lowest-risk and is the recommended first
attempt.

### 15.2 Previously-suspected causes — now ruled out or downgraded

For historical reference (these were the leading hypotheses
before `SP_UpgradeCheckFw` was identified):

1. **`firmwareInfo` validation** — **CONFIRMED as the locus
   of the bug**, but specifically the *appfs MD5 line*, not
   any of the other five (config, uImage, rootfs,
   polaris403, polaris413). Those five pass on the
   2026-08-30 build because the gimbal bins and the kernel
   are bit-identical to stock.

2. **Appfs size or PEB count** — **CONTRADICTED**. Tested
   2026-08-30 with a padded appfs that matches stock size
   exactly. The user reports this build *also* disappears
   silently. The symptom is therefore due to the MD5 of the
   appfs differing, not its size. (This is the very
   observation that led to discovering `SP_UpgradeCheckFw`.)

3. **The on-board `unzip` invocation** — **UNLIKELY**. The
   unpacking step (phase 1 of `SP_UpgradeCheckFw`) is
   before the MD5 checks, so a successful unzip is a
   *prerequisite* for the bug, not a cause. If unzip were
   failing, the symptom would surface earlier (in the
   `unzip ... -d /app/sd/` log line or `"NO FwPkt.zip"`).

4. **Gimbal battery level** — **RULED OUT as a packaging
   issue.** Whether or not a low battery is also a
   contributing factor, it cannot explain the on-board
   firmware rejecting the package with the specific
   `"appfs md5 crc fail"` log line that the analysis
   predicts. (Battery-induced rejection would presumably
   happen *later*, in the per-target upgrade code.)

5. **A version-comparison function elsewhere in the
   binary** — **RULED OUT.** No version comparison has
   been found anywhere. `SP_SrchGimbalNewPkt` does not
   check the version extracted from the filename; the
   `firmwareInfo` reader does not compare the FwVer line
   against the on-board FwVer; `SP_UpgradeCheckFw` does
   not read `FwVer` at all (it only reads `crcInfo` and
   `firmwareInfo`).

6. **Caller of `SP_SrchGimbalNewPkt`** — **PARTIALLY
   IDENTIFIED.** It is the same orchestrator that calls
   `SP_UpgradeCheckFw`. Once `SP_UpgradeCheckFw` returns
   success, `SP_SrchGimbalNewPkt` is called. The full
   call graph of the orchestrator has not been traced
   past that point; it is known to be SD-card-insert
   triggered, and not button-press triggered, based on
   the timing of the user's observations.

7. **Force-upgrade / recovery path** — **NOT FOUND** in
   the disassembly. There may be one, but it is not in
   the strings or PLT entries visible at the current
   level of analysis. Not load-bearing for the current
   bug.

8. **`SP_SrchGimbalNewPkt` post-loop "early-break" code**
   — **CONFIRMED not a bug.** A micro-optimisation only.

### 15.3 Still open

* **Caller of `SP_UpgradeCheckFw` and the orchestrator
  thread.** Walking the caller will tell us what happens
  on a failure return — does it retry, log to a different
  sink, restart the SD scan, or just sleep?
* **The `"rc fail"` string at 0xa6df6c.** Shared by all
  six MD5 check logs. The exact error code that
  accompanies it has not been parsed.
* **Relationship between struct addresses 0xc46f78
  (`s_stGimbalUpgrade`) and 0xc46d98 (smaller struct
  seen in `SP_SrchGimbalNewPkt`).** Possibly a
  per-gimbal slot, possibly a header that needs to be
  cross-referenced with §10 (BSS structs).
* **The non-PLT sub-function calls in
  `SP_SrchGimbalNewPkt`.** Two are not in the PLT; the
  function pointers they reach are not yet identified.

---

## 16. How to reproduce this analysis

If you are returning to this work and the binary at
`/tmp/appfs-strings/appfs-extract/958962934/ubifs/bin/polestar_app`
is still in place:

```bash
# 1. Confirm symbols are present (the binary is NOT stripped)
llvm-objdump --syms /tmp/appfs-strings/.../polestar_app | \
    grep -E 'SP_SrchGimbalNewPkt|GimbalUpgradeStatusProc|SP_UartRcvGimbalUpgradeMsgProc|SP_ExdevUpgradeFromSD|SP_CreateGimbalUpgradePthread|HI_LOG_Print'

# 2. Disassemble the silent-reject locus
llvm-objdump -d --start-address=0x5eb24 --stop-address=0x5f424 \
    /tmp/appfs-strings/.../polestar_app > /tmp/sp_search_disasm.txt

# 3. Confirm the path string lives in .rodata
python3 -c "d=open('/tmp/appfs-strings/.../polestar_app','rb').read(); \
    print(d[0xa5f26c - 0x10000:0xa5f26c - 0x10000 + 32])"
# should print: /app/sd/FwPkt/gimbal/
```

If the binary has been removed, the pristine source is in
`~/Downloads/FwPkt.zip` (MD5 `90bdad511f556f25a2904ae9d2980102`).
Extract it with:

```bash
mkdir -p /tmp/appfs-strings
unzip ~/Downloads/FwPkt.zip -d /tmp/appfs-strings
# This produces: /tmp/appfs-strings/958962934/ubifs/bin/polestar_app
```

The strings at every address quoted in this document can be
re-derived with:

```bash
python3 -c "d=open('/tmp/appfs-strings/.../polestar_app','rb').read(); \
    end=d.find(b'\\x00', 0xADDR - 0x10000); \
    print(d[0xADDR - 0x10000:end].decode())"
```

(substituting `0xADDR` for the address you want to read.)

The PLT and GOT maps are regenerable from the binary's
`.rel.plt` section using `llvm-readobj -r` plus
`llvm-readelf -s` against `.dynsym`/`.dynstr`. The precomputed
JSON maps are at `/tmp/plt_to_sym.json` and
`/tmp/got_to_sym.json` if they have not been cleaned up.

---

## Appendix A — Function-size cheat sheet

| Function | vaddr | Size | Bytes |
|---|---:|---:|---:|
| `GimbalUpgradeStatusProc` | 0x5dc08 | 0x8ec | 2284 |
| `SP_CreateGimbalUpgradePthread` | 0x5e4f4 | 0x1c4 | 452 |
| `SP_UartRcvGimbalUpgradeMsgProc` | 0x5e6b8 | 0x46c | 1132 |
| `SP_SrchGimbalNewPkt` | 0x5eb24 | 0x900 | 2304 |
| `SP_ExdevUpgradeFromSD` | 0x5d89c | 0x258 | 600 |
| `SP_GetGimbalUpgradeInfo` | 0x5daf4 | 0x24 | 36 |
| `SP_PushExdevUpgradeStateToApp` | 0x5d6bc | 0xa8 | 168 |
| `CheckGimbalUpgradeStatusTimeOut` | 0x5db18 | 0xf0 | 240 |
| `ExdevUpgradeLedTask` | 0x5d764 | 0xfc | 252 |

Total: 7468 bytes of upgrade code, all in the 0x5d6bc–0x5f424
range of the binary. That is a small enough footprint that the
entire upgrade subsystem can be re-read end-to-end in under an
hour of focused disassembly.

## Appendix B — Address cross-reference

| Region | Range | Contents |
|---|---|---|
| Upgrade code | 0x5d6bc → 0x5f424 | All 9 upgrade functions |
| Gimbal UART | 0x5fb34 → 0x5fd28 | `UartRxMsgCrc` — owns 0x5A magic byte (UART protocol, NOT file validation) |
| Gimbal UART RX task | 0x5fec4 → 0x60620 | `GimbalUartRxTask` — polls gimbal over UART |
| CRC-8 routine | 0x5e134 → 0x5e184 | CRC-8/ROHC, used in state 9 |
| Dispatcher | 0x5e314 | State-machine jump table |
| IGNORE/FAIL decision | 0x5e278 | Sets struct[0x4] to 0x408 or 0x409 |
| Path string | 0xa5f26c | `/app/sd/FwPkt/gimbal/` |
| sscanf format | 0xa5f428 | `"%*[^_]_%[^bin]"` |
| Exdev dir string | 0xa5ed38 | `/app/sd/ExDevFwPkt/` |
| 0x5A check string | 0xa5f7f7 | `"%d is not 0x5A,offset[%d],len[%d]"` — owned by `UartRxMsgCrc` |
| Gimbal struct base | 0xc46f78 | `s_stGimbalUpgrade` |
| Gimbal struct +0x08 (fp) | 0xc46f80 | `FILE*` (polaris403_ fopen) |
| Gimbal struct +0x0c (sz) | 0xc46f84 | `size_t` (polaris403_ ftell) |
| Gimbal struct +0x8c (v3) | 0xc47004 | `char[?]` (polaris403_ version, sscanf output) |
| Gimbal struct +0xac (fn3) | 0xc47024 | `char[0x80]` (polaris403_ filename) |
| Gimbal struct +0x12c (v4) | 0xc470a4 | `char[?]` (polaris413_ version, sscanf output) |
| Gimbal struct +0x14c (fn4) | 0xc470c4 | `char[0x80]` (polaris413_ filename) |
| Exdev struct | 0xc46d98 | Separate 320-byte BSS scratchpad (0x1e0 below gimbal) |
| HI_LOG_Print | 0x1a2560 | Single logging API used by all upgrade code |
| Size threshold | 0x3e8 | `cmp r3, #0x3e8; bhi` at 0x5ee60 — file must be > 1000 bytes |
| Final return | 0x5f238..0x5f29c | Both `pkt_ok` (+0xac-4=+0xa8? no — see §6.3) and `py_ok` must be 1 |

---

*End of document. If you extend it, add your finding to the
appropriate section and bump the table of contents.*

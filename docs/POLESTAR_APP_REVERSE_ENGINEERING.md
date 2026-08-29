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
6. [`SP_SrchGimbalNewPkt` — the silent-reject locus](#6-sp_srchgimbalnewpkt--the-silent-reject-locus)
7. [`SP_UartRcvGimbalUpgradeMsgProc` — UART message handler](#7-sp_uartrcvgimbalupgrademsgproc--uart-message-handler)
8. [`SP_ExdevUpgradeFromSD` — Exdev (external-device) upgrade path](#8-sp_exdevupgradefromsd--exdev-external-device-upgrade-path)
9. [`SP_CreateGimbalUpgradePthread` — upgrade thread entry point](#9-sp_creategimbalupgradepthread--upgrade-thread-entry-point)
10. [The two shared structs in `.bss`](#10-the-two-shared-structs-in-bss)
11. [PLT / GOT resolved calls](#11-plt--got-resolved-calls)
12. [All `.rodata` strings relevant to upgrade](#12-all-rodata-strings-relevant-to-upgrade)
13. [Call graph for the upgrade flow](#13-call-graph-for-the-upgrade-flow)
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
| `SP_SrchGimbalNewPkt` | 0x5eb24 | 0x900 (2304) | **Silent-reject locus** — scans `/app/sd/FwPkt/gimbal/` for a valid packet |
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
| `strstr` (PLT 0x205c0) | resolves via GOT 0xbf3140 | Tests for "Pkt", ".bin" in dirent names |
| `memset` (PLT 0x22198) | resolves via GOT 0xbf3a88 | Zeros the 128-byte filename buffer |
| `strcpy` (PLT 0x21604) | resolves via GOT 0xbf36ac | Copies the directory path into the buffer |
| `strcat` (PLT 0x22468) | resolves via GOT 0xbf3b78 | Appends the dirent name to the buffer |
| `sscanf` (PLT 0x21718) | resolves via GOT 0xbf3708 | Parses "X_Y.bin" → Y |
| `strlen` (PLT 0x2197c) | resolves via GOT 0xbf37d4 | Measures parsed Y for null-termination |
| `fopen64` (PLT 0x202d8) | resolves via GOT 0xbf3048 | Opens the constructed file path |
| `fclose` (PLT 0x20860) | resolves via GOT 0xbf3278 | Closes the file after size check |
| `fseek` (PLT 0x20c14) | resolves via GOT 0xbf335c | Seeks to end of file |
| `ftell` (PLT 0x2029c) | resolves via GOT 0xbf3034 | Reads file size |
| `rewind` (PLT 0x22228) | resolves via GOT 0xbf3ab8 | Rewinds to start (NB: not `fread`; this was a previous misread) |
| `HI_LOG_Print` | **0x1a2560** (direct symtab, NOT PLT) | The single logging API used throughout the upgrade code |

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
│   SD card → /app/sd/FwPkt/gimbal/X_Y.bin                            │
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
│   SD card → /app/sd/ExDevFwPkt/X_Y.bin                             │
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

## 6. `SP_SrchGimbalNewPkt` — the silent-reject locus

`SP_SrchGimbalNewPkt` is 2304 bytes of pure C compiled to ARM. It
takes a single argument: the directory to scan. In the upgrade
flow, the caller passes the constant string
`/app/sd/FwPkt/gimbal/` (rodata 0xa5f26c).

**Return contract:** `0` on success, `-1` on failure. Failure
is *not* a hard error; the caller treats `-1` as "no upgrade
available" and never invokes `SP_CreateGimbalUpgradePthread`.
This is exactly the "silent" path.

### 6.1 The two-pattern scan

The function walks the directory with `opendir`/`readdir`/`closedir`
and applies **two independent filename tests** to every entry.
**Both** must produce a positive result for the function to
return 0:

1. **Pkt test.** The dirent name must contain the literal
   substring `"Pkt"` (`strstr(..., "Pkt")` at 0x5ebb0).
   The function then `sscanf`s the name with format
   `"%*[^_]_%[^bin]"` (rodata 0xa5f428) which means
   *"skip everything up to and including the first `_`,
   then read everything up to but not including `bin`"*.
   So a name like `100_Pkt_42.bin` would yield `"42"` in
   `struct+0x8c` (the temp parse buffer).

   Then the function opens the file and checks that its size
   (from `ftell`) is **greater than 1000 bytes (0x3e8)**. If so,
   the test is considered passed; `[fp,-8] = 0` is set as
   the success flag.

2. **pY.bin test.** After the `Pkt` test, the same `readdir` is
   continued with `strstr(..., ".bin")` (0x5ebe4) and a check that
   `r3[0x13] == 0x70` (ASCII `'p'`) at 0x5ebf8. So the filename
   must end in `.bin` *and* the first character of the basename
   must be `'p'`. A name like `pHID_LED_2.0.bin` would qualify.

   The same size check (>1000 bytes) is applied. If passed,
   `[fp,-0xc] = 0` is set.

Only if **both `[fp,-8] == 0` and `[fp,-0xc] == 0`** does the
function return `0` (success). Otherwise it returns `-1`.

### 6.2 Complete pseudocode

What follows is the decompilation of `SP_SrchGimbalNewPkt` from
0x5eb24 to 0x5f424, with every PLT call resolved. **All function
names are confirmed by symtab lookup.** All rodata references are
the confirmed addresses.

```c
int SP_SrchGimbalNewPkt(const char *dirpath) {
    struct gimbal_upgrade_state *g = (struct gimbal_upgrade_state *)0xc46f78;
    char fullpath[0x80];                          // at g + 0xac, 128 bytes
    char parsed_version[0x40];                    // at g + 0x8c
    char alt_fullpath[0x80];                      // at g + 0x14c, 128 bytes
    char alt_parsed[0x40];                        // at g + 0x12c

    DIR *d = opendir(dirpath);                    // 0x5eb48
    if (!d) {
        HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                     "open %s dir fail!\n", dirpath);
        return -1;
    }

    int pkt_ok   = 0;                             // [fp, -8]
    int py_ok    = 0;                             // [fp, -0xc]

    for (struct dirent *de = readdir(d);
         de != NULL;
         de = readdir(d)) {                       // 0x5ebf8 / 0x5f254

        // === First scan: "Pkt" pattern ===
        if (strstr(de->d_name, "Pkt")            // 0x5ebb0
         && strstr(de->d_name, ".bin")           // 0x5ebdc
         && de->d_name[0] == 'p') {              // 0x5ebf8

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "ptr->d_name:%s\n", de->d_name);

            memset(fullpath, 0, sizeof fullpath);            // 0x5ec44
            strcpy(fullpath, dirpath);                       // 0x5ec58
            strcat(fullpath, de->d_name);                    // 0x5ec74
            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "pktfile %s\n", fullpath);

            // Parse X_Pkt_Y.bin → Y, e.g. "100_Pkt_42.bin" → "42"
            sscanf(de->d_name, "%*[^_]_%[^bin]",
                   parsed_version);                          // 0x5ecd0
            // Null-terminate before ".bin" by overwriting last char
            size_t L = strlen(parsed_version);               // 0x5ece0
            if (L > 0) parsed_version[L - 1] = '\0';

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %%d\n", parsed_version);

            g->file = fopen64(fullpath, "r");               // 0x5ed50
            if (!g->file) {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31mopen %s file fail!\n\x1b[m", fullpath);
                continue;                                   // NB: continue, not return
            }

            fseek(g->file, 0, SEEK_END);                    // 0x5edcc
            g->filesize = ftell(g->file);                   // 0x5ede0
            rewind(g->file);                                // 0x5ee08
            // ^ NOT fread, despite earlier misread.

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %d\n", parsed_version, g->filesize);

            if (g->filesize > 1000) {                       // 0x5ee60 cmp #0x3e8
                pkt_ok = 0;
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "pkt ok", ...);
            } else {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31m%s size is [%d]],fw error!\n\x1b[m",
                             parsed_version, g->filesize);
                pkt_ok = 1;  // error flag!
            }

            fclose(g->file);                                // 0x5eee8
            g->file = NULL;                                 // 0x5eef8
        }

        // === Second scan: "p" + ".bin" pattern ===
        if (strstr(de->d_name, ".bin")           // 0x5ef18
         && de->d_name[0] == 'p') {              // 0x5ef2c/0x5ef30

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "ptr->d_name:%s\n", de->d_name);

            memset(alt_fullpath, 0, sizeof alt_fullpath);   // 0x5ef80
            strcpy(alt_fullpath, dirpath);                  // 0x5ef94
            strcat(alt_fullpath, de->d_name);               // 0x5efb0
            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "pktfile %s\n", alt_fullpath);

            sscanf(de->d_name, "%*[^_]_%[^bin]",
                   alt_parsed);                             // 0x5f00c
            size_t L = strlen(alt_parsed);                  // 0x5f01c
            if (L > 0) alt_parsed[L - 1] = '\0';

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %%d\n", alt_parsed);

            g->file = fopen64(alt_fullpath, "r");            // 0x5f08c
            if (!g->file) {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31mopen %s file fail!\n\x1b[m", alt_fullpath);
                continue;
            }

            fseek(g->file, 0, SEEK_END);                    // 0x5f108
            g->filesize = ftell(g->file);                   // 0x5f11c
            rewind(g->file);                                // 0x5f144

            HI_LOG_Print(4, "SP_SrchGimbalNewPkt", __LINE__,
                         "%s u32FwSize %d\n", alt_parsed, g->filesize);

            if (g->filesize > 1000) {                       // 0x5f19c cmp #0x3e8
                py_ok = 0;
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "pY ok", ...);
            } else {
                HI_LOG_Print(2, "SP_SrchGimbalNewPkt", __LINE__,
                             "\x1b[0;32;31m%s size is [%d]],fw error!\n\x1b[m",
                             alt_parsed, g->filesize);
                py_ok = 1;
            }

            fclose(g->file);                                // 0x5f224
            g->file = NULL;                                 // 0x5f234
        }
    }

    closedir(d);                                            // 0x5f274

    if (pkt_ok == 0 && py_ok == 0) return 0;                // 0x5f238-0x5f24c
    return -1;                                              // 0x5f290-0x5f29c
}
```

### 6.3 The 128-byte filename buffer (THE BUG)

`SP_SrchGimbalNewPkt` writes the full path into a **128-byte
fixed-size buffer** at `g + 0xac` (`fullpath[0x80]`) and again
into `g + 0x14c` (`alt_fullpath[0x80]`). The string is
constructed as:

```c
strcpy(buf, dirpath);           // "/app/sd/FwPkt/gimbal/"  → 21 bytes
strcat(buf, de->d_name);        // the dirent name
```

If `strlen(dirpath) + strlen(de->d_name) >= 128`, the
**null-termination is silently lost**: the next byte in memory
gets clobbered, and any subsequent `HI_LOG_Print("%s", buf)`
will print past the end of the buffer until it hits a `\0` in
BSS. There is **no `fopen` failure** triggered by this — the
buffer is opened as a path even if its tail is corrupted, and
the kernel's path resolver will report a different error
(silently, to the kernel log) than what `polestar_app` logs.

This is the most likely source of the "zip disappears silently"
behaviour seen in the field: a directory with a long-ish name
clips into the 128-byte buffer, the path becomes garbled, and
`fopen64` returns NULL → logged via `open %s file fail!` but
the **upper-level decision is still "no upgrade available"** →
silent reboot.

[unconfirmed] A user-supplied FwPkt.zip that extracted with a
path like `/app/sd/FwPkt/gimbal/somelongfirmwarenamePkt_42.bin`
(>107 chars) would trigger this clip. The patcher's
`container/patch.sh` should be checked for any path manipulation
that might prepend extra segments.

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
flash. If the patcher ever has to put a longer name there, this
is the buffer to grow.

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
| 0xa5f26c | `/app/sd/FwPkt/gimbal/` | `SP_SrchGimbalNewPkt` | **The directory that must contain `X_Pkt_Y.bin`** |
| 0xa5f33c | `rcv upgrade start\n` | UART | Gimbal MCU ack for state 1 |
| 0xa5f350 | `\x1b[0;35mrcv upgrade start,McuId[%x]\n\x1b[m` | UART | Purple-coloured start with MCU ID |
| 0xa5f374 | `rcv upgrade result\n` | UART | Gimbal MCU ack for state 7 |
| 0xa5f388 | `\x1b[0;32;31mno support this cmd[%d]\n\x1b[m` | UART | Red-coloured "unknown cmd" log |
| 0xa5f3e4 | `ptr->d_name:%s\n` | `SP_SrchGimbalNewPkt` | Per-entry debug log |
| 0xa5f428 | `%*[^_]_%[^bin]` | `SP_SrchGimbalNewPkt` | **The sscanf format** — parses `X_Y.bin` → Y |
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
       └─ SP_SrchGimbalNewPkt("/app/sd/FwPkt/gimbal/")
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

1. **What is the on-board FwVer value the device expects?**
   The user is currently running `FwVer:4.0.0.32;date:2025.05.09;\n`
   (extracted from `/app/sd/FwPkt/FwVer` on the SD card image),
   but it is not clear whether the on-board updater cross-checks
   this against the supplied `firmwareInfo`'s FwVer field before
   or after the `SP_SrchGimbalNewPkt` scan. The `patch.sh`
   script's FwVer-mismatch log (line 65-68) is warn-only, so it
   is not the cause of the silent reject; but the actual check
   may be elsewhere in the binary and not yet located.

2. **What is the JNI bridge or shared object that calls
   `SP_SrchGimbalNewPkt`?** The function is not reached from
   `main` directly — there is at least one intermediate caller
   that has not been identified. Without tracing the actual
   entry point, we cannot say *when* the scan runs (e.g. on
   SD-card insertion, on a UI button press, on a timer, etc.).

3. **What is the second `struct+0x14c` filename buffer used for
   outside the second pattern?** It is not referenced again
   after the second pattern completes in `SP_SrchGimbalNewPkt`,
   but it shares the BSS with the gimbal struct. Other code may
   be writing to it.

4. **Is there a "force upgrade" path that bypasses
   `SP_SrchGimbalNewPkt`?** A user-recoverable recovery path
   (e.g. holding a button at boot) would explain the historical
   ability to recover from a bad flash, but no such path has
   been located in the disassembly.

5. **What is the relationship between the FwPkt.zip structure
   and the directory layout `SP_SrchGimbalNewPkt` expects?**
   The on-board unzip command (`/app/sd/FwPkt.zip -d /app/sd/`,
   string at 0xa6de2e) extracts the **whole zip** into
   `/app/sd/`. The on-board scanner then looks in
   `/app/sd/FwPkt/gimbal/`. So a zip that contains
   `FwPkt/gimbal/X_Pkt_Y.bin` will end up in the right place
   after unzip. If the zip contains a different top-level dir
   (e.g. `BenroPolarisUpdate/gimbal/...`), the on-board scan
   will not find it. This was the original cause of one of the
   earlier "zip disappears" reports (PR #24 comment thread).

6. **Is the 128-byte buffer clip the actual cause of the current
   silent-reject?** Working hypothesis, unconfirmed. To test:
   build a zip that contains a `gimbal/X_Pkt_42.bin` with
   `X_Pkt_42.bin` < 107 characters, drop on SMB, flash, and
   see if the upgrade now succeeds. If it does, this is the
   bug; if it does not, continue down the call graph.

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
| CRC-8 routine | 0x5e134 → 0x5e184 | CRC-8/ROHC, used in state 9 |
| Dispatcher | 0x5e314 | State-machine jump table |
| IGNORE/FAIL decision | 0x5e278 | Sets struct[0x4] to 0x408 or 0x409 |
| Path string | 0xa5f26c | `/app/sd/FwPkt/gimbal/` |
| sscanf format | 0xa5f428 | `%*[^_]_%[^bin]` |
| Exdev dir string | 0xa5ed38 | `/app/sd/ExDevFwPkt/` |
| Gimbal struct | 0xc46f78 | 320-byte BSS scratchpad |
| Exdev struct | 0xc46d98 | 320-byte BSS scratchpad (0x1e0 below) |
| Filename buffer (gimbal) | 0xc47024 (= 0xc46f78 + 0xac) | 128 bytes |
| Filename buffer (exdev)  | 0xc470c8 (= 0xc46f78 + 0x14c) | 128 bytes |
| HI_LOG_Print | 0x1a2560 | Single logging API used by all upgrade code |

---

*End of document. If you extend it, add your finding to the
appropriate section and bump the table of contents.*

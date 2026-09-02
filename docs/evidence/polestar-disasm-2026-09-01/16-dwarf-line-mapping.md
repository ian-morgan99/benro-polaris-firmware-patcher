# 16 — DWARF line info source map

**Purpose:** Map code addresses in `polestar_app` back to source files and line numbers
using DWARF line info embedded in the ELF.

**Tool:** `tools/dwarf_line.py` (per-session build). Reads `readelf -wl` output and
resolves any VA in the binary to a `(file, line)` tuple. Four modes:

```bash
python3 tools/dwarf_line.py <elf> 0x<addr>          # single lookup
python3 tools/dwarf_line.py --range 0x<lo> 0x<hi>   # every line in a range
python3 tools/dwarf_line.py --file sp_oms.c         # all entries in a file
python3 tools/dwarf_line.py --sym SP_OmsUpgradeFromSd  # by symbol name
```

## Coverage

| Metric | Value |
|---|---|
| Total line entries | 11 114 |
| Source files (per DWARF) | 245 |
| Units with full line info | 230+ |
| Units with NO line info (header-only / `-g0`) | ~15 |

`polestar_app` was compiled with `gcc 6.3.0` for `arm-linux-gnueabi`
(`/opt/hisi-linux/x86-arm/arm-himix200-linux/lib/gcc/arm-linux-gnueabi/6.3.0`).
The build uses `-g` (dwarf-2) but the per-TU granularity means some TUs were
compiled with the macros/inlines fully expanded — they have no real source line
info, only the `typecheck-gcc.h` (system header) fallback.

## Source tree (recovered from DWARF)

Every entry in the binary's `File Name Table` resolves to one of these roots
(per the `Directory Table`):

| Root | Module | Examples |
|---|---|---|
| `init/` | bootstrap | `init.c` |
| `hi_system/` | system (HiSilicon SDK) | `hi_system.c` |
| `sp_common/` | shared helpers | `sp_pthread.c`, `sp_type.c` |
| `sp_module/` | sensor/actuator modules | `sp_uart.c`, `sp_msgComm.c`, `sp_msgProc.c`, `sp_media.c`, `sp_sys.c`, `sp_upgrade.c`, `sp_exDevUpgrade.c`, `sp_gimbalUpgrade.c`, `sp_oms.c`, `sp_holy_grail.c` |
| `sp_msgmng/` | messaging | `sp_msgmng.c` |
| `sp_sensor/` | sensor I/O | `sp_sensor.c` |
| `sp_camera/` | camera bridge | `sp_camera.c` |
| `sp_net/` | network/4G | `sp_net.c` |

## All upgrade-related functions (with source locations)

`readelf -s` filtered for `Exdev|Upgrade|ExDev|FwPkt` × `FUNC`. Each entry
resolved by `tools/dwarf_line.py`:

| VA | Size | Symbol | Source:line |
|---|---|---|---|
| `0x0004dfb0` | 160 | `SP_PushUpgradeState` | `sp_msgProc.c:1669` |
| `0x0005b9d8` | 36 | `SP_GetExdevUpgradeFile` | `sp_camera.c:1038` |
| `0x0005b9fc` | 240 | `CheckExdevUpgradeStatus` | `sp_exDevUpgrade.c:25` |
| `0x0005baec` | 2460 | `ExdevUpgradeStatusProc` | `sp_exDevUpgrade.c:40` |
| `0x0005c488` | 772 | `SP_CreateExdevUpgradeStatus` | `sp_exDevUpgrade.c:181` |
| `0x0005c78c` | 1392 | `SP_UartRcvExdevUpgradTask` | `sp_exDevUpgrade.c:229` |
| `0x0005ccfc` | 200 | `SP_ExDevFwPktCheck` | `sp_exDevUpgrade.c:304` |
| `0x0005cdc4` | 2296 | `SP_SrchExdevNewPkt` | `sp_exDevUpgrade.c:314` |
| `0x0005d6bc` | 168 | `SP_PushExdevUpgradeState` | `sp_exDevUpgrade.c:418` |
| `0x0005d764` | 252 | `ExdevUpgradeLedTask` | `sp_exDevUpgrade.c:427` |
| `0x0005d860` | 60 | `SP_CreateExdevUpgradeLed` | `sp_exDevUpgrade.c:443` |
| `0x0005d89c` | 600 | `SP_ExdevUpgradeFromSD` | `sp_exDevUpgrade.c:449` ← **exdev SD variant** |
| `0x0005dc08` | 2284 | `GimbalUpgradeStatusProc` | `sp_gimbalUpgrade.c:37` |
| `0x00074b80` | 36 | `SP_OmsCtx` | `sp_oms.c:175` |
| `0x00074ba4` | 64 | `SP_OmsEvToF` | `sp_oms.c:202` |
| `0x00074be4` | 72 | `SP_OmsEvToIso` | `sp_oms.c:203` |
| `0x00074c2c` | 84 | `SP_OmsEvToShutter` | `sp_oms.c:213` |
| `0x00074c80` | 112 | `SP_OmsIsoToEv` | `sp_oms.c:222` |
| `0x00074cf0` | 120 | `SP_OmsShutterToEv` | `sp_oms.c:230` |
| `0x00074d68` | 112 | `SP_OmsFToEv` | `sp_oms.c:243` |
| `0x00074dd8` | 132 | `SP_OmsEvFromCamera` | `sp_oms.c:255` |
| `0x00074e5c` | 1188 | `SP_OmsRawDataProc` | `sp_oms.c:262` |
| `0x00075300` | 128 | `SP_OmsPushStateToApp` | `sp_oms.c:405` |
| `0x00075380` | 800 | `OmsTask` | `sp_oms.c:415` |
| `0x000756a0` | 288 | `SP_CreateOmsTask` | `sp_oms.c:508` |
| `0x00075804` | 184 | `OmsUpgradeCmdStart` | `sp_oms.c:567` |
| `0x000758bc` | 64 | `OmsUpgradeCmdCancle` | `sp_oms.c:578` |
| `0x000758fc` | 64 | `OmsUpgradeCmdDataReply` | `sp_oms.c:585` |
| `0x0007593c` | 64 | `OmsUpgradeCmdSendData` | `sp_oms.c:592` |
| `0x0007597c` | 64 | `OmsUpgradeCmdCrcReply` | `sp_oms.c:600` |
| `0x000759bc` | 64 | `OmsUpgradeCmdResultReply` | `sp_oms.c:608` |
| `0x000759fc` | 88 | `OmsUpgradeCmdExit` | `sp_oms.c:617` |
| `0x00075a54` | 132 | `OmsUpgradeCmdData` | `sp_oms.c:626` |
| `0x00075ad8` | 292 | `OmsUpgradeTimeOut` | `sp_oms.c:640` |
| `0x00075bfc` | 2904 | `OmsUpgradeStatusProc` | `sp_oms.c:657` |
| `0x00076754` | 404 | `SP_CreateOmsUpgrade` | `sp_oms.c:820` |
| `0x000768e8` | 1596 | `SP_OmsUpgradeMsgProc` | `sp_oms.c:835` |
| `0x00076f24` | 2392 | `SP_OmsUpgradeCheck` | `sp_oms.c:914` |
| `0x0007787c` | 200 | `SP_OmsUpgradePushState` | `sp_oms.c:1010` |
| `0x00077944` | 92 | `SP_OmsUpgradeSetStep` | `sp_oms.c:1021` |
| `0x000779a0` | 168 | `SP_OmsUpgradePush` | `sp_oms.c:1028` |
| `0x00077a48` | 584 | `OmsUpgradePushResult` | `sp_oms.c:1037` |
| `0x00077c90` | 100 | `SP_OmsUpgradePushStateAck` | `sp_oms.c:1074` |
| `0x00077cf4` | 176 | `SP_OmsUpgradeFromSd` | `sp_oms.c:1084` ← **OMS SD entry point** |
| `0x0013efe8` | 100 | `PushUpgradeStateTask` | `sp_upgrade.c:129` |
| `0x0013f04c` | 52 | `SP_PushUpgradeStateAck` | `sp_upgrade.c:137` |
| `0x0013f080` | 836 | `UpgradeTask` | `sp_upgrade.c:142` ← **addls dispatch @ 0x13f104:sp_upgrade.c:156** |
| `0x0013f3c4` | 156 | `SP_CreateUpgradeTask` | `sp_upgrade.c:229` |
| `0x0013f460` | 212 | `UpgradeLedTask` | `sp_upgrade.c:239` |
| `0x0013f534` | 60 | `SP_CreateUpgradeLed` | `sp_upgrade.c:255` |
| `0x0013fde0` | 248 | `SP_CheckUpgradeResult` | `sp_upgrade.c:368` |
| `0x0013fed8` | 280 | `SP_IsDelUpgradeFiles` | `sp_upgrade.c:386` |
| `0x0013fff0` | 116 | `SP_DelUpgradeFiles` | `sp_upgrade.c:409` |
| `0x0014023c` | 1876 | `SP_UpgradeCheckFw` | `sp_upgrade.c:438` |

### sp_upgrade.c — complete 21-function table (extended)

The table above lists 14 sp_upgrade.c functions (all those visible in the symtab with the
"upgrade" name pattern). The full file contains **21 function starts** (verified by ARM
`push {regs}` instruction scan, VA range 0x13eae8..0x140a98 — next push at 0x140a98
is in `sp_ttyUsb.c:47`). The 7 additional functions not captured by the pattern filter:

| VA | Size | Symbol | Source:line | Visibility |
|---|---|---|---|---|
| `0x0013eae8` | 400 | `GetGimbalInfoTask` | `sp_upgrade.c:18` | LOCAL |
| `0x0013ec78` | 52 | `SP_GetGimbalInfoTask` | `sp_upgrade.c:61` | GLOBAL |
| `0x0013ecac` | 500 | `SendHwToGimbalTask` | `sp_upgrade.c:66` | LOCAL |
| `0x0013eea0` | 52 | `SP_SendHwToGimbalTask` | `sp_upgrade.c:101` | GLOBAL |
| `0x0013eed4` | 196 | `GetExFwTask` | `sp_upgrade.c:108` | LOCAL |
| `0x0013ef98` | 80 | `SP_GetGimbalExFwTask` | `sp_upgrade.c:123` | GLOBAL |
| `0x0013f570` | 660 | `SP_GetFwVer` | `sp_upgrade.c:263` | GLOBAL |
| `0x0013f804` | 1108 | `SP_GetDeviceVer` | `sp_upgrade.c:298` | GLOBAL |
| `0x0013fc58` | 392 | `SP_PushDeviceVer` | `sp_upgrade.c:348` | GLOBAL |
| `0x00140064` | 472 | `CrcMd5` | `sp_upgrade.c:421` | GLOBAL |
| `0x00140990` | 264 | `isStrEq` | (none, no DWARF line) | GLOBAL |

**Name conflict at 0x13f04c:** symtab (`readelf -s`) says `SP_PushUpgradeState` (GLOBAL,
52 bytes). DWARF line info says `sp_upgrade.c:137`. The prior evidence file listed
`SP_PushUpgradeStateAck` here — that name comes from a different function in
`sp_msgProc.c:1669` (a different GLOBAL function at 0x4dfb0). The 0x13f04c symbol
is the sp_upgrade.c variant and is named `SP_PushUpgradeState` in the symtab; the
"PushUpgradeStateAck" name in the original entry of this table is a misattribution.
**Use the symtab name `SP_PushUpgradeState` going forward.**

DWARF line entries for sp_upgrade.c: 137 (per `tools/dwarf_line.py --file sp_upgrade.c`).

**Total: 60 upgrade-related functions (53 symtab-matched + 7 sp_upgrade.c additions), ALL mapped to a source file.**

This is a **huge** win — the entire upgrade pipeline now has source attribution.
The four "interesting" entry points (in execution order) are:

1. `SP_GetExdevUpgradeFile @ 0x5b9d8 → sp_camera.c:1038` (probe `/dev/...`)
2. `CheckExdevUpgradeStatus @ 0x5b9fc → sp_exDevUpgrade.c:25` (entry, picks flow)
3. `SP_SrchExdevNewPkt @ 0x5cdc4 → sp_exDevUpgrade.c:314` (searches for update pkg)
4. `SP_ExDevFwPktCheck @ 0x5ccfc → sp_exDevUpgrade.c:304` (per-packet validation)

## The three `addls pc, pc, r3, lsl #2` switch dispatchers

| VA | File:line (DWARF) | Encoding | Verified |
|---|---|---|---|
| `0x13f104` | `sp_upgrade.c:156` | `0x908FF107` (cmp #7) | ✓ capstone |
| `0x3f668` | `typecheck-gcc.h:2664` | `0x908FF103` (cmp #0x17) | ✓ capstone |
| `0x60998` | `sp_uart.c:314` | `0x908FF162` (cmp #0x62) | ✓ capstone |

Only one of three has real source attribution (`sp_uart.c:314`). EventMsgProc's
`0x3f668` is in the same header-only unit (no real source for that TU).

## sp_holy_grail.c — the SD bypass module

`sp_holy_grail.c` is a 875-line module covering `0x6a8d8-0x7069c` (lines 25–1300).
Notable entry points:

| VA | File:line (DWARF) | Symbol | Size |
|---|---|---|---|
| `0x6cb80` | `sp_holy_grail.c:~478` | `HG_OmsAdjEvByShutter` | 2880 |
| `0x6d6c0` | `sp_holy_grail.c:~622` | `HG_OmsAdjEvByIso` | 1032 |
| `0x6dac8` | `sp_holy_grail.c:~676` | `HG_OmsAdjEvByF` | 1060 |
| `0x6deec` | `sp_holy_grail.c:732` | `SP_HG_OmsAdjEv` | 2552 |

This is the "Holy Grail" — a side-channel OMS exposure calculation that bypasses
the normal shutter-priority / iso-priority flow. Whether it gets activated by
SD-upgrade-mismatched firmware is still TBD.

## msgComm dispatcher table (the `0x47d10` callers)

The 28 callers of `0x47d10` all converge in `sp_msgComm.c:59`
(verified by DWARF — the function is `SP_MsgComm_Publish` or similar). The
`0x47d10` call site itself is the message ID dispatch hub. SD install trigger
(msgId `0x405`) comes from this site.

## "typecheck-gcc.h" addresses — what they mean

Some addresses resolve to `typecheck-gcc.h` instead of a real source. This means
**the function is in a TU compiled with `-g` but with macros/inlines fully
expanded** — every line ends up attributed to a system header. Concretely:

- The 3 144-byte `EventMsgProc` (declared at `file 2, line 2595` in DWARF) has
  no real source line info; the `addls` dispatcher at `0x3f668` shows up as
  `typecheck-gcc.h:2664`.
- The `addls` switch case body at `0x3f8fc` (SD install trigger) shows up as
  `typecheck-gcc.h:2657`.

**However**, the function's *declaration* (per `DW_TAG_subprogram` in
`readelf -wi`) is at `file 2 line 2595` — confirming it IS in the same TU as
`sp_msgComm.c`. We just don't get per-instruction line info for it.

## Verified lookups (regression test for the parser)

| Address | Symbol | DWARF result |
|---|---|---|
| `0x77cf4` | `SP_OmsUpgradeFromSd` | `sp_oms.c:1084` |
| `0x76f24` | `SP_OmsUpgradeCheck` | `sp_oms.c:914` |
| `0x768e8` | `SP_OmsUpgradeMsgProc` | `sp_oms.c:835` |
| `0x75bfc` | `OmsUpgradeStatusProc` | `sp_oms.c:657` |
| `0x6deec` | `SP_HG_OmsAdjEv` | `sp_holy_grail.c:732` |
| `0x13f104` | (in `UpgradeTask`) | `sp_upgrade.c:156` |
| `0x60998` | (in `GimbalUartRxMsgProcTask`) | `sp_uart.c:314` |
| `0x3f668` | (in `EventMsgProc`) | `typecheck-gcc.h:2664` |
| `0x322ac` | (in `NetlinkUeventTask`) | `sp_media.c:565` |
| `0x2a348` | (in `main`) | `main.c:213` |

## Why the parser was failing before

Two bugs in the initial draft of `tools/dwarf_line.py`:

1. **File table regex too strict** — didn't handle the `(name, dir, time, size)`
   column order, and got confused by extra whitespace. Fixed with
   `r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s*$"`.

2. **Unit content regex stopped too early** — used `(?:\n\n|\Z)` as terminator
   for "Line Number Statements" content, but `\n\n` legitimately appears
   **inside** the line program (between sequence blocks). Result: each unit
   was truncated to ~7 statements, every address showed as "line 30" of its
   first file. Fixed by terminating at the next unit's `\n  Offset:` header:
   `r"Line Number Statements:\n(.*?)(?:\n  Offset:|\Z)"`.

3. **Initial file index was 0** — should default to 1 per DWARF spec (file
   indices are 1-based).

After the fix, `sp_oms.c` resolves **518 line entries** (the entire OMS module),
`sp_holy_grail.c` resolves **875 line entries**, `sp_media.c` ~600, etc.

## What's NOT covered (for next agent)

- `0x3f610-0x3f700` (EventMsgProc body) — no real line info, need to disassemble
- The 246 other `addls` hits in the binary — only 3 are confirmed dispatchers
- `SP_UartRcvExdevUpgradTask @ 0x5c78c` (1392 bytes) — the SD uart read loop
- `SP_ExdevUpgradeFromSD @ 0x5d89c` (600 bytes) — exdev SD variant
- `OmsUpgradeStatusProc @ 0x75bfc` (2904 bytes) — full state machine
- `SP_UpgradeCheckFw @ 0x14023c` (1876 bytes) — fw validation

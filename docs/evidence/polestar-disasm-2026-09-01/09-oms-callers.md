# 09 -- Call chain into `SP_OmsUpgradeFromSd` (SD-card OMS install)

**Recorded 2026-09-01 during the recording-everything turn.**
**Subject:** End-to-end trace of the SD-card OMS firmware-install trigger,
from Linux kernel uevent through to `OmsUpgradeStatusProc` writing firmware.

> **CRITICAL CORRECTION**: An earlier checkpoint of this work claimed all 65
> OMS/upgrade functions were *dead code*. That claim was **false**, caused
> by a bug in capstone's `ins.operands[0]` accessor for ARM `BL` instructions
> in polestar_app (raises `CS_ERR_DETAIL`). See evidence file
> [`10-capstone-operand-bug.md`](10-capstone-operand-bug.md). After fixing
> the access via `op_str` regex parsing, **54/65 upgrade functions ARE called**.

## TL;DR

```
Linux kernel uevent ("add@/block/mmcblk0/mmcblk0p1")
    |
    v
NetlinkUeventTask (0x322ac)        ; subscribes to /sys/fs/grep/.../uevent
    |  matches SUBSYSTEM="block" + DEVTYPE="partition"
    |  calls SP_EventPub(event_id)  ; for SD: event 0x402 first, then 0x405
    v
EventMsgProcTask (0x40258)         ; single subscriber to the event bus
    |
    v
EventMsgProc (0x3f610, sp_sys.c:2593)
    |  switch on (event_id - 0x401)  via addls pc,pc,r3,lsl #2 at 0x3f668
    |  dispatch table @ 0x3f670
    |
    +-- case 4 (event 0x405)  @ 0x3f8fc, sp_sys.c:2657
            movw r0, #0x405            ;  event id
            bl  0x77cf4               ; -> SP_OmsUpgradeFromSd
            |
            v
        SP_OmsUpgradeFromSd (0x77cf4)  ; sp_oms.c
            ldr  r3, [pc,#0x48] @0x77d48  ;  literal: log line 0x2f7
            movw r3, #0x2f7
            bl   0x1a2560                ; -> SP_Log (severity 4, INFO)
            bl   0x76754                 ; -> SP_CreateOmsUpgradePthread
            bl   0x77944                 ; -> SP_SomeAck / Status send
            pop  {fp, pc}
            |
            v
        SP_CreateOmsUpgradePthread (0x76754)  ; sp_oms.c
            bl   0x2245c                    ; -> pthread_create(...)
                                            ;  with start_routine = 0x75bfc
            pop  {fp, pc}
            |
            v   (new thread)
        OmsUpgradeStatusProc (0x75bfc)    ; sp_oms.c, size 0xb58
            ;  polls fwpkt file on /app/sd, calls SP_OmsUpgradeCheckFwPkt
            ;  via bl 0x76f24 inside its main loop
            ;
            |-->  SP_OmsUpgradeCheckFwPkt (0x76f24)
            |       reads /app/sd/BenroPolaris_v2.fwpkt (or similar)
            |       dispatches to SP_UpgradeProcess / SP_UpgradeCheck
            v
        ... MTD writes to /dev/mtdblock* ...
```

## Discovery steps

1. `SP_OmsUpgradeFromSd @ 0x00077cf4` (size ~144, ARM).
2. `find_callers.py 0x77cf4` -> **1 direct BL**: `0x0003f950: bl 0x77cf4`.
3. `0x3f950` sits inside `EventMsgProc @ 0x0003f610` (size 0xb1c, runs 0x3f610-0x412c).
   - This matches `sp_sys.c:2593` per DWARF line 0xa22.
4. `find_callers.py 0x3f610` -> **1 direct BL**: `0x0040330: bl 0x3f610`.
5. `0x40330` is the entry of `EventMsgProcTask @ 0x0040258` (size 0x1f0).
6. Tracing the event-bus: the entry `SP_EventPub @ 0x3f364` has **14 BL callers**
   (verified via `find_callers.py 0x3f364`).

## SP_EventPub callers (14 sites)

| Caller address | Function | Notes |
|--|--|--|
| 0x325d4 | `NetlinkUeventTask` | 4 sites total; one per event id |
| 0x32924 | `NetlinkUeventTask` | event 0x40b |
| 0x329b0 | `NetlinkUeventTask` | event 0x416 |
| 0x4a9bc | `CheckTtyUsbTask` | ttyUSB poller, 2 sites |
| 0x49ea8 | `GimbalUartRxMsgProcTask` | gimbal UART RX |
| 0x4d778 | `SocketServerTask` | phone-app socket |
| 0x3f364 | `EventMsgProc` itself | self-publishes event 0x405 in case 3 |
| ... | (others) | log + retry paths |

## NetlinkUeventTask events (subsystem strings from .rodata 0xa48120)

Strings confirmed at 0xa48120..0xa481c0 (unencoded plaintext, file offset = vaddr):

- `add@/block/mmcblk0/mmcblk0p1`  -> SD card partition mount -> event 0x402
- `add@/mmc_host/mmc0/mmc0`       -> MMC controller init   -> event 0x402
- `add@/block/mmcblk0`            -> whole SD card         -> event 0x402
- `add@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/`  -> USB hub   -> event 0x40b
- `add@/tty/ttyAMA1/hci0/hci0:`   -> Bluetooth HCI ready   -> event 0x416
- Actions: `umount /app/sd`, `usb_connect`, `usb_disconnect`, `bt conneted`, `4G usb connect`

The `add@/block/mmcblk0/mmcblk0p1` match string is the one that fires when the
user inserts an SD card containing `BenroPolaris_v2.fwpkt`.

## EventMsgProc dispatch table (0x3f668-0x3f6cc)

The `EventMsgProc` switch dispatcher is implemented as a real
`addls pc, pc, r3, lsl #2` at `0x3f668`, reading a 24-entry jump
table at `0x3f670-0x3f6cc`. The addls jumps over the table to the
selected `b` instruction, which in turn dispatches to the case body.

Encoding details:
- 0x3f668: word = `0x908FF103` (cond=LS, opcode=ADD, S=1, Rn=Rd=PC,
  Rm=r3, shift=LSL #2)
- After subtracting 0x401 from msgId, r3 in [0..0x17] is in range
  (msgId 0x401..0x418); otherwise the fallthrough `b 0x40098` is
  taken (default handler).
- The 24 `b <vaddr>` instructions are at 0x3f670-0x3f6cc (one
  4-byte ARM `b` per case).

See [12-eventmsgproc-dispatch.md](12-eventmsgproc-dispatch.md) for
the full case-by-case map and the disassembly of each case body.

The OMS install path is:

- case 4 (event 0x405) @ 0x3f8fc (`sp_sys.c:2657`, log id 0xa61):
  1. log message ("event 0x405 received")
  2. `SP_ScanAllFileList`            @ 0x35fc4   — scan SD file system
  3. `SP_PushSdIdToApp`              @ 0x3f214    — push SD id to remote app
  4. `SP_PushSdInfoToApp`            @ 0x3f130    — push SD info to remote app
  5. `SP_ResetPasswordUseSdcard`     @ 0x423b4    — reset password from SD card
  6. `SP_LogPathInit`                @ 0x4042c    — re-init log path on SD
  7. `SP_ExdevUpgradeFromSD(2)`      @ 0x5d89c    — exdev sub-system upgrade
  8. `SP_OmsUpgradeFromSd()`         @ 0x77cf4    — OMS (main-controller) upgrade

This means event 0x405 is the **SD-card-inserted** handler that
orchestrates ALL the things the system does on an SD insertion:
  - system housekeeping (log path, password reset)
  - remote-app notifications
  - BOTH upgrade paths (Exdev first, then OMS) — sequential, not alternative

The arg `2` to `SP_ExdevUpgradeFromSD` is a "trigger source" code
(0=manual, 1=auto, 2=SD event, 3=other — inferred from the `mov r0, #2`
just before the call).

## Self-reinjection of event 0x405

Event 0x405 is **also** re-published by `SP_EventPub @ 0x3f364` from
other tasks. In particular, `NetlinkUeventTask` (the kernel-uevent
listener) matches `add@/block/mmcblk0/mmcblk0p1` and posts event 0x405,
causing this entire case-4 body to run. There is no separate SD path —
this is THE SD path.

## Verified by direct disassembly

### `EventMsgProc` case 4 body (0x3f8fc..0x3f95c)

```
0x3f8fc: ldr    r3, [pc, #0x848]      ; .rodata str ptr
0x3f900: add    r3, pc, r3
0x3f904: str    r3, [sp]
0x3f908: movw   r3, #0xa61            ; log id = sp_sys.c:2657
0x3f90c: ldr    r2, [pc, #0x83c]      ; .rodata str ("event 0x405" log msg)
0x3f910: add    r2, pc, r2
0x3f914: ldr    r1, [pc, #0x838]      ; .rodata str
0x3f918: add    r1, pc, r1
0x3f91c: mov    r0, #4                ; severity = ERROR
0x3f920: bl     0x1a2560              ; SP_Log
0x3f924: bl     0x35fc4               ; SP_ScanAllFileList
0x3f928: ldr    r3, [pc, #0x7d4]      ; SD device struct ptr
0x3f92c: ldr    r3, [r4, r3]          ; r4 = this
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

**Key corrections vs prior session analysis:**

- The earlier hand-written pseudo-disasm at 0x3f914..0x3f91c was wrong;
  it described a "self re-publish" (`movw r0,#0x405; bl SP_EventPub`)
  that is **not** in case 4. The actual case 4 has 7 BL calls (not 1).
- The re-publish of event 0x405 happens in **case 3** (event 0x404),
  not case 4 — the 0x3f888 region of `EventMsgProc` does the
  conditional `bl SP_EventPub` from the SD-context path.
- Case 4 (event 0x405) is the **executor** of all the SD side-effects,
  not a re-trigger.

### `SP_OmsUpgradeFromSd` body (0x77cf4..0x77d88)

```
0x77cf4: push   {fp, lr}
0x77cf8: add    fp, sp, #4
0x77cfc: sub    sp, sp, #0x10
0x77d00: ldr    r3, [pc, #0x84]       ; check obj.0x6d != 0
0x77d08: ldrb   r3, [r3, #0x6d]
0x77d0c: cmp    r3, #0
0x77d10: beq    0x77d84
0x77d14..0x77d44: opendir/readdir for /app/sd
0x77d6c: bl     0x1a2560              ; log "find .fwpkt" id 0x2f7
0x77d70: bl     0x76754               ; SP_CreateOmsUpgradePthread
0x77d74: mov    r0, #2
0x77d78: bl     0x77944               ; SP_???StatusSend (publish status)
0x77d7c: b      0x77d84
0x77d80: nop
0x77d84: sub    sp, fp, #4
0x77d88: pop    {fp, pc}
```

### `SP_CreateOmsUpgradePthread` pthread_create call (0x76814..0x7682c)

```
0x76814: ldr    r2, [pc, #0xac]       ; literal @ 0x768c8
0x76818: add    r2, pc, r2            ; r2 = 0x76820 + (-0xc24) = 0x75bfc
0x7681c: mov    r1, #0                ; attr = NULL
0x76820: ldr    r0, [pc, #0xa4]       ; literal @ 0x768cc (&tid @ 0xc4a80c)
0x76824: add    r0, pc, r0
0x76828: add    r0, r0, #0x118
0x7682c: bl     0x2245c               ; pthread_create
```

The signed-extend of `0xfffff3dc` is `-0xc24`, added to PC `0x76820` gives
`0x75bfc` -- the entry of `OmsUpgradeStatusProc`. Therefore the thread
function is definitively `OmsUpgradeStatusProc`.

## Cross-references to other paths

The OMS install is reachable via THREE transports, all converging on
`EventMsgProc`:

1. **SD card** -- `NetlinkUeventTask` matches `add@/block/mmcblk0/...`
   posts `event 0x402`, `EventMsgProc` case 1 sets flag, case 3 reposts
   `event 0x405`, case 4 invokes `SP_OmsUpgradeFromSd`.

2. **Bluetooth** -- `BtRcvMsgProcTask @ 0x46xxx` calls
   `SP_OmsUpgradeMsgProc @ 0x768e8` directly via `bl 0x768e8` at `0x469c8`.
   This is the 4G/BT phone-app upgrade path.

3. **Gimbal UART** -- `GimbalUartRxMsgProcTask` receives a `SrchGimbalNewPkt`
   request, calls `SP_SrchGimbalNewPkt` to start a gimbal-firmware pull.
   See evidence file `06-srchgimbal-callers.md` for details.

4. **ExDev UART** -- `ExDevFwPkt` parsing via `/dev/ttyUSB2` or
   `/dev/ttyAMA3`. See evidence file `08-exdev-uart-upgrade-path.md`.

## Test/Exploit implications

- Event 0x405 can in principle be triggered from a privileged shell by
  injecting a netlink message. The cleaner path is to write
  `BenroPolaris_v2.fwpkt` to `/app/sd/` and `umount /app/sd`, which
  fires the kernel uevent naturally.
- We **cannot** call `SP_OmsUpgradeFromSd` directly from the shell because
  polestar_app is the only process that holds the firmware-write
  privileges on `/dev/mtdblock*`. The polestar binary must be the
  one to start the install.
- The bluetooth `SP_OmsUpgradeMsgProc` at 0x768e8 is likely the path
  used by the official phone app to push firmware; understanding its
  framing may be more tractable than SD.

## Status of `OmsUpgradeStatusProc`

`OmsUpgradeStatusProc @ 0x75bfc` has 0 direct BL callers in the entire
binary (verified by `find_callers.py 0x75bfc`). It is reached **only**
via `pthread_create`. The polling cadence, file-search path, and
final MTD write are all inside this function (size 0xb58 = 2904 bytes).

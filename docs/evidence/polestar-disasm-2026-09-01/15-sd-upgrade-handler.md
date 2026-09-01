# 15 — SD-upgrade handler at 0x3f7c0

**Status:** Confirmed via disasm + find_callers.py.
**Vaddr:** `0x3f7c0` → `0x3fa00` (~576 bytes).
**Symbol:** unnamed.
**This is the body of the "case 4" arm** of the 24-case EventMsgProc dispatch
table at `0x3f668-0x3f6cc` (see [12-eventmsgproc-dispatch.md](12-eventmsgproc-dispatch.md)).

This is the handler that gets invoked when EventMsgProc receives a message
that resolves to case index 4. It is the function that actually performs the
SD-card upgrade by calling `SP_ExdevUpgradeFromSD(2)` and `SP_OmsUpgradeFromSd`.

---

## What it does

```
handler_4(void)
  status_check(0x1a23d4)
  if (fail) {
      state = 1
      spSysSendMsg(0x403)
      return
  }
  state = 3
  spSysSendMsg(0x404)             ; "starting" notification
  memset(local_buf, 0, 0x38)
  spSysSendMsg(0x405)             ; "ready" notification
  spSysSendMsg2(1)                ; arg=1
  prep_0x35fc4()
  prep_0x3f130()
  prep_0x423b4()
  prep_0x4042c()
  SP_ExdevUpgradeFromSD(2)        ; arg=2 (vendor mode?)
  SP_OmsUpgradeFromSd()           ; OMS upgrade path
  branch 0x400dc                  ; loop tail / cleanup
```

The crucial points:
1. It publishes **two** EventMsgProc notifications (0x404 and 0x405) BEFORE
   calling the upgrade functions.
2. It calls SP_ExdevUpgradeFromSD **with arg=2**, which is the only arg value
   that passes the gate at `0x5d89c: cmp r3, #2; bne 0x5da98`.
3. It then calls SP_OmsUpgradeFromSd (no arg needed; it's a void/0-arg call).

---

## Disassembly highlights

### Pre-flight status check

```
0x3f7c0: push {r4, r5, r6, r7, fp, lr}
0x3f7c4: add  fp, sp, #0x10
0x3f7c8: sub  sp, sp, #0x40
0x3f7cc: bl   0x1a23d4               ; status check helper
0x3f7d0: cmp  r0, #0
0x3f7d4: bne  0x3f7e0                ; if not 0, branch to failure
0x3f7d8: mov  r3, #1
0x3f7dc: str  r3, [r0, #0x30]        ; state = 1 (failure state?)
0x3f7e0: ...
```

### Failure path: spSysSendMsg(0x403)

```
0x3f7e8: movw r0, #0x403
0x3f7ec: bl   0x3f364                ; spSysSendMsg(0x403)  ← failure notice
0x3f7f0: b    0x400dc                ; jump to tail
```

### Success path begins at 0x3f7f4

```
0x3f7f4: ...
0x3f7f8: bl   0x1a0ad4               ; get state struct
0x3f7fc: mov  r2, #3
0x3f800: str  r2, [r3, #0x30]        ; state = 3
0x3f804: ...
0x3f81c: movw r0, #0x404
0x3f820: bl   0x3f364                ; spSysSendMsg(0x404)  ← "starting"
0x3f824: ...
```

### More progress, then memzero, then spSysSendMsg(0x405)

```
0x3f880: ...
0x3f888: movw r0, #0x405
0x3f88c: bl   0x3f364                ; spSysSendMsg(0x405)  ← "ready"
0x3f890: ...
0x3f8a4: mov  r0, #1
0x3f8a8: bl   0x3f2d8                ; spSysSendMsg2(1)   ← generic ack
0x3f8ac: b    0x400a0                ; continue at 0x400a0
```

### Pre-flight calls (the prep chain)

```
0x3f8fc: bl   0x35fc4                ; prep helper #1
0x3f900: ...
0x3f93c: bl   0x3f130                ; prep helper #2
0x3f940: bl   0x423b4                ; prep helper #3
0x3f944: bl   0x4042c                ; prep helper #4
```

### THE CALL: SP_ExdevUpgradeFromSD with arg=2

```
0x3f948: mov  r0, #2
0x3f94c: bl   0x5d89c                ; SP_ExdevUpgradeFromSD(2)
```

### THE CALL: SP_OmsUpgradeFromSd

```
0x3f950: bl   0x77cf4                ; SP_OmsUpgradeFromSd
0x3f954: b    0x400dc                ; jump to tail
```

---

## Why this is interesting for our patch

1. **It exists and is reached via EventMsgProc case 4.** We don't need to invent
   a new code path — the SD upgrade code is already wired in.
2. **The arg=2 gate at SP_ExdevUpgradeFromSD 0x5d89c is the vendor filter.**
   Other call sites pass arg=0 (rejected) or arg=1 (also rejected). Only arg=2
   enters the vendor-agnostic path that calls pthread_create → ExdevUpgradeStatusProc.
3. **The msgId 0x404 and 0x405 publishes are observable** — the receiver for
   these msgIds (probably another EventMsgProc subscriber) can log progress.
   We can use this for runtime confirmation that the upgrade path executed.

---

## How to trigger case 4

The 24-case dispatch at `0x3f668-0x3f6cc` IS an `addls` switch — see
[12-eventmsgproc-dispatch.md](12-eventmsgproc-dispatch.md) for the full
analysis. The case index is `(msgId - 0x401) - 1`, so case 4 is
msgId 0x405. The case 4 arm starts at `0x3f8fc`.

To find the trigger:
1. Disasm the bytes just BEFORE `0x3f668` (likely the EventMsgProc dispatcher).
2. Look for how the index into the table is computed.
3. Look at the 28 callers of `0x47d10` — one of them publishes a msgId that
   resolves to index 4.

---

## Verification

```
$ python tools/find_callers.py --func SP_ExdevUpgradeFromSD
SP_ExdevUpgradeFromSD: vaddr=0x5d89c
found 1 caller(s):
  vaddr=0x3f94c

$ python tools/find_callers.py --func SP_OmsUpgradeFromSd
SP_OmsUpgradeFromSd: vaddr=0x77cf4
found 1 caller(s):
  vaddr=0x3f950

$ python tools/disasm.py --vaddr 0x3f7c0 --len 0x240
[576 bytes disassembled; matches symbol size]
```

The `mov r0, #2; bl 0x5d89c` sequence at `0x3f948-0x3f94c` is the unmistakable
exdev call with arg=2.

---

## Open questions

1. What publishes msgId that resolves to case 4 in the 24-case dispatch?
2. Is `0x1a23d4` a "card mounted" check? (It returns 0 → failure path;
   non-zero → success path.)
3. What do `0x35fc4`, `0x3f130`, `0x423b4`, `0x4042c` do as pre-flight?
4. Does `SP_OmsUpgradeFromSd` actually fire the OMS message loop at `0x46800`,
   or does it just post an event?
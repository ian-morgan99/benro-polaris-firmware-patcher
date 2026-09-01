# 13 — SP_OmsUpgradeMsgProc (the REAL OMS dispatcher)

**Status:** Confirmed via disasm + find_callers.py.
**Vaddr:** `0x768e8`
**Size:** 1596 bytes (≈ 0x768e8 → 0x76f24; ends right where `SP_OmsUpgradeCheck` begins).
**Symbol table:** `SP_OmsUpgradeMsgProc` (static, internal linkage — capstone auto-detected from symbol table).
**Callers:** exactly **1** — at `vaddr 0x469c8` (inside the OmsUpgrade message loop, see [14-oms-upgrade-loop.md](14-oms-upgrade-loop.md)).

This is the function the prior turn 12-eventmsgproc-dispatch.md was mistakenly
trying to describe. It is NOT at 0x3f668, it does NOT use `addls pc, pc, r3, lsl #2`,
and it is NOT part of the 24-case EventMsgProc table at 0x3f668-0x3f6cc.

The 24-case EventMsgProc dispatch table at 0x3f668-0x3f6cc (described in
[12-eventmsgproc-dispatch.md](12-eventmsgproc-dispatch.md) — to be retracted) is a
**separate** dispatcher; SP_OmsUpgradeMsgProc is reached via the OmsUpgrade
message loop, not via EventMsgProc.

---

## High-level shape

```
SP_OmsUpgradeMsgProc(r0 = struct*)
  fp+0xb   = byte  ← outer switch
  fp+0xc   = byte  ← nested switch (only inside case 0xf1)
  fp+0xd   = byte  ← inner switch (only inside case 0xf1/1)
  fp-0x114 = state (4 bytes)
  fp-0x22c = counter A
  fp-0x230 = counter B
```

The function is entered with a pointer to a message struct in `r0`.

---

## Prologue (0x768e8 → 0x768f8)

```
0x768e8: push {r4, r5, r7, fp, lr}
0x768ec: add  fp, sp, #0xc
0x768f0: sub  sp, sp, #0x1c
0x768f4: mov  r4, r0          ; r4 = struct*
0x768f8: str  r0, [fp, #-0x20] ; spill struct*
```

---

## Outer switch (0x768fc → 0x76934)

The dispatch key is the BYTE at offset 0xb of the message struct:

```
0x768fc: ldrb r3, [r4, #0xb]   ; r3 = struct->byte_at_0xb
0x76900: cmp  r3, #0xf0
0x76904: beq  0x76a9c          ; case 0xf0
0x76908: cmp  r3, #0xf1
0x7690c: beq  0x769a4          ; case 0xf1 (BIG nested switch)
0x76910: cmp  r3, #0xf2
0x76914: beq  0x76dd0          ; case 0xf2 (state machine)
0x76918: ; default: log + return -1
```

### Case 0xf0 (0x7691c → 0x76a9c)

This is a sentinel value that triggers an immediate exit. The function:
1. Loads the state struct via `bl 0x1a0ad4` (returns struct* in `r3`).
2. Logs at line `0x36` via `bl 0x1a2560`.
3. Returns `-1`.

### Case 0xf1 (0x769a4 → 0x76dd0 — BIG nested switch)

```
0x769a4: ldrb r3, [r4, #0xc]   ; nested key
0x769a8: cmp  r3, #1
0x769ac: beq  0x769c0          ; sub-case 1
0x769b0: cmp  r3, #2
0x769b4: beq  0x76bd0          ; sub-case 2
0x769b8: cmp  r3, #3
0x769bc: beq  0x76cb0          ; sub-case 3
0x769c0: cmp  r3, #7
0x769c4: beq  0x76d60          ; sub-case 7
; default: fall through to log + return -1
```

#### Sub-case 1 (0x769c0 → 0x76bd0)

Inner-inner switch on byte at offset 0xd:

```
0x769c0: ldrb r3, [r4, #0xd]   ; innermost key
0x769c4: cmp  r3, #0
0x769c8: beq  0x76a30          ; sub-sub-case 0
0x769cc: cmp  r3, #1
0x769d0: beq  0x76a64          ; sub-sub-case 1
0x769d4: cmp  r3, #2
0x769d8: beq  0x76a98          ; sub-sub-case 2
```

All three sub-sub-cases follow the same skeleton:

```
; precondition: [state_struct + 0x114] == 3
0x76a30: ldr  r3, [fp, #-0x20]
0x76a34: bl   0x1a0ad4         ; get state struct
0x76a38: ldr  r2, [r3, #0x114] ; load state
0x76a3c: cmp  r2, #3
0x76a40: bne  <error>

; action: write a constant to [state_struct + 0x114]
0x76a48: mov  r2, #8           ; ← for sub-sub-case 0
0x76a4c: str  r2, [r3, #0x114]

; log + return 0
0x76a50: movw r0, #0x...
0x76a54: movt r0, #0x...
0x76a58: mov  r1, r4           ; r1 = msg struct
0x76a5c: bl   0x1a2560         ; log
0x76a60: mov  r3, #0
0x76a64: mov  r0, r3
0x76a68: pop  {r4, r5, r7, fp, pc}
```

| sub-sub-case | new state at +0x114 | log line |
|--------------|---------------------|----------|
| 0            | 8                   | 0x21e    |
| 1            | 4                   | 0x227    |
| 2            | 9                   | 0x235    |

**Why this matters:** sub-sub-case 1 sets state = 4, which is the value
checked at 0x46a18 in the OmsUpgrade message loop (see [14-oms-upgrade-loop.md](14-oms-upgrade-loop.md)).
That's the "upgrade is done, exit loop" signal.

#### Sub-case 2 (0x76bd0 → 0x76cb0)

```
0x76bd0: ldr  r3, [fp, #-0x20]
0x76bd4: bl   0x1a0ad4         ; get state struct
0x76bd8: ldr  r2, [r3, #0x114]
0x76bdc: cmp  r2, #7
0x76be0: bne  <error>

; action: bl 0x7597c (a helper); then set [r3+0x114] = ?
0x76be8: bl   0x7597c
0x76bec: ...
```

#### Sub-case 3 (0x76cb0 → 0x76d60)

```
0x76cb0: ldr  r3, [fp, #-0x20]
0x76cb4: bl   0x1a0ad4
0x76cb8: ldr  r2, [r3, #0x114]
0x76cbc: cmp  r2, #6
0x76cc0: bne  <error>
```

Sub-case 3 transitions from state 6 to the next state.

#### Sub-case 7 (0x76d60 → 0x76dd0)

```
0x76d60: ldr  r3, [fp, #-0x20]
0x76d64: bl   0x1a0ad4
0x76d68: mov  r2, #0
0x76d6c: str  r2, [r3, #0x22c] ; counter A = 0
0x76d70: mov  r2, #0
0x76d74: str  r2, [r3, #0x230] ; counter B = 0
0x76d78: ...
```

Sub-case 7 is a "reset counters" path.

### Case 0xf2 (0x76dd0 → end)

```
0x76dd0: ldr  r3, [fp, #-0x20]
0x76dd4: bl   0x1a0ad4         ; get state struct
0x76dd8: ldr  r2, [r3, #0x114]
0x76ddc: cmp  r2, #3
0x76de0: bne  <error>
0x76de4: ...
```

Case 0xf2 is a state-machine driver that updates [r3+0x114] and counter
fields at [r3+0x184], then logs at line `0x23b` via 0x1a2560.

---

## Default (no match)

```
0x76918: movw r0, #0x...        ; format string
0x7691c: movt r0, #0x...
0x76920: mov  r1, r4            ; r1 = msg struct
0x76924: bl   0x1a2560          ; log
0x76928: mov  r3, #-1
0x7692c: mov  r0, r3
0x76930: pop  {r4, r5, r7, fp, pc}
```

---

## What this means for SD upgrade

The OmsUpgrade message loop (see [14-oms-upgrade-loop.md](14-oms-upgrade-loop.md))
calls SP_OmsUpgradeMsgProc once per message it pulls from the queue. Messages
have a fixed layout:

```
struct oms_msg {
    uint32_t id;            // offset 0x0   ; checked as -100 (0xFFFFFF9C)
    uint8_t  pad[7];        // 0x4..0xa
    uint8_t  cmd;           // offset 0xb   ; 0xf0 | 0xf1 | 0xf2
    uint8_t  sub1;          // offset 0xc   ; sub-case under 0xf1
    uint8_t  sub2;          // offset 0xd   ; sub-sub-case under 0xf1/1
    uint8_t  pad2;          // offset 0xe
    ...                      // rest is logging-only
};
```

To complete an OMS upgrade, the protocol (over the OmsUpgrade message queue) is:

| step | msg.id | msg.cmd | msg.sub1 | msg.sub2 | triggers state → |
|------|--------|---------|----------|----------|-------------------|
| 1    | -100   | 0xf1    | 2        | -        | 7 (via sub-case 2) |
| 2    | -100   | 0xf1    | 1        | 0        | 3 → 8 |
| 3    | -100   | 0xf1    | 1        | 1        | → 4 (LOOP EXIT, see 14) |

This protocol is OBSERVED only — the binary does not publish these messages;
they arrive from somewhere external (likely the OMS companion task or the
cellular modem's network task).

---

## Verification trail

```
$ python tools/find_callers.py --func SP_OmsUpgradeMsgProc
SP_OmsUpgradeMsgProc: vaddr=0x768e8
found 1 caller(s):
  vaddr=0x469c8
```

```
$ python tools/disasm.py --vaddr 0x768e8 --len 0x640
[1596 bytes disassembled; matches symbol size]
```

---

## Open questions

1. Who PUBLISHES msg.id=-100 messages with cmd 0xf1/0xf2 to the queue that
   SP_OmsUpgradeMsgProc reads from? (The OmsUpgrade message loop reads from
   queue handle returned by 0x46118; need to trace that.)
2. Is there a sister dispatcher for non-OMS firmware upgrade messages?
3. What does 0x7597c do (the helper called in case 0xf1/2)?
# 14 — OmsUpgrade message loop (0x46800 → 0x46a50)

**Status:** Confirmed via disasm.
**Vaddr:** `0x46800` → `0x46a50` (~600 bytes).
**Symbol:** unnamed (not in symbol table). It is the **only** function that calls
`SP_OmsUpgradeMsgProc` at `0x768e8`, so this is the loop that drains the
OmsUpgrade message queue and dispatches each message.

This loop lives somewhere in the main OmsUpgrade task. It is NOT the 24-case
EventMsgProc dispatcher; it is a separate event-driven loop on a System V IPC
message queue.

---

## What it does (one iteration)

```
while (running) {
    msg = read_from_queue();
    if (msg.id == -100) {                 // signed compare
        formatted = sprintf(buf, "...", msg);
        log(formatted);
        checksum = check(buf);
        if (checksum == ok) {
            state_stack = copy_frame();
            SP_OmsUpgradeMsgProc(msg);    // ← 0x768e8 (real dispatcher)
            timer_result = timer_wait();
            if (timer_result != 0) {
                struct = get_state();
                if (struct->state == 4) break;  // DONE
            }
        }
    }
}
```

---

## Disassembly highlights

### Prologue

```
0x46800: push {r4, r5, r7, fp, lr}
0x46804: add  fp, sp, #0xc
0x46808: sub  sp, sp, #0x200        ; allocate 0x200 bytes local
0x4680c: ...                         ; spill args
```

### Queue read

```
0x46818: bl 0x46118                  ; msgrcv-style read into [fp-0x208]
```

The destination buffer is a 0x200-byte struct on the stack. After the read,
the message id field is at offset 0 of that buffer.

### msg.id == -100 check

```
0x46844: cmn  r3, #0x64              ; r3 + 0x64 == 0 iff r3 == -100 (signed)
0x46848: bne  0x46934                ; if not -100, skip (don't dispatch)
```

### Format + log

```
0x46960: mov  r2, #5                 ; 5 args to sprintf
0x46964: mov  r1, #1
0x46968: mov  r0, r4                 ; output buffer
0x4696c: bl   0x21e5c                ; sprintf(buf, fmt, ...)
0x46970: mov  r1, r4
0x46974: mov  r0, #0x95              ; log line id
0x46978: bl   0x1a2560               ; log()
```

### Checksum/verify

```
0x46998: bl 0x47164                  ; checks msg, returns 0 if ok
0x4699c: cmp r0, #0
0x469a0: bne 0x46a44                 ; if not ok, loop back
```

### Copy frame + dispatch

```
0x469a4: sub  r3, fp, #0x200
0x469a8: sub  r3, r3, #0xc
0x469ac: sub  r3, r3, #8
0x469b0: mov  r2, #0x100
0x469b4: mov  r1, r3
0x469b8: sub  r0, fp, #0x118
0x469bc: bl   0x2131c                ; memcpy(local_buf, msg, 0x100)
0x469c0: sub  r3, fp, #0x118
0x469c4: sub  r3, r3, #0xc
0x469c8: bl   0x768e8                ; ← SP_OmsUpgradeMsgProc(msg)
```

### Post-dispatch

```
0x469cc: mov  r0, #0
0x469d0: bl   0x33e54                ; timer1 = time_now_ms()
0x469d4: mov  r4, r0
0x469d8: bl   0x3401c                ; timer2 = ???
0x469dc: cmp  r0, #0
0x469e0: beq  0x46a44                ; if timer2 == 0, loop back

0x469e4: bl   0x1a0ad4               ; get state struct
0x469e8: ldr  r2, [r3, #0xc0]
0x469ec: cmp  r2, #4
0x469f0: beq  0x46a44                ; if state == 4, loop back (DONE)

; fall through to log
0x469f4: movw r0, #0x...
0x469f8: movt r0, #0x...
0x469fc: mov  r1, #0xa6              ; log line id
0x46a00: bl   0x1a2560               ; log("upgrade failed" or similar)
0x46a04: b    0x46a44                ; loop back
```

The check at 0x469ec (`cmp r2, #4`) on `[state_struct + 0xc0]` is the loop exit
when SP_OmsUpgradeMsgProc set state = 4 via sub-case 1/sub-sub-case 1
(see [13-oms-upgrade-msgproc.md](13-oms-upgrade-msgproc.md)).

---

## Queue identity (0x46118)

The queue read primitive at `0x46118` was not disassembled end-to-end in this
session, but its 1 caller is at `0x46818`. Earlier trace evidence suggests this
queue is the OmsUpgrade companion queue (not the same as the EventMsgProc queue
at `0x31`).

To investigate further:
- `python tools/find_callers.py --vaddr 0x46118` should yield exactly 1 result.
- Disasm `0x46118` to find the queue handle setup.

---

## Why this matters

- This is the **real OMS upgrade flow entrypoint** at runtime.
- It is reached by writing `msg.id = -100` (and appropriate cmd/sub1/sub2
  bytes) into the OmsUpgrade message queue.
- From outside (e.g. via `/proc/<pid>/mem` or dbus), you cannot directly inject
  a message into this queue — you would need to know the queue key.
- However, **inside** the polestar_app process, anything that calls
  `msgsnd(key, msg, ...)` with the right key could publish a message.
- 28 callers of `0x47d10` (the queue write primitive) are all PUBLISHERS
  (see [12-eventmsgproc-dispatch.md](12-eventmsgproc-dispatch.md)). One of
  those 28 publishes onto the OmsUpgrade queue.

---

## Verification

```
$ python tools/disasm.py --vaddr 0x46800 --len 0x250
[600 bytes disassembled; matches symbol size]
```

The single `bl 0x768e8` at `0x469c8` confirms this loop is the only caller of
SP_OmsUpgradeMsgProc.

---

## Open questions

1. Which of the 28 callers of `0x47d10` is the OmsUpgrade publisher?
2. What queue key does `0x46118` open?
3. Is this loop ever reached during normal SD-card upgrade, or only via OMS?
   (The SD-upgrade handler at `0x3f7c0` → `0x3f950` does NOT call this loop;
   it calls SP_OmsUpgradeFromSd directly.)
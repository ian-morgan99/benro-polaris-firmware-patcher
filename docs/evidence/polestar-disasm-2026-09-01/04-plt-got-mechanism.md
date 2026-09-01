# PLT / GOT / Switch Dispatcher Mechanism

**Date:** 2026-09-02
**Source:** `artifacts/polestar_app/polestar_app.original` (ARM ELF)
**Related:** [05-triggers-and-pivot-options.md](05-triggers-and-pivot-options.md) | [07-gimbal-uart-rx-thread.md](07-gimbal-uart-rx-thread.md)

---

## 1. PLT Call Targets

| PLT addr | Symbol | Used by |
|----------|--------|---------|
| 0x206b0 | `sleep@GLIBC_2.4` | `GetExFwTask@0x13eed4`, state 1 handler |
| 0x21658 | `pthread_self@GLIBC_2.4` | `GetExFwTask`, `GimbalUartInitTask` |
| 0x2245c | `pthread_create@GLIBC_2.4` | `GimbalUartInitTask`, `SP_GetGimbalExFwTask` |
| 0x227f8 | `pthread_detach@GLIBC_2.4` | `GimbalUartInitTask` |
| 0x229e4 | `usleep@GLIBC_2.4` | `UpgradeTask@0x13f150` (1_000_000 us) |

## 2. The `usleep(1_000_000)` trick

State 1 (watchdog) at 0x13f148-0x13f150:

```arm
0x13f148: movw r0, #0x4240       ; 0x4240
0x13f14c: movt r0, #0xf          ; 0x000f4240 = 1,000,000
0x13f150: bl   #0x229e4          ; usleep(1_000_000) = sleep 1 second
```

## 3. Switch Dispatchers

ARM pattern: `addls pc, pc, r3, lsl #2`. PC pipeline advances 8 bytes,
so effective base is `dispatcher_addr + 8`.

| Dispatcher | Base | Range | Function |
|------------|------|-------|----------|
| 0x60998 | 0x609a0 | 0..98 | `GimbalUartRxMsgProcTask@0x60620` (98 cases, see file 07) |
| 0x3f668 | 0x3f670 | 0..23 | `EventMsgProc` (24-case, see file 12) |
| 0x13f104 | 0x13f10c | 0..7 | `UpgradeTask@0x13f080` (state machine) |

## 4. Literal-Pool Pattern

`ldr rN, [pc, #X]; add rN, pc, rN` -- literals are **signed**!

For gimbal UART thread spawn at 0x62a14:
- 0x62a60: `0xfffff9c8` -> -0x638 -> +PC = 0x623a8 (Thread A start)
- 0x62a64: `0x00be475c` -> +PC = 0xc47150 (Thread A tid, BSS)
- 0x62a68: `0xffffd4bc` -> -0x2b44 -> +PC = 0x5febc (Thread B start)
- 0x62a6c: `0x00be473c` -> +PC = 0xc47140 (Thread B tid, BSS)
- 0x62a70: `0xffffdbf8` -> -0x2408 -> +PC = 0x60618 (Thread C start, LITERAL POOL STUB)
- 0x62a74: `0x00be471c` -> +PC = 0xc47110 (Thread C tid, BSS)

## 5. Literal Pool Stub Trick

Thread start routines are 8 bytes BEFORE the real function. Those 8
bytes are literal pool data that decodes to conditional instructions
(Z flag) which don't fire in a fresh thread, so execution falls through.

Example 0x60618 (Thread C, before `GimbalUartRxMsgProcTask`):

```
0x60618: e0c3 01b6  -> umullseq pc, pc, r8, r3
0x6061c: e0a6 3096  -> adcseq r6, lr, r0, lsr #24
```

Both conditional with Z flag set; fresh thread Z=0, so fall through to
0x60620.

## 6. PT_LOAD Layout

```
PT_LOAD 1 (code):  File 0..0xbb6fe8  VA 0x10000..0xbc6fe8  (r-x, 12.3MB)
PT_LOAD 2 (data):  File 0xbb7100..0xc25f74  VA 0xbd7100..0xe04e70  (rw-)
BSS:               VA 0xc45f80..0xe04e70  (1.8MB NOBITS)
```

## 7. BSS critical addresses

| Address | Purpose |
|---------|---------|
| 0xc47148 | GLOBALS[0x1310] -> obj pointer |
| 0xc47150 | Thread A tid (BSS) |
| 0xc47160 | Thread A arg (BSS) |
| 0xc47110 | Thread C tid (BSS) |
| 0xc4d904 | "GetExFwTask already running" flag |
| 0xc4d988 | Same purpose, different name |

## 8. GetExFwTask Spawn Chain

```
SP_GimbalUartInit @ 0x62a78
   -> pthread_create(0, 0, 0x6292c, 0)  [8 bytes before GimbalUartInitTask]
GimbalUartInitTask @ 0x62934 (size 324)
   -> pthread_detach(pthread_self())
   -> obj = GLOBALS[0x1310]
   -> call SP_UartSet @ 0x63e18
   -> Spawn 3 child threads:
       A: 0x623a8 (parser)
       B: 0x5febc (reader, arg=&obj)
       C: 0x60618 (dispatcher -- 8 bytes before GimbalUartRxMsgProcTask @ 0x60620)
GimbalUartRxMsgProcTask @ 0x60620 (size 7568)
   -> switch dispatcher at 0x60a00
   -> case 0x21 at 0x60b2c:
         obj->field_a0 = 1
         obj->field_d0 = state_byte
         if (field_d0 != 0) call SP_GetGimbalExFwTask @ 0x13ef98
SP_GetGimbalExFwTask @ 0x13ef98
   -> if (g_flag_0xc4d904 == 0) {
          g_flag_0xc4d904 = 1
          pthread_create(&tid, NULL, GetExFwTask, NULL)
      }
GetExFwTask @ 0x13eed4 (size 196)
   -> pthread_detach(pthread_self())
   -> while (1) {
          if (obj->field_4b0 != 0) { sleep(2); break; }
          obj->field_9c = 0
          SP_GimbalUartGetExFwVer(2)
          sleep(1)
          if (obj->field_d0 != 0) break
          if (obj->field_9c == 0) continue
      }
```

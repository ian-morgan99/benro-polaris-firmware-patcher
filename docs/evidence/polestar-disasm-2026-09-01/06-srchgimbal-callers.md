# 06 -- Call chain into `SP_SrchGimbalNewPkt`

**Recorded 2026-09-01 during the recording-everything turn.**
**Subject:** Trace the call path from the upgrade state machine into the gimbal packet-search routine.

## TL;DR

```
? (extern, probably pthread_create stub)  -> 0x13f080 "UpgradeTask"
                                            |
                                            +-- switch r3=state @ obj.0x4b8:
                                                 case 3:  b 0x13f268  -> bl 0x5e4f4 (gated on obj.0xc != 0)
                                                                              +-- 0x5e4f4  SP_CreateGimbalUpgradePthread
                                                                                          +-- 0x5e594  bl 0x5eb24
                                                                                                       +-- 0x5eb24  SP_SrchGimbalNewPkt
```

## Discovery steps

1. `SP_SrchGimbalNewPkt @ 0x0005eb24` (size 2304, ARM).
2. `find_callers.py 0x5eb24` -> **1 direct BL**: `0x0005e594: bl 0x5eb24`.
3. `0x5e594` sits inside `SP_CreateGimbalUpgradePthread @ 0x0005e4f4` (size 372, runs 0x5e4f4-0x5e664).
4. `find_callers.py 0x5e4f4` -> **1 direct BL**: `0x0013f28c: bl 0x5e4f4`.
5. `0x13f28c` sits inside an anonymous function at `0x0013f080` (size 0x318 = 792, runs 0x13f080-0x13f398).
6. `find_callers.py 0x13f080` -> **0 direct BL** callers.
7. `find_ldr_pc.py 0x13f080` -> **0 PC-relative loads**.
8. `find_data_refs.py 0x13f080` -> **0 data references** in the entire ELF.

**Conclusion:** `UpgradeTask @ 0x13f080` has **no static call sites**. It is registered as a thread function pointer (or callback) somewhere in the runtime that we cannot statically reach.

## State-machine map (function 0x13f080)

The dispatcher at 0x13f0f4 reads `r3 = obj.0x4b8` (the state) and uses `cmp r3, #7; addls pc, pc, r3, lsl #2` to jump into a case table. The b-table is at 0x13f10c-0x13f128:

| State @ obj+0x4b8 | Jump target | Action |
|--|--|--|
| 0 | 0x13f110 | `b 0x13f12c` (counter-increment then test) |
| 1 | 0x13f114 | `b 0x13f1ec` (call 0x14023c, store r0) |
| 2 | 0x13f118 | `b 0x13f228` (log + bl 0x412bc + sleep + bl 0x2ac94) |
| 3 | 0x13f11c | `b 0x13f268` (gimbal check: ldr obj.0xc, cmp 0, bne 0x13f28c) |
| 4 | 0x13f120 | `b 0x13f360` (tail -- sleep 2 s) |
| 5 | 0x13f124 | `b 0x13f2c8` (case 5 body) |
| 6 | 0x13f128 | `b 0x13f314` (case 6 body) |
| 7 | 0x13f10c | `b 0x13f360` (tail -- sleep 2 s) |

### Case 0: counter-increment + 10-minute timeout (0x13f12c-0x13f1e8)

- 0x13f12c-0x13f148: increments obj.0x4c0 (counter), then `bl 0x229e4` (usleep 0xf4240 = 1 000 000 us = 1 s).
- 0x13f160: `cmp r3, #0x258` (decimal 600 -- i.e. 600 s = 10 minutes). If the counter exceeds 600, go to fail.
- 0x13f170: reset counter to 0.
- 0x13f18c-0x13f19c: `bl 0x1a2560` (log "upgrade", with line 0xa9 = 169, "upgrade failed / timeout" message)
- 0x13f1a8: sets obj.0x2c0 = 1 (status = "error"?)
- 0x13f1bc: sets obj.0x4bc = -1.
- 0x13f1c4: `bl 0x4dfb0` (cleanup?)
- 0x13f1c8: `bl 0x13fff0` (another cleanup / fail path)
- 0x13f1d8: sets obj.0x4b0 = 0 (the loop flag = stop)
- 0x13f1e0: `bl 0x2e904` (with r0=0)
- 0x13f1e4: `bl 0x13f04c` (call into the start of the function, the "init" path)
- 0x13f1e8: `b 0x13f36c` (back to tail with state = 0)

So case 0 is a **10-minute timeout** for the upgrade. If the loop doesn't break out within 600 s, it goes to fail and resets.

### Case 1: result-check (0x13f1ec-0x13f224)

- 0x13f1ec: `bl 0x14023c` (poll-result / status?)
- 0x13f1f0-0x13f1fc: `str r0, [fp, #-0x10]; cmp r3, #0; bne 0x13f214`
- 0x13f208-0x13f210: if r0 == 0, set obj.0x4b8 = 3 (state = 3), goto tail.
- 0x13f21c-0x13f224: if r0 != 0, set obj.0x4b8 = 6 (state = 6), goto tail.

So case 1 is **"poll a result; if success, go to state 3; if failure, go to state 6"**.

### Case 2: log + tick (0x13f228-0x13f264)

- 0x13f238-0x13f24c: log line 0xbc = 188 ("upgrade running" or similar), `bl 0x1a2560`.
- 0x13f250: `bl 0x412bc` (intermediate).
- 0x13f254-0x13f25c: `movw r0, #0x86a0; movt r0, #1` -> 0x186a0 = 100 000 us = 100 ms. `bl 0x229e4` (usleep).
- 0x13f260: `bl 0x2ac94` (intermediate).
- 0x13f264: `b 0x13f360` (tail).

Case 2: log + 100 ms tick + step.

### Case 3: gimbal check (0x13f268-0x13f28a)

- 0x13f268-0x13f274: `ldr r3, [obj]; ldr r3, [r3, #0xc]; cmp r3, #0; bne 0x13f28c`
- 0x13f27c-0x13f284: if `obj.c == 0`, sleep 0x7a1200 us = 8 000 000 us = 8 s, then b 0x13f36c (tail).
- 0x13f28c: `bl 0x5e4f4` -> `SP_CreateGimbalUpgradePthread` (the gimbal path)

So the **trigger** for `SP_CreateGimbalUpgradePthread` is:
- the state machine reached state 3 (per the case table)
- AND `obj.c != 0` (some "gimbal connected" / "gimbal ready" flag)

### Loop logic (0x13f36c-0x13f398)

- 0x13f374: `ldr r3, [r3, #0x4b0]; cmp r3, #0; bne 0x13f0f4` -- **if obj.0x4b0 != 0, loop back to the switch**.
- The state is mutated to 0 at various points to break the loop.

The "stop" path:
- 0x13f1dc: `mov r0, #0; bl 0x2e904` (sets state to 0?)
- 0x13f1e4: `bl 0x13f04c` (cleanup)
- 0x13f1e8: `b 0x13f36c` (re-enter the loop with state = 0 -> tail)

## Verifying the dynamic call entry

If `UpgradeTask` is a pthread, the actual caller is likely `pthread_create` itself with `start_routine = &UpgradeTask`. We should look for:

- A `bl pthread_create` (PLT call) that takes the address `0x13f080` as an argument.
- Or a structure that contains a function pointer at offset 0 for some object (the Upgrade state machine object).

`SP_CreateGimbalUpgradePthread` is itself named and explicitly creates a thread. By analogy, `UpgradeTask` at 0x13f080 is likely a *camera*-side pthread created by a similar `SP_Create*UpgradePthread` wrapper.

I did NOT find a `SP_CreateCameraUpgradePthread` in the symbol table. Likely it is:
- either an inline `pthread_create` from somewhere with the address loaded as a literal -- but then `find_data_refs.py` would have found `0x13f080` in .rodata. It didn't.
- or the pointer is in a runtime table. We need to grep `[rX, rX]` references where the address is added to a base.

## Next step

To find the *caller* of `UpgradeTask`, the cleanest path is:
- search for the address 0x13f080 inside a **`struct pthread_create_args`-like** structure, e.g. looking for it in `.data` near other pthread arguments
- OR look for an *offset* from a base address. The function might be referenced as `base + 0x???` inside a vtable.

We confirmed that *no such static reference exists*. So the function pointer is either:
- passed in from a shared library (gstreamer plugin?) -- but `polestar_app` is statically linked per the ELF header.
- assigned at runtime (probably via the HI_system probe or a constructor).

In the prior handover section 5, hypothesis H1 said "watcher is some other daemon" -- closed at 0x13f080 because that daemon is `polestar_app` itself. The Upgrade state machine is the *camera-side* analog of the gimbal upgrade pthread. The follow-up question is **what triggers the pthread to start with the camera-upgrade address**.

I stopped digging here. The user has been told the device is up and the recording-everything turn is the priority.

## Code that I dumped (for future re-analysis)

The dispatcher table is at `0x13f10c-0x13f128`. The literal pool is at `0x13f39c-0x13f3bc+`. The state-machine object is a global at an offset from a base pointer loaded via `ldr r4, [pc, #0x308]` at 0x13f08c.

## Status

**Open:** Who calls `UpgradeTask @ 0x13f080`? Likely answer: `pthread_create` from somewhere in the camera-stream pipeline, but we cannot find the static call site. Need a runtime trace (gdb on the device, or strace -f -e trace=clone).

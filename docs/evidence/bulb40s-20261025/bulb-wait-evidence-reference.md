# Sanitised evidence reference — pgphoto post-release file poll (#230)

Proprietary disassembly is **not** published here; it lives in
`PrivateResearch/polaris-evidence/bulb40s-20261025/pgphoto-wait-loop.txt`.
This file records only what an auditor needs to re-derive the finding independently.

## Source binary identity

| field | value |
|---|---|
| file | `pgphoto.stage2ondisk` (shipped in `6.0.0.54.69`) |
| build id | `6.0.0.54.69-o-v17d-darkframe-budget-20261023` |
| SHA-256 | `3e340e9e03744bdc75ba2f3479999abb092468c05e5e27915530ae0cbb99789e` |
| MD5 | `2e3383301c7691a360175ca6889e26c8` |
| size | 7801576 bytes |
| arch | ARMv7 (Cortex-A7), little-endian, non-PIE, **stripped of nothing** — ships with `.symtab` and DWARF, so `gpManager.c` line numbers map directly onto the code |

## Function and offsets

Symbol `capture_image_with_Bulb`, `gpManager.c:3185-3348`, vaddr `0x101aac`.

| vaddr | gpManager.c | instruction word | disassembly | role |
|---|---|---|---|---|
| `0x101abc` | 3185 | `e50b10cc` | `str r1, [fp, #-0xcc]` | caller's `duration_ms`, stored verbatim |
| `0x101b40` | 3205 | `ebffede9` | `bl #0xfd2ec` (`setCameraStatus(1)`) | bulb ON, before the hold loop |
| `0x101d70` | 3241 | `e51b30cc` | `ldr r3, [fp, #-0xcc]` | hold bound reads `duration_ms` |
| `0x101d88` | 3241 | `9a00002f` | `bls #0x101e4c` | exit hold when `elapsed_ms >= duration_ms` |
| `0x101f68` | 3287 | `e3a0000a` | `mov r0, #0xa` | poll timeout = **10 ms** per iteration |
| `0x102054` | 3308 | `ba000001` | `blt #0x102060` | branch to long budget while files missing |
| `0x102058` | 3308 | `e3a03002` | `mov r3, #2` | fast path when nothing outstanding |
| **`0x102060`** | **3308** | **`e3a03f96`** | **`mov r3, #0x258`** | **600 iterations — the budget patched** |
| `0x102064` | 3308 | `e50b3014` | `str r3, [fp, #-0x14]` | store the budget |
| `0x10207c` | 3313 | `e1520003` | `cmp r2, r3` / `bgt` | give up after 600 iterations |
| `0x1020f0` | 3322 | `e3e03000` | `mvn r3, #0` | returns **-1** ("no file") |
| `0x102214` | 3345 | `ebffec34` | `bl #0xfd2ec` (`setCameraStatus(0)`) | bulb OFF — **after** the hold loop |

## Derivation of the poll interval unit

`wait_and_handle_event` at `0xfa60c` (`gpManager.c:977`). At `gpManager.c:989` its timeout
argument is multiplied by `#0x3e8` (1000) before being passed to the sleep helper, so the
argument is **milliseconds**. Therefore `mov r0, #0xa` = 10 ms and the budget is
`600 × 10 ms ≈ 6 s`.

## Why the hold bound must not move

`setCameraStatus(0)` (`gpManager.c:3345`) executes *after* the hold loop, so the loop bound at
`gpManager.c:3241` controls shutter release as well as the wait. Raising it would lengthen the
exposure. Corroborated by `ff39696`: a requested 40 s bulb measured **40.001 s** app-side hold.

## Measured wall-clock figure (the number the static bound cannot cover)

`6.0.0.54.69`, dial on B, noise reduction **on**, 40 s exposure: Clog reports
`capture end -83196 ms`, i.e. the file appeared ~43 s after release. This is a *measured*
elapsed time; the `600 × 10 ms ≈ 6 s` figure above is a **nominal poll allowance**, not a
measured deadline — see the caveat below.

## Caveat on the 6 s figure (TA point 2)

`600 × 10 ms` assumes every `wait_and_handle_event` call consumes its full timeout. If an event
arrives early the call returns sooner, so the real wall-clock allowance on a failing NR-on run
may differ. Actual per-iteration counts, return codes and elapsed-since-release have **not**
been captured on a failing run; that instrumentation is still outstanding and is tracked as
follow-up work rather than claimed here.

## Patch applied in `6.0.0.54.70`

Single instruction at `0x102060`: `e3a03f96` (`mov r3, #600`) → `e3023710`
(`movw r3, #10000`), giving 100 s of post-release polling. Output SHA-256
`e63063e83920dcf9508173113c272cc54ca41f9a51df1afc4e436574aa766e65`; exactly 3 bytes differ from
the source binary and the file size is unchanged. Full diff:
`docs/evidence/o-v17e-flash-20261025/byte-diff.txt`.

## The loop's second exit condition (added after review; an earlier comment stated this backwards)

The poll loop has two ways to stop, both at `gpManager.c:3313`:

```
0x10207c  cmp r2, r3          ; attempts so far vs the budget
0x102080  bgt #0x10209c       ; out of attempts -> stop and report failure
0x102084  ldr r3, [pc, #0x260]
0x102088  ldr r3, [r4, r3]    ; GOT slot 0x2f7564 -> sp_camera (.bss, 0x3787dc)
0x10208c  ldr r3, [r3]
0x102090  ldr r3, [r3, #0xd0] ; camera state field
0x102094  cmp r3, #1
0x102098  bne #0x101f5c       ; NOT 1 -> keep waiting (0x101f5c is the next poll)
```

So the loop **continues while the field is not 1** and **stops early when it becomes 1**. An earlier
comment on #230 stated this the other way round; that was wrong, caused by misreading the GOT setup at
`0x101ac4` (`ldr r4,[pc,#0x75c]` then `add r4, pc, r4`, giving base `0x2f7000`).

The field is `sp_camera->0xd0`, read through the same GOT slot in sixteen places across pgphoto. Other
sites compare it to 2 (`gphotoMain.c:267`) and 3 (`SP_camera_main.c:182`), so it holds a small number
of states rather than being a boolean.

**Unresolved:** whether this field becomes 1 shortly after shutter release on a noise-reduction run. If
it does, the loop exits before using the raised budget and `.70` has no effect. No log we have covers
this path — the long-exposure logs are K-1 II on `.65`. Needs an instrumented failing run.

# Code 780 `sw:` field — version-sum behavior and the polestar_fwver_patch fix

## What Benro Connect expects

The Benro Connect app (Java: `PolarisOrderCommunication.sendOrder(816, 2, "sw:" + i + ";")`)
reads the `sw` field from code 780 (device-info burst) and displays it as the
firmware version. It expects the **exact five-component camera FwVer** that the
operator set on the device (e.g. `6.0.0.54.65`).

## Stock polestar_app behavior (the bug)

The stock `polestar_app` binary builds the code-780 `sw` value by **adding the
first four numeric components of the gimbal version to the first four components
of the camera version**:

```
sw = (gimbal_major + cam_major).(gimbal_minor + cam_minor).(gimbal_patch + cam_patch).(gimbal_build + cam_build)
```

For a device with `/app/FwVer = 6.0.0.54` and gimbal firmware `2.0.0.22`:

```
sw = (2+6).(0+0).(0+0).(22+54) = 8.0.0.76
```

This is wrong in two ways:
1. The fifth build component (`.65`) is **discarded** — the app sees `8.0.0.76`
   instead of `6.0.0.54.65`.
2. The gimbal version is **summed into** the camera version, so the displayed
   value changes whenever the gimbal firmware is updated, even though the camera
   stack is unchanged.

The summation happens at a fixed 7-word ARM instruction span at VA `0x13FB80`
in the stock `polestar_app` ELF (file offset `0x3FB80`, given the `FILE_VA_BIAS = 0x10000`).
The original sequence performs the per-component adds and a `sprintf` into the
`sysFwVer` global field that code 780 reports.

## The patch (`container/polestar_fwver_patch.py`)

The patch replaces the 7-word span with a `strcpy` of the raw camera version
string from the `mFwVer` global (offset `+0x3a8` in the globals struct) into the
`sysFwVer` field (offset `+0x3e8`), so code 780 reports the exact five-part
version:

```
sw = "6.0.0.54.65"   (exact copy of /app/FwVer content)
```

### Why it's not a simple `sprintf("%s", …)` or naive `strcpy`

Two earlier attempts failed on the live device:

| Attempt | What it did | Failure mode |
|---------|-------------|--------------|
| 1: change format to `%s` | Replaced the second `sprintf`'s format pointer with a standalone `"%s\0"` in `.rodata` | App died while handling code 780 (variadic calling convention mismatch on the ARM soft-float ABI) |
| 2: naive `strcpy` at last word | Placed `bl strcpy` in the final word of the 7-word span | Overwrote `mov r2, #0x40` (the memset length for the following `memset(global+0x468, 0, r2)` call). The later memset ran with whatever `strcpy` left in caller-saved `r2`, non-deterministically zeroing or leaving stale a 64-byte device-info field. Version string was correct but everything else in the burst was corrupted. |

### The working patch layout

The final patch reclaims the two now-dead format-address loads at the start of
the span so that both the `bl strcpy` call **and** the restored `mov r2, #0x40`
fit within the 7-word footprint:

```
0x13FB80  ldr  r0, [pc, #0x84]   ; global-slot literal (rebased to 0x13FC0C)
0x13FB84  ldr  r0, [r4, r0]      ; r0 = &globals
0x13FB88  add  r1, r0, #0x3a8    ; src = &mFwVer (raw camera version)
0x13FB8C  add  r0, r0, #0x3e8    ; dst = &sysFwVer (code 780 "sw" field)
0x13FB90  bl   strcpy            ; exact copy, no variadic format change
0x13FB94  mov  r2, #0x40         ; RESTORED: length for the stock memset below
0x13FB98  mov  r0, r0           ; padding; keeps the span exactly seven words
```

The instruction immediately after the span (`mov r1, #0` at `0x13FB9C`, which
sets up the stock `memset`) is left byte-for-byte intact. The patch verifies
this tail word before and after the write so a future patch that grows past the
span fails closed instead of silently corrupting device info.

## Verification

- **Static:** `container/test_polestar_fwver_patch.sh` checks the patched bytes,
  the tail-word invariant, and the literal-pool entry.
- **Live (code 780):** after install, the first lasting phone socket must
  receive `780@sw:6.0.0.54.<N>;#` where `<N>` matches `/app/FwVer`. This is
  checked in `tests/test_app_burst_protocol.py` and in the canary probe.
- **Monotonic allocator:** `scripts/verify_display_fwver_monotonic.py` ensures
  each new candidate's display FwVer is strictly greater than all previously
  consumed versions (see `docs/RELEASE-VERSION-STATE.md`).

## History

| Version | Candidate | Note |
|---------|-----------|------|
| `.53` | o-v15p | Withdrawn — first attempt at the version patch (format-pointer fix) crashed the app on code 780 |
| `.54` | o-v15q | Installed; reported `6.0.0.54.54` on code 780 (first successful exact-copy install) |
| `.55`–`.65` | o-v15r … o-v16g | All carry the working `strcpy` patch; each reports its exact five-part FwVer on code 780 |

The patch is applied by `container/patch.sh` during every FwPkt build (invoked
from `scripts/build-release-candidate.sh`). It is idempotent: if the site
already contains the patched bytes, it is a no-op.

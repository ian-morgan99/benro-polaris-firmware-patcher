#!/usr/bin/env python3
"""Direct engine probe: does the v96 cancel writer actually write glob_cancel?

AGENTS.md requires that a behaviour claim be tested directly rather than inferred.
The harness lifecycle fixture covers capture_image_with_Bulb, which is NOT where
the cancel writer lives. polaris_cancel_writer_patch.py replaces the `nop` at
0x2033c in stopCaptureImage and the one at 0x203d4 in stopCaptureContinuContinuous
with a branch into a cave that stores 1 into glob_cancel (0x375e08, one byte in
writable .bss).

Addresses used here were read from the symbol table, not guessed:
    stopCaptureImage              @ 0x202e4, size 108  (contains 0x2033c)
    stopCaptureContinuContinuous  @ 0x20350, size 156  (contains 0x203d4)

Each function is straight-line with four external calls and then reaches the
patched site, so it is drivable without modelling any camera state.

v90 is run as a control: at the same sites it holds `nop`, so glob_cancel must
stay 0. If v90 also set it, the probe would be measuring something else.

Read-only: the firmware binary is never modified.
"""
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_PC,
    UC_ARM_REG_LR,
    UC_ARM_REG_SP,
    UC_ARM_REG_R0,
)

V96 = "/home/ian/polaris-v94/out/astro-v96-cancel-writer-20261105/stage2-ondisk/ondisk/pgphoto.stage2ondisk"
V90 = "/home/ian/polaris-v94/out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk"

TEXT_VA = 0x10000          # first LOAD: vaddr 0x10000 == file offset 0
TEXT_SZ = 0x2CFA44         # ends at 0x2dfa44, just past both caves
GLOB_CANCEL = 0x375E08     # one byte in writable .bss (ET_EXEC, unrelocated)
STACK = 0x70000000
STACK_SZ = 0x10000
STOP = 0x60000000          # LR sentinel; pop {fp, pc} returns here

# External calls made by the two functions. Stubbed as no-ops returning 0.
STUBS = {
    0x14E7C: "memset",        # (buf, 0, 0x80)
    0x15464: "ptp_command",   # (buf, arg, len, string)
    0x1A62C: "sleep",         # (30) or (10)
    0x16728: "send_request",  # (0x108, buf)
}

TARGETS = {
    "stopCaptureImage": 0x202E4,
    "stopCaptureContinuContinuous": 0x20350,
}


def run(path, label):
    """Run one function and report glob_cancel before/after."""
    raw = open(path, "rb").read()
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)

    text_len = (TEXT_SZ + 0xFFF) & ~0xFFF
    uc.mem_map(TEXT_VA, text_len)
    uc.mem_write(TEXT_VA, raw[:TEXT_SZ])

    # glob_cancel lives in .bss, outside the text window. Map just its page,
    # zero-filled as it would be at process start.
    bss_page = GLOB_CANCEL & ~0xFFF
    if not (TEXT_VA <= bss_page < TEXT_VA + text_len):
        uc.mem_map(bss_page, 0x1000)

    uc.mem_map(STACK, STACK_SZ)
    uc.mem_map(STOP, 0x1000)
    uc.reg_write(UC_ARM_REG_SP, STACK + 0x8000)

    state = {"calls": [], "insns": 0}

    def hook(u, address, size, _):
        state["insns"] += 1
        if address == STOP:
            u.emu_stop()
            return
        name = STUBS.get(address)
        if name is not None:
            state["calls"].append(name)
            u.reg_write(UC_ARM_REG_R0, 0)
            # These are BL *targets* (callees), so the caller resumes at LR,
            # not at address+size. Resuming at address+size would run on into
            # whatever follows the callee instead of returning to the caller.
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, hook, begin=TEXT_VA, end=TEXT_VA + text_len)
    uc.hook_add(UC_HOOK_CODE, hook, begin=STOP, end=STOP + 4)

    before = bytes(uc.mem_read(GLOB_CANCEL, 1))
    fn = TARGETS[label]
    uc.reg_write(UC_ARM_REG_LR, STOP)
    try:
        uc.emu_start(fn, STOP, count=2000)
    except Exception as exc:  # fail closed: report the engine's own error
        print(f"  {label}: EMULATION ERROR {type(exc).__name__}: {exc}")
        return None

    after = bytes(uc.mem_read(GLOB_CANCEL, 1))
    print(
        f"  {label}: insns={state['insns']} stubs={state['calls']}\n"
        f"  {label}: glob_cancel before={before.hex()} after={after.hex()}"
    )
    return after


def main():
    ok = True
    for label in TARGETS:
        print(f"=== {label} : v96 (patched) ===")
        got = run(V96, label)
        if got is None:
            ok = False
        elif got == b"\x01":
            print("  -> PASS: cancel writer executed and set glob_cancel = 1")
        else:
            print(f"  -> FAIL: glob_cancel is {got.hex()}, expected 01")
            ok = False

        print(f"=== {label} : v90 (unpatched control) ===")
        ctrl = run(V90, label)
        if ctrl is None:
            ok = False
        elif ctrl == b"\x00":
            print("  -> as expected: v90 leaves glob_cancel at 0")
        else:
            print("  -> UNEXPECTED: v90 also set glob_cancel; probe is not isolating the patch")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

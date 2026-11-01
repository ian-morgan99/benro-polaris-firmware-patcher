"""Execute the outcome-preservation stubs emitted for capture_image_with_Bulb.

Two stock instructions overwrite the helper's return slot after
wait_and_handle_event has recorded a cancellation: the stop-callback result at
+0x438 and the getImageToBuffer result at +0x6dc. Each is redirected into a
conditional record in the code cave. These tests run that emitted machine code
directly against a synthetic frame, so they pin the rule itself rather than only
the bytes of a patch.

Unicorn is an optional test dependency and a skip is not a release clearance.
All callbacks are simulated: nothing here establishes shutter closure, output
publication or physical behaviour. See issue #251.
"""

import struct
import sys
from pathlib import Path

import pytest

unicorn = pytest.importorskip("unicorn")
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import (UC_ARM_REG_FP, UC_ARM_REG_PC, UC_ARM_REG_R0,
                               UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_SP)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "container"))
import polaris_bulb_dispatch_patch as patch

CAVE = 0x10000
BULB = 0x20000
FRAME = 0x800000
STACK = FRAME - 0x400
SAVED = FRAME - 16
SENTINEL = 0xDEADBEEF

# The stock words each redirect replaces. Kept here so a change to either the
# patch or this test is visible in one place.
STOP_STORE = 0xE50B3010             # str r3, [fp, #-16]
PUBLISH_STORE = 0xE50B0010          # str r0, [fp, #-16]


def _blob():
    return patch.build_trampoline(
        CAVE, 0x12000, BULB, 0x14000, 0x14100, 0x14200, 0x14300, 0x14400,
        0x14500, 0x14600, 0x14700, 0x14800)


def _machine():
    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    machine.mem_map(CAVE, 0x1000)
    machine.mem_map(BULB, 0x1000)
    machine.mem_map(FRAME - 0x1000, 0x2000)
    machine.mem_write(CAVE, _blob())
    machine.reg_write(UC_ARM_REG_FP, FRAME)
    machine.reg_write(UC_ARM_REG_SP, STACK)
    return machine


def _execute(stub_offset, resume_offset, *, register, value, saved,
             scratch=UC_ARM_REG_R1):
    """Run one emitted stub against a synthetic frame.

    Emulation stops at the resume site itself - ``until`` is exclusive - so
    arrival is proven by the final PC and no instruction has to be invented for
    that site. What lives there is irrelevant to the stub's behaviour.

    Args:
        stub_offset: cave offset holding the stub
        resume_offset: helper offset the stub must resume at
        register: UC register holding the new result (r3 for stop, r0 for publish)
        value: the new result the stock code would have stored
        saved: the outcome already in the return slot
        scratch: register poisoned to detect an undeclared clobber

    Returns:
        (saved_after, pc, register_after, scratch_after)
    """
    machine = _machine()
    machine.mem_write(SAVED, struct.pack("<i", saved))
    machine.reg_write(register, value & 0xFFFFFFFF)
    # Poison a caller-visible register. The stop-path stub must not touch any;
    # the publication stub legitimately uses r1, which is dead at its resume site,
    # so that one passes scratch=None and is covered separately below.
    if scratch is not None:
        machine.reg_write(scratch, SENTINEL)
    machine.emu_start(CAVE + stub_offset, BULB + resume_offset, count=32)
    return (struct.unpack("<i", machine.mem_read(SAVED, 4))[0],
            machine.reg_read(UC_ARM_REG_PC),
            struct.unpack("<i", struct.pack("<I", machine.reg_read(register)))[0],
            None if scratch is None else machine.reg_read(scratch))


@pytest.mark.parametrize("stop_result,saved,expected", [
    # A successful close must not erase a cancellation.
    (0, -52, -52),
    # A failed close outranks the cancellation: the caller must learn the
    # exposure may still be open, not merely that the user cancelled.
    (-1, -52, -1),
    # Normal expiry with a successful close is unchanged from stock.
    (0, 0, 0),
    # A failure with nothing saved yet is recorded as stock did.
    (-7, 0, -7),
])
def test_stop_path_records_only_a_failure(stop_result, saved, expected):
    after, pc, register_after, scratch = _execute(
        patch.BULB_KEEP_CANCEL_OFFSET, patch.BULB_STOP_RELOAD_OFFSET,
        register=UC_ARM_REG_R3, value=stop_result, saved=saved)
    assert after == expected
    assert pc == BULB + patch.BULB_STOP_RELOAD_OFFSET, \
        "stub did not resume at the stock reload site"
    # r3 still carries the stop result, so the stock publish/skip decision at
    # +0x440 is unaffected by the redirect.
    assert register_after == stop_result
    assert scratch == SENTINEL


@pytest.mark.parametrize("publish_result,saved,expected", [
    (0, -52, -52),      # successful publication must not erase a cancellation
    (-1, -52, -52),     # nor may a failed one: retrieving an image from a capture
                        # the user cancelled is downstream housekeeping, and
                        # GP_ERROR_CANCEL is the outcome the caller needs
    (0, 0, 0),          # normal capture is unchanged
    (-3, 0, -3),        # a normal capture still reports a real publication failure
])
def test_publication_never_replaces_a_saved_outcome(publish_result, saved, expected):
    after, pc, register_after, _ = _execute(
        patch.BULB_KEEP_PUBLISH_OFFSET, patch.BULB_PUBLISH_RESUME_OFFSET,
        register=UC_ARM_REG_R0, value=publish_result, saved=saved, scratch=None)
    assert after == expected
    assert pc == BULB + patch.BULB_PUBLISH_RESUME_OFFSET, \
        "stub did not resume at the stock timing block"
    # getImageToBuffer's return value survives for any later reader.
    assert register_after == publish_result


def test_stop_path_and_publication_use_opposite_rules():
    """The two callbacks must not be collapsed into one rule.

    A failed shutter closure is a safety signal and outranks the cancellation;
    a failed image retrieval after a cancellation is noise and must not replace
    it. Collapsing both into "last failure wins" would hide GP_ERROR_CANCEL, and
    collapsing both into "first outcome wins" would hide an open shutter.
    """
    stop_after, _, _, _ = _execute(
        patch.BULB_KEEP_CANCEL_OFFSET, patch.BULB_STOP_RELOAD_OFFSET,
        register=UC_ARM_REG_R3, value=-1, saved=-52)
    publish_after, _, _, _ = _execute(
        patch.BULB_KEEP_PUBLISH_OFFSET, patch.BULB_PUBLISH_RESUME_OFFSET,
        register=UC_ARM_REG_R0, value=-1, saved=-52, scratch=None)
    assert stop_after == -1, "a failed close must outrank the cancellation"
    assert publish_after == -52, "a failed retrieval must not erase the cancellation"


def test_stop_path_leaves_every_caller_visible_register_alone():
    """The stop-path stub must not depend on a scratch register being dead.

    The first draft used r1 there. It happened to be dead at that site, but a
    stub that preserves an outcome should not need that argument to be safe.
    """
    _, pc, register_after, scratch = _execute(
        patch.BULB_KEEP_CANCEL_OFFSET, patch.BULB_STOP_RELOAD_OFFSET,
        register=UC_ARM_REG_R3, value=0, saved=-52)
    assert pc == BULB + patch.BULB_STOP_RELOAD_OFFSET
    assert scratch == SENTINEL, "stop-path stub clobbered r1"
    assert register_after == 0


def test_publication_stub_only_uses_the_proven_dead_register():
    """The publication stub needs r1 because it must read the saved outcome.

    r1 is dead at +0x6e0: the first later mention is the definition
    ``ldr r1,[pc,#364]`` at +0x71c, and the failure branches into +0x750 never
    read it. Pin that r0 - the value stock would have stored - is untouched, so
    nothing downstream of the resume site changes.
    """
    _, pc, register_after, _ = _execute(
        patch.BULB_KEEP_PUBLISH_OFFSET, patch.BULB_PUBLISH_RESUME_OFFSET,
        register=UC_ARM_REG_R0, value=-4, saved=0, scratch=None)
    assert pc == BULB + patch.BULB_PUBLISH_RESUME_OFFSET
    assert register_after == -4


def test_stubs_live_in_previously_unused_cave_words():
    """The fix must not grow the trampoline or displace existing content."""
    blob = _blob()
    assert len(blob) == patch.TRAMPOLINE_SIZE
    # The dispatch tail ends at +0x224 and the literal pool starts at +0x240,
    # so the first stub occupies words that were previously zero.
    assert patch.BULB_KEEP_CANCEL_OFFSET + 16 <= patch.LITERAL_POOL
    for offset in range(patch.BULB_KEEP_CANCEL_OFFSET,
                        patch.BULB_KEEP_CANCEL_OFFSET + 16, 4):
        assert struct.unpack_from("<I", blob, offset)[0] != 0
    # The second stub sits after the match strings, which end at +0x2B7.
    assert patch.BULB_KEEP_PUBLISH_OFFSET >= patch.MODE_KEY_TEXT + 19
    for offset in range(patch.BULB_KEEP_PUBLISH_OFFSET,
                        patch.BULB_KEEP_PUBLISH_OFFSET + 16, 4):
        assert struct.unpack_from("<I", blob, offset)[0] != 0


def _fake_layout(store_word, reload_word=0xE51B3058, compare_word=0xE3530000,
                  resume_word=0xE24B3064):
    """Minimal offsets/addresses for the redirect logic without a real ELF."""
    data = bytearray(0x1000)
    def put(offset, word):
        struct.pack_into("<I", data, offset, word)
    put(patch.BULB_STOP_STORE_OFFSET, store_word)
    put(patch.BULB_STOP_RELOAD_OFFSET, reload_word)
    put(patch.BULB_STOP_RELOAD_OFFSET + 4, compare_word)
    put(patch.BULB_PUBLISH_STORE_OFFSET, PUBLISH_STORE)
    put(patch.BULB_PUBLISH_RESUME_OFFSET, resume_word)
    return bytes(data), {"bulb": 0}, {"bulb": 0x100000}


def test_redirects_target_the_emitted_stubs():
    cave, bulb = 0x2df704, 0x101aac
    for word, source, target in (
        (patch.bulb_keep_cancel_word(bulb, cave),
         bulb + patch.BULB_STOP_STORE_OFFSET,
         cave + patch.BULB_KEEP_CANCEL_OFFSET),
        (patch.bulb_keep_publish_word(bulb, cave),
         bulb + patch.BULB_PUBLISH_STORE_OFFSET,
         cave + patch.BULB_KEEP_PUBLISH_OFFSET),
    ):
        imm = word & 0xFFFFFF
        if imm & 0x800000:
            imm -= 1 << 24
        assert word >> 28 == 0xE, "redirect must be unconditional"
        assert source + 8 + imm * 4 == target


def test_refuses_an_unrecognised_stop_store():
    """Fail closed: never redirect a layout that was not verified."""
    data, offsets, addresses = _fake_layout(0xE1A03000)   # mov r3, r0, not a store
    with pytest.raises(ValueError, match="stop-path store"):
        patch.patch_bulb_cancel_result(data, offsets, addresses, 0x2df704)


def test_refuses_an_unrecognised_publish_store():
    data = bytearray(0x1000)
    struct.pack_into("<I", data, patch.BULB_STOP_STORE_OFFSET, STOP_STORE)
    struct.pack_into("<I", data, patch.BULB_STOP_RELOAD_OFFSET, 0xE51B3058)
    struct.pack_into("<I", data, patch.BULB_STOP_RELOAD_OFFSET + 4, 0xE3530000)
    struct.pack_into("<I", data, patch.BULB_PUBLISH_STORE_OFFSET, 0xE1A00000)
    struct.pack_into("<I", data, patch.BULB_PUBLISH_RESUME_OFFSET, 0xE24B3064)
    with pytest.raises(ValueError, match="publication store"):
        patch.patch_bulb_cancel_result(bytes(data), {"bulb": 0}, {"bulb": 0x100000},
                                       0x2df704)


def test_refuses_a_damaged_surrounding_instruction():
    """The publish decision after the stop store must still be the stock cmp."""
    data, offsets, addresses = _fake_layout(STOP_STORE, compare_word=0xE3530001)
    with pytest.raises(ValueError, match="publish decision"):
        patch.patch_bulb_cancel_result(data, offsets, addresses, 0x2df704)


def test_redirect_is_idempotent_and_reverifies_the_layout():
    cave = 0x2df704
    data, offsets, addresses = _fake_layout(STOP_STORE)
    once, changed = patch.patch_bulb_cancel_result(data, offsets, addresses, cave)
    assert changed
    twice, changed_again = patch.patch_bulb_cancel_result(once, offsets, addresses, cave)
    assert not changed_again and twice == once
    # An already-redirected store with a damaged neighbour is still rejected.
    damaged = bytearray(once)
    struct.pack_into("<I", damaged, patch.BULB_STOP_RELOAD_OFFSET, 0xE1A00000)
    with pytest.raises(ValueError, match="reload of the stop result"):
        patch.patch_bulb_cancel_result(bytes(damaged), offsets, addresses, cave)

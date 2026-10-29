"""Execute the emitted ARM dispatcher with ABI-faithful widget stubs.

Unicorn is an optional test dependency; a skip is not a release clearance.
The stubs model widget ownership and text pointer lifetime, not camera I/O.
"""

import struct
import sys
from pathlib import Path

import pytest

unicorn = pytest.importorskip("unicorn")
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_CPSR, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_SP)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "container"))
import polaris_bulb_dispatch_patch as patch

CAVE, BURST, BULB = 0x10000, 0x12000, 0x13000
MANUFACTURER, NAME, CASESTR = 0x14000, 0x14100, 0x14200
GET_CONFIG, GET_TYPE, GET_VALUE, FREE, STRSTR = 0x14300, 0x14400, 0x14500, 0x14600, 0x14700
GLOBAL, WIDGET, TEXT, VENDOR = 0x30000, 0x31000, 0x32000, 0x33000
STACK = 0x50000


def _cstring(machine, address):
    result = bytearray()
    for offset in range(2048):
        byte = machine.mem_read(address + offset, 1)[0]
        if not byte:
            return bytes(result)
        result.append(byte)
    raise AssertionError("unterminated string")


def _run(*, model="PENTAX K-3 Mark III", vendor="PENTAX", mode=8,
         duration=5, status=0, failure=None):
    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    machine.mem_map(0x10000, 0x50000)
    blob = patch.build_trampoline(CAVE, BURST, BULB, MANUFACTURER, NAME,
                                  CASESTR, GLOBAL, GET_CONFIG, GET_TYPE,
                                  GET_VALUE, FREE, STRSTR)
    machine.mem_write(CAVE, blob)
    machine.mem_write(GLOBAL, struct.pack("<I", 0x1234))
    machine.mem_write(TEXT, (f"exposure-mode-raw={mode};").encode() + b"\0")
    machine.mem_write(VENDOR, vendor.encode() + b"\0")
    machine.reg_write(UC_ARM_REG_SP, STACK)
    machine.reg_write(UC_ARM_REG_R0, status)
    machine.reg_write(UC_ARM_REG_R1, duration & 0xFFFFFFFF)
    machine.reg_write(UC_ARM_REG_R2, 0xACDC)
    machine.reg_write(UC_ARM_REG_LR, 0x18000)
    state = {"freed": 0, "widget": False, "searches": 0, "result": None}

    def put32(addr, value):
        machine.mem_write(addr, struct.pack("<I", value & 0xFFFFFFFF))

    def hook(uc, address, size, data):
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        if address in (BULB, BURST + 12, 0x18000):
            state["result"] = (address, r0, r1, uc.reg_read(UC_ARM_REG_R2))
            uc.emu_stop()
            return
        if address == MANUFACTURER:
            result = VENDOR
        elif address == NAME:
            uc.mem_write(r0, model.encode() + b"\0")
            result = 0
        elif address == CASESTR:
            result = r0 if _cstring(uc, r1).lower() in _cstring(uc, r0).lower() else 0
        elif address == GET_CONFIG:
            assert r0 == 0x1234 and _cstring(uc, r1) == b"pentaxconditions"
            if failure == "config":
                result = -1
            elif failure == "no-output":
                result = 0
            elif failure == "null-widget":
                put32(uc.reg_read(UC_ARM_REG_R2), 0)
                result = 0
            else:
                put32(uc.reg_read(UC_ARM_REG_R2), WIDGET)
                state["widget"] = True
                result = 0
        elif address == GET_TYPE:
            assert r0 == WIDGET and state["widget"] and not state["freed"]
            put32(r1, 3 if failure == "wrong-type" else 2)
            result = -1 if failure == "type" else 0
        elif address == GET_VALUE:
            assert r0 == WIDGET and state["widget"] and not state["freed"]
            # GP_WIDGET_TEXT writes a char * into the caller's slot.
            put32(r1, 0 if failure == "null-text" else TEXT)
            result = -1 if failure == "value" else 0
        elif address == STRSTR:
            assert state["widget"] and not state["freed"]
            assert r0 == TEXT, "must pass the returned pointer, not its stack slot"
            state["searches"] += 1
            result = r0 if _cstring(uc, r1) in _cstring(uc, r0) else 0
        elif address == FREE:
            assert r0 == WIDGET and state["widget"] and not state["freed"]
            state["freed"] += 1
            # Poisoning makes any subsequent use of the borrowed text invalid.
            uc.mem_write(TEXT, b"\0")
            result = 0
        else:
            return
        uc.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    machine.hook_add(UC_HOOK_CODE, hook)
    machine.emu_start(CAVE, 0x19000, count=1000)
    assert state["result"] is not None
    assert state["freed"] == int(state["widget"])
    expected_r0 = 0xFFFFFF92 if state["result"][0] == 0x18000 else status
    assert state["result"][1:] == (expected_r0, duration & 0xFFFFFFFF, 0xACDC)
    return state


@pytest.mark.parametrize("mode", [9, 12, 20])
def test_live_b_modes_route_to_bulb_while_widget_alive(mode):
    state = _run(mode=mode)
    assert state["result"][0] == BULB
    assert state["searches"] > 0


@pytest.mark.parametrize("kwargs", [
    {"mode": 8}, {"mode": 99}, {"model": "PENTAX K-1 Mark II", "mode": 9},
    {"model": "PENTAX K-3 Mark III Monochrome", "mode": 9},
    {"vendor": "Canon", "mode": 9}, {"duration": 0, "mode": 9},
    {"duration": -1, "mode": 9}, {"status": 1, "mode": 9},
])
def test_other_paths_fall_back_with_original_arguments(kwargs):
    assert _run(**kwargs)["result"][0] == BURST + 12


@pytest.mark.parametrize("failure", ["config", "no-output", "null-widget", "type", "wrong-type", "value", "null-text"])
def test_unknown_mode_returns_error_without_starting_a_shot(failure):
    assert _run(failure=failure)["result"][0] == 0x18000


@pytest.mark.parametrize("equal", [False, True])
def test_cancel_branch_only_takes_stop_edge_when_equal(equal):
    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    machine.mem_map(0x10000, 0x10000)
    source = BULB + patch.BULB_CANCEL_OFFSET
    target = BULB + patch.BULB_CANCEL_STOP_PATH_OFFSET
    machine.mem_write(source, struct.pack("<I", patch.bulb_cancel_patch_word(BULB, target)))
    machine.reg_write(UC_ARM_REG_CPSR, 0x13 | (0x40000000 if equal else 0))
    machine.emu_start(source, 0x1F000, count=1)
    assert machine.reg_read(UC_ARM_REG_PC) == (target if equal else source + 4)

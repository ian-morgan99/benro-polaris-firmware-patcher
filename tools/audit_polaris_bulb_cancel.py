"""Reproduce the v90 cancel-return defect without a camera or firmware write.

Usage: OBJDUMP=/path/to/arm-objdump python3 tools/audit_polaris_bulb_cancel.py
       /path/to/v90/pgphoto.stage2ondisk

Requires pyelftools and unicorn. The input must be the exact v90 dispatcher
marker; the script reverses its known patch in memory and applies this
checkout's dispatcher. It exits nonzero while successful cleanup hides cancel.
All camera/event/file callbacks are simulated; this is not hardware evidence.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import types

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "container"))
import polaris_bulb_dispatch_patch as new

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pgphoto", help="the exact v90 pgphoto.stage2ondisk binary")
binary = parser.parse_args().pgphoto
with open(binary, "rb") as stream:
    digest = hashlib.sha256(stream.read()).hexdigest()
expected_digest = "8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac"
if digest != expected_digest:
    sys.exit("Refusing unknown pgphoto binary: sha256=" + digest)
source = subprocess.check_output(["git", "-C", str(repo), "show", "f344e41261a886f8f6107b9467095bc90b3835a1:container/polaris_bulb_dispatch_patch.py"], text=True)
old = types.ModuleType("old_patcher")
exec(compile(source, "v90_patcher", "exec"), old.__dict__)
data, offsets, addresses, seg = new.inspect_binary(binary)
old_size = old.TRAMPOLINE_SIZE
base = seg["filesz"] - old_size
cave = seg["vaddr"] + base
cave_off = seg["offset"] + base
original_blob = old.build_trampoline(cave, addresses["burst"], addresses["bulb"],
    addresses["manufacturer"], addresses["name"], addresses["strcasestr"],
    addresses["camera_global"], addresses["camera_get_single_config"],
    addresses["widget_get_value"], addresses["widget_free"], addresses["strstr"])
assert bytes(data[cave_off:cave_off + old_size]) == original_blob
assert struct.unpack_from("<I", data, offsets["burst"])[0] == old.encode_branch(addresses["burst"], cave)
assert struct.unpack_from("<I", data, offsets["bulb"] + old.BULB_CANCEL_OFFSET)[0] == old.bulb_cancel_patch_word(addresses["bulb"], addresses["bulb"] + old.BULB_CANCEL_STOP_PATH_OFFSET)

# Reconstruct only the known patch effects in a bytearray, never on disk. This
# derives the unpatched layout from v90's validated marker; it is a diagnostic,
# not a pristine stock image or a release artifact.
struct.pack_into("<I", data, offsets["burst"], old.BURST_PROLOGUE[0])
data[cave_off:cave_off + old_size] = bytes(old_size)
source_va = addresses["bulb"] + old.BULB_CANCEL_OFFSET
struct.pack_into("<I", data, offsets["bulb"] + old.BULB_CANCEL_OFFSET,
                 old.encode_branch(source_va, addresses["bulb"] + old.BULB_CANCEL_OLD_TARGET_OFFSET, condition=0))
segment = dict(seg, filesz=seg["filesz"] - old_size, memsz=seg["memsz"] - old_size)
struct.pack_into("<I", data, seg["phdr_offset"] + 16, segment["filesz"])
struct.pack_into("<I", data, seg["phdr_offset"] + 20, segment["memsz"])
patched, changed = new.patch_data(data, offsets, addresses, segment)
assert changed
assert struct.unpack_from("<I", patched, offsets["bulb"] + new.BULB_CANCEL_OFFSET)[0] >> 28 == 0
repeat = dict(segment, filesz=segment["filesz"] + new.TRAMPOLINE_SIZE,
              memsz=segment["memsz"] + new.TRAMPOLINE_SIZE)
same, changed_again = new.patch_data(patched, offsets, addresses, repeat)
assert not changed_again and same == patched
print("PASS: v90 exact marker verified; reconstructed ELF layout accepts current dispatcher patch and idempotent recheck")
print("LIMIT: in-memory diagnostic only; not a stock firmware build or hardware qualification")

# Execute the patched cancel edge through the real helper instructions until
# its stop callback result overwrites the saved error. External calls are
# faithfully bounded stubs: they do not issue any PTP operation or touch a
# camera. The input is deliberately the current v90 ELF and remains in RAM.
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_FP, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR

with open(binary, "rb") as stream:
    elf = ELFFile(stream)
    loads = [dict(s.header) for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    syms = {s.name: s["st_value"] for table in elf.iter_sections()
            if table["sh_type"] == "SHT_SYMTAB" for s in table.iter_symbols()}

def target_of_branch(offset):
    source = addresses["bulb"] + offset
    word = struct.unpack_from("<I", patched, offsets["bulb"] + offset)[0]
    imm = word & 0xffffff
    if imm & 0x800000:
        imm -= 1 << 24
    return source + 8 + imm * 4

snprintf_plt = target_of_branch(0x410)
bulb = addresses["bulb"]
frame = 0x810000
stack = 0x80c000

def execute_cancel(stop_result):
    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    machine.mem_map(0x10000, 0x400000)
    machine.mem_map(0x800000, 0x20000)
    for segment in loads:
        off, size, address = segment["p_offset"], segment["p_filesz"], segment["p_vaddr"]
        machine.mem_write(address, bytes(patched[off:off + size]))
    machine.reg_write(UC_ARM_REG_FP, frame)
    machine.reg_write(UC_ARM_REG_SP, stack)
    machine.mem_write(frame - 16, struct.pack("<i", -52))
    calls = []

    def hook(uc, address, size, opaque):
        if address == bulb + 0x43c:
            uc.emu_stop()
            return
        if address == syms["cb_arg_run"]:
            calls.append("stop callback")
            uc.mem_write(frame - 88, struct.pack("<i", stop_result))
        elif address in (syms["gp_log"], syms["HI_LOG_Print"], snprintf_plt):
            calls.append("external stub")
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    machine.hook_add(UC_HOOK_CODE, hook)
    machine.emu_start(bulb + 0x328, bulb + 0x440, count=1000)
    return struct.unpack("<i", machine.mem_read(frame - 16, 4))[0], calls

for stop_rc in (0, -1):
    saved, calls = execute_cancel(stop_rc)
    assert "stop callback" in calls
    print("CANCEL input=-52, stub stop result=%d, subsequent saved result=%d" % (stop_rc, saved))
    if stop_rc == 0 and saved != -52:
        print("OPEN DEFECT: successful stop overwrites the saved cancellation; complete return-path fix required")

# Continue to the real return instruction with fake successful event and image
# callbacks. This is an execution model of the binary control flow, not proof
# that a physical shutter closed or that a real file was published.
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4

def execute_until_return(stop_result):
    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    machine.mem_map(0x10000, 0x400000)
    machine.mem_map(0x500000, 0x1000)
    machine.mem_map(0x800000, 0x20000)
    for segment in loads:
        off, size, address = segment["p_offset"], segment["p_filesz"], segment["p_vaddr"]
        machine.mem_write(address, bytes(patched[off:off + size]))
    def put32(address, value):
        machine.mem_write(address, struct.pack("<I", value & 0xffffffff))
    machine.reg_write(UC_ARM_REG_FP, frame)
    machine.reg_write(UC_ARM_REG_SP, stack)
    got = bulb + 0x24 + struct.unpack_from("<I", patched, offsets["bulb"] + 0x77c)[0]
    machine.reg_write(UC_ARM_REG_R4, got)
    put32(got + 0x628, 0x400000)
    put32(got + 0x564, 0x402000)
    put32(0x402000, 0x401000)
    put32(0x401000 + 0xd0, 0)
    put32(frame - 16, -52)
    put32(frame - 36, 1)
    put32(frame, 0x500000)
    events = []
    seen = []
    usleep_plt = target_of_branch(0x664)
    gettimeofday_plt = target_of_branch(0x6d0)
    stubs = {syms[name] for name in ("gp_log", "HI_LOG_Print", "timediff_now",
             "getImageToBuffer", "setCameraStatus")}
    stubs.update((snprintf_plt, usleep_plt, gettimeofday_plt))

    def hook(uc, address, size, opaque):
        if address == 0x500000:
            seen.append("returned")
            uc.emu_stop()
            return
        if address == syms["cb_arg_run"]:
            seen.append("stop")
            put32(frame - 88, stop_result)
        elif address == syms["wait_and_handle_event"]:
            event = 2 if not events else 4
            events.append(event)
            put32(uc.reg_read(UC_ARM_REG_R1), event)
        elif address not in stubs:
            return
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    machine.hook_add(UC_HOOK_CODE, hook)
    try:
        machine.emu_start(bulb + 0x328, 0x500004, count=10000)
    except Exception:
        print("emulator PC at failure:", hex(machine.reg_read(UC_ARM_REG_PC)))
        raise
    assert "returned" in seen, (seen, events, hex(machine.reg_read(UC_ARM_REG_PC)))
    return struct.unpack("<i", struct.pack("<I", machine.reg_read(UC_ARM_REG_R0)))[0], events

failed = False
for stop_rc in (0, -1):
    result, events = execute_until_return(stop_rc)
    print("FULL RETURN: cancel=-52 stop=%d return=%d fake-events=%s" % (stop_rc, result, events))
    expected = -52 if stop_rc == 0 else stop_rc
    if result != expected:
        print("FAIL: cancellation or stop failure was not preserved", file=sys.stderr)
        failed = True
if failed:
    sys.exit(1)

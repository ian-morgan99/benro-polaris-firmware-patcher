#!/usr/bin/env python3
"""Offline audit of an exact built ptp2.so. Does not open a camera.

This calls the production condition classifiers, not a reimplementation.
Inputs are synthetic reproductions of logged fields, NOT captured full frames.
Output is diagnostic evidence, not a hardware test or a recovery implementation.
Run with LD_LIBRARY_PATH pointing at the matching core and port libraries.
"""

import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} /absolute/path/to/ptp2.so")
    path = Path(sys.argv[1]).resolve(strict=True)
    module = ctypes.CDLL(str(path))
    admission = module.pentax_admission_block_reason
    admission.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    admission.restype = ctypes.c_int
    reason_name = module.pentax_admission_block_reason_name
    reason_name.argtypes = [ctypes.c_int]
    reason_name.restype = ctypes.c_char_p
    reconcile = module.pentax_reconcile_conditions
    reconcile.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                          ctypes.POINTER(ctypes.c_uint32)]
    reconcile.restype = ctypes.c_int
    print(json.dumps({"module": str(path),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "hardware_io": False, "synthetic_inputs": True}))
    for label, size, flag, handle, activity in [
        ("logged-1600-candidate-fields", 576, 1, 1, 0),
        ("shooting-with-candidate", 576, 1, 1, 1),
        ("processing-with-candidate", 576, 1, 1, 2),
        ("idle", 576, 0, 0, 0),
        ("flag-with-zero-handle", 576, 1, 0, 0),
        ("handle-without-flag", 576, 0, 1, 0),
        ("short-frame", 107, 1, 1, 0),
    ]:
        frame = bytearray(576)
        for offset, value in [(32, flag), (36, handle), (104, activity)]:
            struct.pack_into("<I", frame, offset, value)
        data = ctypes.create_string_buffer(bytes(frame))
        candidate = ctypes.c_uint32(0)
        reason = reason_name(admission(data, size, 0)).decode()
        decision = reconcile(data, size, ctypes.byref(candidate))
        print(json.dumps({
            "case": label, "size": size, "field32": flag,
            "field36": handle, "field104": activity,
            "strict_reason": reason, "reconcile_enum": decision,
            "reconciled_handle": candidate.value,
            "it2_candidate_flag": flag == 1 if size >= 108 else None,
            "it2_shooting_bit": bool(activity & 1) if size >= 108 else None,
            "it2_processing_bit": bool(activity & 2) if size >= 108 else None,
        }))


if __name__ == "__main__":
    main()

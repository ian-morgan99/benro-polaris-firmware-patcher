#!/usr/bin/env python3
"""Extract the reviewed static rate-path facts from an exact Polaris MCU image.

This is an evidence tool, not a firmware patcher and not a protocol client.  It
only accepts the reviewed ``polaris413_2.0.0.22.bin`` image, checks the exact
hash, and reports the instruction/literal facts around the historical
``J``/``0x4A`` handler.  It never writes a binary, opens a socket, or emits a
motion command.

The result narrows the implementation question: the handler takes a float
from the per-axis packet state and computes::

    input_float * axis_scale * 0.0002770000137 / 1000.0

``axis_scale`` is read from the MCU's per-axis state at offset ``0x21c``.  The
static record intentionally does not assign units to that result.  Tick
cadence, state-machine ownership, packet admission, acknowledgements, zero
semantics, and physical degrees/second conversion remain qualification gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


EXPECTED_SHA256 = "34d3f4186185c541adb9c8e57b3e2ec13e402dfb4bb3e9b2262cbf03f1a5c112"
EXPECTED_SIZE = 84_284
IMAGE_NAME = "polaris413_2.0.0.22.bin"
BASE_VA = 0x08000000
HANDLER_VA = 0x0800501C
HANDLER_OFFSET = HANDLER_VA - BASE_VA
LITERAL_SCALE_OFFSET = 0x5180
LITERAL_DIVISOR_OFFSET = 0x5184
LITERAL_COMPARE_OFFSET = 0x5188
EXPECTED_SCALE_WORD = 0x39913A50       # 0.0002770000137388706f
EXPECTED_DIVISOR_WORD = 0x447A0000     # 1000.0f
EXPECTED_COMPARE_WORD = 0xC61C4000     # -10000.0f
AXIS_STRIDE = 0x64
STATE_OFFSET = 0x0D
INPUT_OFFSET = 0x0E
AXIS_SCALE_OFFSET = 0x21C
OUTPUT_STEP_OFFSET = 0x264
OUTPUT_STATE_OFFSET = 0x25C

HANDLER_PREFIX = bytes.fromhex(
    "a07800ebc00101eb001004eb8000407b"
    "9fed548adfed548a544f"
)
FORMULA_SEQUENCE = bytes.fromhex(
    "d0f80e00c5f8600200ee100ad5ed870a"
    "b84260ee200a60ee880a80eea81a85ed991a"
)
STATE3_SEQUENCE = bytes.fromhex(
    "d0f80e104548c0f8601225215170"
)


class StaticAnalysisError(ValueError):
    """The supplied MCU payload is not the exact reviewed image/layout."""


def _read_bytes(data: bytes, offset: int, size: int) -> bytes:
    end = offset + size
    if offset < 0 or end > len(data):
        raise StaticAnalysisError(f"range 0x{offset:x}..0x{end:x} is outside the image")
    return data[offset:end]


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack("<I", _read_bytes(data, offset, 4))[0]


def _word_float(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word))[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_facts(data: bytes) -> dict:
    """Verify the static fingerprints and return the reviewed facts."""

    if len(data) < LITERAL_COMPARE_OFFSET + 4:
        raise StaticAnalysisError("image is too short for the reviewed literal pool")
    if _read_bytes(data, HANDLER_OFFSET, len(HANDLER_PREFIX)) != HANDLER_PREFIX:
        raise StaticAnalysisError("J/0x4A handler prefix differs from the reviewed image")
    if _read_bytes(data, HANDLER_OFFSET + 0xAC, len(FORMULA_SEQUENCE)) != FORMULA_SEQUENCE:
        raise StaticAnalysisError("J/0x4A float conversion sequence differs from the reviewed image")
    if _read_bytes(data, HANDLER_OFFSET + 0x56, len(STATE3_SEQUENCE)) != STATE3_SEQUENCE:
        raise StaticAnalysisError("state-3 forwarding sequence differs from the reviewed image")

    scale_word = _read_u32(data, LITERAL_SCALE_OFFSET)
    divisor_word = _read_u32(data, LITERAL_DIVISOR_OFFSET)
    compare_word = _read_u32(data, LITERAL_COMPARE_OFFSET)
    if scale_word != EXPECTED_SCALE_WORD:
        raise StaticAnalysisError("reviewed scale literal differs from the exact image")
    if divisor_word != EXPECTED_DIVISOR_WORD:
        raise StaticAnalysisError("reviewed divisor literal differs from the exact image")
    if compare_word != EXPECTED_COMPARE_WORD:
        raise StaticAnalysisError("reviewed comparison literal differs from the exact image")
    scale = _word_float(scale_word)
    divisor = _word_float(divisor_word)
    if not (math.isfinite(scale) and math.isfinite(divisor) and scale > 0 and divisor > 0):
        raise StaticAnalysisError("reviewed conversion literals are not positive finite floats")

    return {
        "status": "static-only-unqualified",
        "handler": {
            "va": f"0x{HANDLER_VA:08x}",
            "file_offset": f"0x{HANDLER_OFFSET:08x}",
            "image": IMAGE_NAME,
            "packet_state_axis_stride": AXIS_STRIDE,
            "state_field_offset": STATE_OFFSET,
            "state_field_offset_hex": f"0x{STATE_OFFSET:02x}",
            "input_float_offset": INPUT_OFFSET,
            "input_float_offset_hex": f"0x{INPUT_OFFSET:02x}",
            "state3_forwarded_message_code": "0x25",
        },
        "conversion": {
            "formula": "input_float * axis_scale * literal_scale / literal_divisor",
            "literal_scale": scale,
            "literal_scale_word": f"0x{scale_word:08x}",
            "literal_scale_file_offset": f"0x{LITERAL_SCALE_OFFSET:08x}",
            "literal_divisor": divisor,
            "literal_divisor_word": f"0x{divisor_word:08x}",
            "literal_divisor_file_offset": f"0x{LITERAL_DIVISOR_OFFSET:08x}",
            "compare_word": f"0x{compare_word:08x}",
            "compare_word_as_float": _word_float(compare_word),
            "axis_scale_state_offset": AXIS_SCALE_OFFSET,
            "axis_scale_state_offset_hex": f"0x{AXIS_SCALE_OFFSET:03x}",
            "output_step_state_offset": OUTPUT_STEP_OFFSET,
            "output_step_state_offset_hex": f"0x{OUTPUT_STEP_OFFSET:03x}",
            "output_state_flag_offset": OUTPUT_STATE_OFFSET,
            "output_state_flag_offset_hex": f"0x{OUTPUT_STATE_OFFSET:03x}",
        },
        "interpretation": {
            "established": [
                "The handler reads an axis-selected float input at packet-state offset 0x0e.",
                "The packet-state records use a 0x64-byte per-axis stride.",
                "The float path multiplies by a per-axis value at state offset 0x21c.",
                "The static constants are approximately 0.000277 and 1000.0.",
                "A state-3 path forwards the input to message code 0x25 rather than using this local float calculation.",
            ],
            "not_established": [
                "degrees-per-second units or calibrated motor-step units",
                "the timer cadence represented by the conversion",
                "packet admission, checksum, dispatcher ownership, or acknowledgement",
                "zero-rate hold versus torque release and STOP priority",
                "axis sign/mapping after the full 403/413/astro path",
                "physical rate accuracy or cross-axis isolation",
            ],
        },
        "decision": "retain as a static MCU lead; do not patch, send, or expose AC 4A",
    }


def analyse(path: Path) -> dict:
    if not path.is_file():
        raise StaticAnalysisError(f"MCU image does not exist: {path}")
    size = path.stat().st_size
    if size != EXPECTED_SIZE:
        raise StaticAnalysisError(f"MCU image size {size} != reviewed size {EXPECTED_SIZE}")
    digest = sha256(path)
    if digest != EXPECTED_SHA256:
        raise StaticAnalysisError(f"MCU image SHA-256 {digest} != reviewed {EXPECTED_SHA256}")
    result = extract_facts(path.read_bytes())
    result["gimbal"] = {"path": str(path), "size": size, "sha256": digest}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gimbal", required=True, type=Path, help="exact reviewed MCU image")
    parser.add_argument("--out", type=Path, help="write JSON to this path")
    args = parser.parse_args(argv)
    try:
        rendered = json.dumps(analyse(args.gimbal), indent=2, sort_keys=True) + "\n"
    except (OSError, StaticAnalysisError, struct.error) as exc:
        print(f"[polaris_gimbal_rate_static] FATAL: {exc}", file=sys.stderr)
        return 2
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

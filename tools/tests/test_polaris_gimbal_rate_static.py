import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polaris_gimbal_rate_static import (
    FORMULA_SEQUENCE,
    HANDLER_OFFSET,
    HANDLER_PREFIX,
    LITERAL_COMPARE_OFFSET,
    LITERAL_DIVISOR_OFFSET,
    LITERAL_SCALE_OFFSET,
    STATE3_SEQUENCE,
    StaticAnalysisError,
    extract_facts,
)


def reviewed_fixture() -> bytearray:
    data = bytearray(LITERAL_COMPARE_OFFSET + 4)
    data[HANDLER_OFFSET:HANDLER_OFFSET + len(HANDLER_PREFIX)] = HANDLER_PREFIX
    formula_offset = HANDLER_OFFSET + 0xAC
    data[formula_offset:formula_offset + len(FORMULA_SEQUENCE)] = FORMULA_SEQUENCE
    state3_offset = HANDLER_OFFSET + 0x56
    data[state3_offset:state3_offset + len(STATE3_SEQUENCE)] = STATE3_SEQUENCE
    struct.pack_into("<f", data, LITERAL_SCALE_OFFSET, 0.000277)
    struct.pack_into("<f", data, LITERAL_DIVISOR_OFFSET, 1000.0)
    struct.pack_into("<I", data, LITERAL_COMPARE_OFFSET, 0xC61C4000)
    return data


def test_static_conversion_facts_are_extracted_without_assigning_units():
    facts = extract_facts(bytes(reviewed_fixture()))
    assert facts["conversion"]["literal_scale"] == pytest.approx(0.000277)
    assert facts["conversion"]["literal_divisor"] == pytest.approx(1000.0)
    assert facts["handler"]["packet_state_axis_stride"] == 0x64
    assert facts["decision"].startswith("retain as a static MCU lead")
    assert any("degrees-per-second units" in item for item in facts["interpretation"]["not_established"])


def test_changed_formula_fingerprint_fails_closed():
    data = reviewed_fixture()
    data[HANDLER_OFFSET + 0xAC] ^= 0x01
    with pytest.raises(StaticAnalysisError):
        extract_facts(bytes(data))


def test_changed_conversion_literal_fails_closed():
    data = reviewed_fixture()
    struct.pack_into("<f", data, LITERAL_SCALE_OFFSET, 0.000278)
    with pytest.raises(StaticAnalysisError):
        extract_facts(bytes(data))

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polestar_rate_candidate import (
    DEFAULT_COMMANDS,
    DEFAULT_TARGET_VA,
    TABLE_VA,
    AnalysisError,
    branch_target,
    parse_load_segments,
)


def test_default_slot_targets_common_return():
    # The reviewed word for command 515 is at TABLE_VA + 2 * 4.
    word = 0xEA0004F9
    assert branch_target(TABLE_VA + 8, word) == DEFAULT_TARGET_VA
    assert 515 in DEFAULT_COMMANDS


def test_branch_decoder_rejects_non_branch():
    assert branch_target(TABLE_VA, 0xE3A03000) is None


def test_elf_parser_rejects_non_elf():
    with pytest.raises(AnalysisError):
        parse_load_segments(b"not an ELF")

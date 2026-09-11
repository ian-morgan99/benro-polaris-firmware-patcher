#!/usr/bin/env python3
"""Focused, firmware-free tests for the manual-focus wait-site guard."""

import struct
import unittest

import analyze_pgphoto as subject


class ManualFocusIdleWaitTest(unittest.TestCase):
    def test_finds_exact_structural_site_inside_function(self):
        insns = [
            (0x1000, "mov r0, #500"),
            (0x1004, "bl 0x2000 <waitCameraIdle>"),
        ]
        self.assertEqual(
            subject.find_manual_focus_idle_wait(insns, (0x1000, 0x1100)),
            [0x1000],
        )

    def test_accepts_hex_immediate_rendering(self):
        insns = [
            (0x1000, "mov r0, #0x1f4"),
            (0x1004, "bl 0x2000 <waitCameraIdle>"),
        ]
        self.assertEqual(
            subject.find_manual_focus_idle_wait(insns, (0x1000, 0x1100)),
            [0x1000],
        )

    def test_rejects_outside_nonadjacent_and_wrong_callee(self):
        self.assertEqual(
            subject.find_manual_focus_idle_wait(
                [(0x0FFC, "mov r0, #500"),
                 (0x1000, "bl 0x2000 <waitCameraIdle>")],
                (0x1000, 0x1100),
            ),
            [],
        )

    def test_duplicate_sites_remain_visible_to_fail_closed_caller(self):
        insns = [
            (0x1000, "mov r0, #500"),
            (0x1004, "bl 0x2000 <waitCameraIdle>"),
            (0x1010, "mov r0, #500"),
            (0x1014, "bl 0x2000 <waitCameraIdle>"),
        ]
        self.assertEqual(
            subject.find_manual_focus_idle_wait(insns, (0x1000, 0x1100)),
            [0x1000, 0x1010],
        )
        self.assertEqual(
            subject.find_manual_focus_idle_wait(
                [(0x1000, "mov r0, #500"),
                 (0x1008, "bl 0x2000 <waitCameraIdle>")],
                (0x1000, 0x1100),
            ),
            [],
        )
        self.assertEqual(
            subject.find_manual_focus_idle_wait(
                [(0x1000, "mov r0, #500"),
                 (0x1004, "bl 0x2000 <usleep>")],
                (0x1000, 0x1100),
            ),
            [],
        )

    def test_new_instruction_is_movw_r0_3000(self):
        # Independent byte-level contract. Capstone/build disassembly provides
        # the second decoder gate in the integration test.
        self.assertEqual(struct.pack("<I", subject.MOVW_R0_3000).hex(), "b80b00e3")


if __name__ == "__main__":
    unittest.main()

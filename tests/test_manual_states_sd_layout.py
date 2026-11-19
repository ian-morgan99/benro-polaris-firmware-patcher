#!/usr/bin/env python3
"""The manual must state the post-extract folder layout, and it must match reality.

Offline. Reads the shipped archives' member lists and the two documents that describe
them. No device, no network.

Why this exists: every archive is rooted at its own directory (FwPkt.zip contains
FwPkt/, polaris-astro.zip contains polaris-astro/, and so on). Windows "Extract All"
adds a folder named after the zip and puts the archive's own folder inside it, so the
user gets FwPkt\\FwPkt\\camera\\ instead of FwPkt\\camera\\. The head does not search --
it looks for /app/sd/FwPkt, /app/sd/polaris-astro, /app/sd/polaris-wifi and
/app/sd/astrometry by exact path -- so a doubled folder fails silently: the firmware
never flashes and the version in the app is unchanged, or install_astro.sh reports "No
such file".

The prose already said "extract it there" without ever showing the resulting tree, so
there was nothing to compare the card against. These tests pin three things, because
fixing one and not the others reproduces the complaint:

  1. Both documents show a tree naming all four folders at the SD card root.
  2. The names in that tree are the names the archives actually carry -- a manual that
     drifts from the build output is worse than none, because it teaches a wrong check.
  3. The Windows doubling hazard is stated with its symptom, not just its cause.

The archive-membership half only runs when a built candidate is present; the document
half always runs, so the gate still catches doc-only regressions on a clean checkout.
"""

from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
USER_MANUAL = ROOT / "docs" / "USER-MANUAL.md"
INSTALL_PROCESS = ROOT / "docs" / "FIRMWARE-INSTALL-PROCESS.md"
AGENTS = ROOT / "AGENTS.md"
PUBLISHER = ROOT / "scripts" / "publish-astro-candidate.sh"

# The four folders the head looks for, by exact name, at the SD card root.
SD_ROOT_FOLDERS = ("FwPkt", "polaris-astro", "polaris-wifi", "astrometry")

# Each archive and the single top-level directory it is rooted at.
ARCHIVE_ROOTS = {
    "FwPkt.zip": "FwPkt",
    "polaris-astro.zip": "polaris-astro",
    "polaris-wifi.zip": "polaris-wifi",
    "astrometry-indexes.zip": "astrometry",
}


def _find_candidate():
    """Newest built candidate with its kit archives present, or None."""
    out = ROOT / "out"
    if not out.is_dir():
        return None
    for d in sorted(out.glob("astro-v*-*/"), reverse=True):
        sd = d / "astro-bundle" / "COPY-TO-SD-CARD-ROOT"
        if (d / "FwPkt.zip").is_file() and (sd / "polaris-astro.zip").is_file():
            return d, sd
    return None


class TestManualStatesLayout(unittest.TestCase):
    def test_user_manual_shows_the_extracted_tree(self):
        text = USER_MANUAL.read_text(encoding="utf-8")
        self.assertIn("(SD card root)", text)
        for folder in SD_ROOT_FOLDERS:
            self.assertIn(folder + "/", text)

    def test_user_manual_names_all_four_as_top_level(self):
        # Not merely mentioned: the tree must present them as siblings at the root.
        # The last sibling carries the terminal glyph ('--) rather than |--, so both
        # are accepted -- requiring |-- for all four would reject a correct tree.
        text = USER_MANUAL.read_text(encoding="utf-8")
        block = text[text.index("(SD card root)"):]
        block = block[:block.index("```") if "```" in block else len(block)]
        for folder in SD_ROOT_FOLDERS:
            self.assertTrue(
                ("|-- " + folder + "/") in block or ("'-- " + folder + "/") in block,
                "%s is not shown as a top-level folder" % folder)

    def test_user_manual_states_the_windows_doubling_hazard(self):
        text = USER_MANUAL.read_text(encoding="utf-8")
        self.assertIn("Extract All", text)
        # The symptom, not just the cause: without it the reader cannot tell a doubled
        # folder from an unrelated failure.
        self.assertIn("FwPkt\\FwPkt", text)
        self.assertIn("No such file", text)

    def test_user_manual_gives_a_pre_reboot_check(self):
        # The whole point of documenting the layout is that it can be verified before
        # rebooting, because a silent no-op looks identical to success.
        text = USER_MANUAL.read_text(encoding="utf-8")
        self.assertIn("firmwareInfo", text)


class TestPublisherTemplateStatesLayout(unittest.TestCase):
    """The per-release README is generated from this template, so it must carry the
    same layout -- otherwise the document a user actually follows still omits it."""

    def test_template_contains_the_tree(self):
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("(SD card root)", text)
        for folder in SD_ROOT_FOLDERS:
            self.assertTrue(
                ("|-- " + folder + "/") in text or ("'-- " + folder + "/") in text,
                "%s missing from the published README template" % folder)

    def test_template_warns_about_windows(self):
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("Extract All", text)
        self.assertIn("FwPkt\\FwPkt", text)

    def test_tree_is_indented_not_fenced(self):
        # The README is emitted through an unquoted heredoc. A fenced block containing
        # backticks would be command-substituted, and a line ending in backslash would
        # be swallowed as a continuation -- both corrupt the diagram silently.
        text = PUBLISHER.read_text(encoding="utf-8")
        block = text[text.index("(SD card root)"):]
        block = block[:block.index("4. Run the installer")]
        self.assertNotIn("```", block)
        for line in block.splitlines():
            self.assertFalse(line.rstrip().endswith("\\"),
                             "trailing backslash would be eaten by the heredoc: " + line)


class TestLayoutMatchesBuiltArchives(unittest.TestCase):
    """The documented names must be the names the build actually produces."""

    def test_every_archive_is_rooted_at_the_documented_folder(self):
        found = _find_candidate()
        if found is None:
            self.skipTest("no built candidate with kit archives present")
        build, sd = found
        targets = {
            "FwPkt.zip": build / "FwPkt.zip",
            "polaris-astro.zip": sd / "polaris-astro.zip",
            "polaris-wifi.zip": sd / "polaris-wifi.zip",
            "astrometry-indexes.zip": sd / "astrometry-indexes.zip",
        }
        for name, path in targets.items():
            with zipfile.ZipFile(path) as z:
                tops = {n.split("/")[0] for n in z.namelist() if n.split("/")[0]}
            self.assertEqual(tops, {ARCHIVE_ROOTS[name]},
                             "%s is not rooted at a single documented folder" % name)

    def test_documented_folder_names_appear_in_the_manual(self):
        # Guards against renaming an archive's root without updating the manual.
        text = USER_MANUAL.read_text(encoding="utf-8")
        for folder in ARCHIVE_ROOTS.values():
            self.assertIn(folder + "/", text)

    def test_fwpkt_holds_the_files_the_manual_says_it_holds(self):
        found = _find_candidate()
        if found is None:
            self.skipTest("no built candidate with kit archives present")
        build, _ = found
        with zipfile.ZipFile(build / "FwPkt.zip") as z:
            names = set(z.namelist())
        for required in ("FwPkt/firmwareInfo", "FwPkt/FwVer", "FwPkt/camera/uImage"):
            self.assertIn(required, names)


class TestCardCapacityAssumption(unittest.TestCase):
    """The SD card is assumed to be 1 GB or larger, and no document may present the
    small test card's size as a limit of the head.

    This exists because a previous revision of this file asserted exactly that: it read
    "on a 118 MB filesystem with 115 MB free" in FIRMWARE-INSTALL-PROCESS.md, took the
    118 MB for the device's capacity, and rewrote Route A to forbid extracting all four
    archives together -- claiming they overflow the card and that the watcher therefore
    declines to flash. The figure is one deliberately small test card used to demonstrate
    the errors=continue truncation failure mode; the same section says to read
    `df -k /app/sd` rather than assume. A 1 GB card holds all four payloads (~162 MB, or
    ~175 MB after FAT32 cluster rounding) with room to spare, so the original Route A
    order was correct and has been restored.

    These tests pin the corrected state: the assumption is recorded, the misleading figure
    is qualified where it appears, and neither user-facing document repeats the claim.
    """

    def test_assumption_is_recorded_in_agent_instructions(self):
        # Assert the heading phrase, not the bare string "1 GB": the figure also occurs
        # in the explanatory prose, so a loose check passes even when the standing
        # assumption itself has been removed.
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("SD card is 1 GB or larger", text)
        self.assertIn("df -k /app/sd", text)

    def test_install_process_qualifies_the_small_card_figure(self):
        # The figure may appear -- it documents a real failure mode -- but only alongside
        # the statement that it is one test card, not the head's capacity.
        text = INSTALL_PROCESS.read_text(encoding="utf-8")
        self.assertIn("1 GB", text)
        i = text.index("118 MB filesystem")
        nearby = text[max(0, i - 2500):i + 2500]
        self.assertTrue(
            "not a property of the device" in nearby or "one such small test card" in nearby,
            "the 118 MB figure is presented without qualifying its provenance")

    def test_published_readme_does_not_claim_a_card_limit(self):
        text = PUBLISHER.read_text(encoding="utf-8")
        for phrase in ("118 MB", "about 118", "card the head mounts is"):
            self.assertNotIn(phrase, text,
                             "the per-release README repeats the card-limit claim: %s" % phrase)

    def test_user_manual_does_not_claim_a_card_limit(self):
        text = USER_MANUAL.read_text(encoding="utf-8")
        for phrase in ("118 MB", "only about 118", "two passes"):
            self.assertNotIn(phrase, text,
                             "the user manual repeats the card-limit claim: %s" % phrase)

    def test_route_a_extracts_all_four_before_rebooting(self):
        # With a 1 GB card assumed this is the correct order. Pinned so a future
        # "capacity" rework cannot silently reintroduce phased staging.
        import re
        text = PUBLISHER.read_text(encoding="utf-8")
        block = text[text.index("## Route A"):]
        nums = [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", block, re.M)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)), "step numbering: %s" % nums)
        self.assertIn("2. Copy polaris-astro.zip", block)
        self.assertIn("3. Copy astrometry-indexes.zip", block)
        self.assertIn("4. Run the installer", block)

    def test_step_numbers_are_unique_and_cross_references_resolve(self):
        import re
        text = PUBLISHER.read_text(encoding="utf-8")
        block = text[text.index("## Route A"):]
        nums = [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", block, re.M)]
        self.assertEqual(nums, sorted(set(nums)), "duplicate step number: %s" % nums)
        defined = {str(n) for n in nums}
        for ref in re.findall(r"\bsteps? (\d+)", block):
            self.assertIn(ref, defined, "reference to undefined step %s" % ref)


if __name__ == "__main__":
    unittest.main()

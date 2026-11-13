#!/usr/bin/env python3
"""The host re-exec must not silently drop the documented env overrides.

Offline. Puts a stub `flatpak-spawn` and no `docker` on PATH, runs the real
scripts/release/build-and-install.sh, and asserts the re-exec carries every
override it documents in usage(). No device, no network, no docker.

Why: flatpak-spawn --host starts its child with a fresh environment. The script
re-execs itself through it to reach the host Docker socket, which discarded
CANDIDATE_ID, BUILD_ID, CHANGE_SUMMARY and the rest. CANDIDATE_ID and BUILD_ID
have $(date -u +%Y%m%dT%H%M%SZ) defaults, so the failure was silent: a named
candidate was built under a timestamped identity instead. Observed with
CANDIDATE_ID=astro-v108-starved-extract-20261112, which re-executed as
o-main-20261113T001741Z. Only CHANGE_SUMMARY being mandatory turned that into a
visible error; the other five would have been lost unnoticed.
"""

from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release" / "build-and-install.sh"

# Documented in usage(): "Environment overrides: STOCK_FWPKT LIBGPHOTO_REPO
# CANDIDATE_ID DISPLAY_FWVER BUILD_ID CHANGE_SUMMARY".
DOCUMENTED = [
    "STOCK_FWPKT", "LIBGPHOTO_REPO", "CANDIDATE_ID",
    "DISPLAY_FWVER", "BUILD_ID", "CHANGE_SUMMARY",
]


class EnvForwardingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bai-env-"))
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        # A stub flatpak-spawn that records its argv and exits, so the re-exec is
        # observable without a host or docker.
        rec = self.tmp / "spawn.argv"
        stub = bin_ / "flatpak-spawn"
        stub.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"{}\"\nexit 0\n".format(rec)
        )
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
        self.rec = rec
        self.bin = bin_

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _script_copy(self):
        """The real script, with only its PATH-prepend reordered.

        Line 16 is `export PATH="/usr/bin:/bin:$PATH"`, which puts the real
        /usr/bin/flatpak-spawn ahead of any stub dir on PATH -- shadowing it by
        PATH order is therefore impossible. Reordering to append instead keeps
        every other line identical, so the branch under test still runs for real.
        The copy asserts on the forwarding block's presence: if that code is ever
        removed or renamed, this test fails loudly instead of quietly passing
        against a script that no longer contains it.
        """
        src = SCRIPT.read_text()
        needle = 'export PATH="/usr/bin:/bin:$PATH"'
        self.assertIn(needle, src,
                      "build-and-install.sh no longer prepends /usr/bin to PATH; "
                      "this test's stub-shadowing trick needs updating")
        self.assertIn("SPAWN_ENV", src,
                      "the env-forwarding block is gone from build-and-install.sh")
        copy = self.tmp / "build-and-install.copy.sh"
        copy.write_text(src.replace(needle, 'export PATH="$PATH:/usr/bin:/bin"'))
        return copy

    def _run(self, overrides):
        env = dict(os.environ)
        # Stub dir first; the reordered PATH in the copy keeps it first.
        env["PATH"] = str(self.bin) + ":/usr/bin:/bin"
        env.pop("DOCKER_HOST", None)
        for k in DOCUMENTED:
            env.pop(k, None)
        env.update(overrides)
        subprocess.run(["bash", str(self._script_copy())], env=env,
                       capture_output=True, text=True, timeout=120)
        if not self.rec.exists():
            return []
        return [ln.strip() for ln in self.rec.read_text().splitlines() if ln.strip()]

    def test_every_documented_override_is_forwarded(self):
        wanted = {
            "STOCK_FWPKT": "/tmp/stock",
            "LIBGPHOTO_REPO": "https://example.invalid/lgpl.git",
            "CANDIDATE_ID": "astro-v108-starved-extract-20261112",
            "DISPLAY_FWVER": "auto",
            "BUILD_ID": "auto",
            "CHANGE_SUMMARY": "docs/release-change-summary-v108-astro.json",
        }
        argv = self._run(wanted)
        got = {a.split("=", 1)[1] for a in argv if a.startswith("--env=")}
        for name, value in wanted.items():
            self.assertIn(f"{name}={value}", got,
                          f"{name} was dropped by the host re-exec")

    @staticmethod
    def _env_map(argv):
        out = {}
        for a in argv:
            if a.startswith("--env="):
                name, _, value = a[len("--env="):].partition("=")
                out[name] = value
        return out

    def test_candidate_id_survives_the_reexec(self):
        """The specific silent failure: a named candidate becoming a timestamp."""
        got = self._env_map(self._run(
            {"CANDIDATE_ID": "astro-v108-starved-extract-20261112"}))
        self.assertEqual(got.get("CANDIDATE_ID"),
                         "astro-v108-starved-extract-20261112")

    def test_caller_value_wins_over_the_script_default(self):
        """The script assigns ${VAR:-default} before the re-exec, so every one of
        the six is set by the time the forwarding block runs. What matters is that
        a caller-supplied value is what reaches the host, not the default -- and
        that the defaults themselves are preserved rather than recomputed against
        an empty environment."""
        got = self._env_map(self._run({"CANDIDATE_ID": "named-candidate"}))
        self.assertEqual(got.get("CANDIDATE_ID"), "named-candidate")
        # STOCK_FWPKT was not set by the caller; the script's own default must
        # still reach the host intact rather than arriving empty.
        self.assertTrue(got.get("STOCK_FWPKT", "").startswith("/"),
                        "STOCK_FWPKT default was lost across the re-exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)

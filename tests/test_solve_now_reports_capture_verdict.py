#!/usr/bin/env python3
"""#364: solve-now.sh must report the head's capture verdict, not just "no frame".

Offline. The shipped solve-now.sh is driven with a stub polaris-mount that emits
replies in the exact format the real binary produces (verified on 192.168.68.25:
`send --listen 3` prints `264@state:1#`, then streams 778/775 battery-and-storage
telemetry between answers). Three cases, each asserting the *diagnosis* the log
gives, because that is what decides where a human looks next:

  accepted   -> frame appears, solve proceeds
  rejected   -> log says REJECTED and quotes the error code
  silent     -> log says nothing was heard within the listen window

Why this exists. Before the fix the send call was:

    "$ASTRO/polaris-mount" ... send --msg '1&264&2&state:1;...' >/dev/null 2>&1

Two independent bugs in one line. polaris-mount's listen_s defaults to 0
(polaris-mount.c:441), so without --listen it writes the command and exits
without reading a single reply -- the head's answer was never even received. And
>/dev/null 2>&1 would have thrown it away had it been. The only message on
failure was "no frame appeared in ${WAIT}s", which is indistinguishable from a
slow camera.

Measured on the live head: opcode 264 was answered `state:-1005` while the log
read only "no frame appeared in 25s". That sent the investigation toward capture
timing; the actual answer was an error code the script had already discarded.
-1005 is intermittent -- the same command minutes later returned state:1 and
produced SP_0041.jpg -- so it can only be diagnosed if the reply is recorded at
the moment it happens.

The rejection case must NOT be reported as a timeout: a refusal needs protocol
work, a timeout needs a longer wait, and printing one message for both guarantees
the wrong fix gets tried first.
"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOLVE_NOW = REPO / "container" / "astro" / "ondisk" / "solve-now.sh"


STUB_MOUNT = """#!/bin/sh
# Emits what polaris-mount send --listen prints, in its real format.
case "$REPLY_MODE" in
  accept)
    printf '264@state:1#\\n'
    printf '778@capacity:100;charge:2;#\\n'
    ;;
  reject)
    printf '264@state:-1005#\\n'
    printf '778@capacity:100;charge:2;#\\n'
    ;;
  telemetry-only)
    printf '778@capacity:100;charge:2;#\\n'
    printf '775@status:1;totalspace:59978;#\\n'
    ;;
esac
exit 0
"""

STUB_ALIGN = """#!/bin/sh
echo "SOLVED {\"ra\":1,\"dec\":2}"
exit 0
"""


def _write(path, text, executable=True):
    path.write_text(text)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class SolveNowReply(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.astro = self.tmp / "astro"
        self.astro.mkdir()
        _write(self.astro / "polaris-mount", STUB_MOUNT)
        _write(self.astro / "polaris-align.sh", STUB_ALIGN)
        # newest_frame() scans these; point it at a temp dir by running with a
        # HOME-scoped copy of the directory list is not possible, so instead we
        # rely on the script's own paths and only assert on stderr diagnostics.
        self.sd = Path("/app/sd/normal")

    def _run(self, mode, wait=1):
        env = dict(os.environ)
        env.update({
            "REPLY_MODE": mode,
            "LAT": "55.95",
            "LON": "-3.19",
            # solve-now.sh reads WAIT=${CAPTURE_WAIT:-25}; setting WAIT directly
            # is overwritten by that assignment.
            "CAPTURE_WAIT": str(wait),
            "ASTRO": str(self.astro),
        })
        return subprocess.run(
            ["sh", str(SOLVE_NOW)], env=env, capture_output=True, text=True,
            timeout=wait + 25,
        )

    def test_rejection_is_reported_as_rejection(self):
        """The core regression: an error code must not print as a timeout."""
        r = self._run("reject", wait=2)
        err = r.stderr
        self.assertIn("REJECTED", err,
                      "a head refusal printed as a plain timeout -- this is the "
                      "#364 masking bug; the -1005 code was discarded and the "
                      "log pointed at capture timing instead")
        self.assertIn("-1005", err,
                      "the error code itself must reach the log; without it "
                      "there is nothing to look up")
        self.assertNotIn("no frame appeared", err,
                         "rejection and timeout must not share a message")

    def test_silence_is_reported_as_silence(self):
        """No 264 answer at all must say so, distinctly from both other cases."""
        r = self._run("telemetry-only", wait=2)
        err = r.stderr
        self.assertIn("head replied", err,
                      "the reply line is the only evidence of what the head said")
        self.assertIn("<nothing within 3s>", err,
                      "telemetry-only must be distinguishable from a real answer")
        self.assertNotIn("REJECTED", err,
                         "no answer is not a refusal")

    def test_reply_is_captured_even_on_success(self):
        """The verdict must be logged regardless of outcome, for the audit trail."""
        r = self._run("accept", wait=2)
        self.assertIn("head replied: 264@state:1#", r.stderr,
                      "success path must still record what the head answered; "
                      "intermittent failures are diagnosed from successful runs' "
                      "baselines")

    def test_listen_flag_is_used(self):
        """Without --listen polaris-mount never reads a reply (listen_s=0)."""
        src = SOLVE_NOW.read_text()
        self.assertIn("--listen", src,
                      "send without --listen exits before reading any reply; "
                      "capturing stdout would then always be empty")

    def test_old_masking_pattern_is_gone(self):
        """Guard against the exact regression: discarding send's output."""
        src = SOLVE_NOW.read_text()
        for line in src.splitlines():
            if "send" in line and "--msg" in line and "264" in line:
                self.assertNotIn(">/dev/null", line,
                                 "send's reply must not be discarded: " + line.strip())


if __name__ == "__main__":
    unittest.main()

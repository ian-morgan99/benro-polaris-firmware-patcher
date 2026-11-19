#!/usr/bin/env python3
"""The running build must be visible in the web UI without clicking anything.

Offline. Parses the shipped index.html and app.js rather than reimplementing them,
so it fails if either file stops agreeing with the other. No device, no network,
no browser.

Why this exists: /api/version already returned build_id, firmware_version_expected,
firmware_version_actual and aligned -- but the only thing that consumed it was
deviceRefresh(), which runs when you open the Device panel and press Refresh. So
the answer to "which build is on this head" was one deliberate click away in a UI
whose whole job is to be glanceable at the scope in the dark, and after a flash the
control link is usually down while :8090 is already up -- precisely when you want
the answer and least able to go looking for it.

Three separate failures this pins, because fixing one and not the others reproduces
the original complaint:

  1. The chip must be in the always-visible header, not inside a tab. The header is
     the only element the app documents as never hidden.
  2. It must be fetched at boot. A chip that exists but is only populated behind a
     click is indistinguishable from no chip -- it renders empty and hidden.
  3. A kit/appfs mismatch must be visibly distinct, not just present. The endpoint
     computes `aligned`; printing the version in neutral styling when aligned is
     false would show a wrong pairing as if it were fine.

It also pins that both names of the release are shown. astro-vNNN and 6.0.0.54.NNN
are one number rendered twice; showing only one is what let v113 ship as .111 and
have nobody notice, because each looked self-consistent on its own.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "container" / "astro" / "webui"


def _header():
    html = (WEBUI / "index.html").read_text()
    match = re.search(r"<header id=\"bar\">(.*?)</header>", html, re.DOTALL)
    assert match, "no <header id=\"bar\"> in index.html"
    return match.group(1)


class TestVersionChipMarkup(unittest.TestCase):
    def test_chip_is_in_the_always_visible_header(self):
        header = _header()
        self.assertIn('id="fwver"', header)

    def test_chip_starts_hidden(self):
        # Empty until the fetch resolves. A chip that renders blank is worse than
        # none: it reads as "version unknown" with no explanation.
        header = _header()
        tag = re.search(r"<span id=\"fwver\"[^>]*>", header).group(0)
        self.assertIn("hidden", tag)


class TestVersionChipIsFetchedAtBoot(unittest.TestCase):
    def test_refresh_is_called_from_boot_wiring(self):
        app = (WEBUI / "app.js").read_text()
        boot = app[app.index("/* ──────────────────────────────── boot"):]
        self.assertIn("fwverRefresh();", boot)

    def test_chip_populator_fetches_the_endpoint_itself(self):
        # Must not reuse deviceRefresh(): that returns early when the control link
        # is down, and after a flash the link is down while :8090 is already up.
        app = (WEBUI / "app.js").read_text()
        body = app[app.index("function fwverRefresh()"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("fetch('/api/version'", body)
        self.assertNotIn("if (S.link", body)

    def test_mismatch_is_rendered_as_an_error_not_plain_text(self):
        app = (WEBUI / "app.js").read_text()
        body = app[app.index("function fwverRefresh()"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("'chip err'", body)
        self.assertIn("d.aligned === false", body)

    def test_both_names_of_the_release_are_shown(self):
        # vNNN from build_id and the display version from /app/FwVer, together.
        app = (WEBUI / "app.js").read_text()
        body = app[app.index("function fwverRefresh()"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("parts.push('v' + vnum)", body)
        self.assertIn("parts.push(act)", body)

    def test_drift_between_the_two_names_is_warned_not_shown_as_normal(self):
        # v113 shipped as .111. If the chip had printed that in neutral styling it
        # would have looked correct. The mismatch must be visible on its own terms.
        app = (WEBUI / "app.js").read_text()
        body = app[app.index("function fwverRefresh()"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("'chip warn'", body)


class TestEndpointStillFeedsTheChip(unittest.TestCase):
    def test_httpd_serves_the_fields_the_chip_reads(self):
        src = (ROOT / "container" / "astro" / "polaris-httpd.c").read_text()
        for field in ("build_id", "firmware_version_expected",
                      "firmware_version_actual", "aligned"):
            self.assertIn(field, src)


if __name__ == "__main__":
    unittest.main()

"""The bundle README must not tell users to run scp.

Why this exists
---------------
docs/RELEASE-ENTRYPOINTS.md states, binding: "scp does not work against this
device: its sshd has no sftp-server subsystem, so scp dies with
`scp: Connection closed` and legacy `scp -O` hangs."

build-astro.sh generates the README.txt that ships at the top of every astro
bundle, and until 2026-11-12 it contained:

    Over ssh instead of sneakernet, the same layout works:

        scp -r COPY-TO-SD-CARD-ROOT/. root@<polaris ip>:/app/sd/

That is presented as a working instruction. It is not. Every bundle ever shipped
told users to run a command that cannot succeed on this hardware, and the
surrounding text asserted it "works". tests/test_astro_kit_install_entrypoint.py
already forbids scp inside the staging scripts; nothing covered the prose we ship
to users, which is how it survived.

These tests parse the heredoc that produces README.txt rather than grepping the
whole file, so a comment in build-astro.sh explaining why scp is wrong does not
trip them -- only text that actually reaches the bundle does.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "build-astro.sh"


def readme_heredoc() -> str:
    """Return the literal text written to $OUT/README.txt by build-astro.sh."""
    lines = BUILDER.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r'^cat > "\$OUT/README\.txt" <<\w+$', line.strip()):
            start = i + 1
            break
    assert start is not None, "could not find the README.txt heredoc in build-astro.sh"
    body = []
    for line in lines[start:]:
        if line.strip() == "EOF":
            return "\n".join(body)
        body.append(line)
    raise AssertionError("README.txt heredoc is not terminated by EOF")


def test_readme_does_not_instruct_scp():
    text = readme_heredoc()
    # Match only a real transfer: scp with a source AND a destination. Prose that
    # names scp to explain why it cannot work (e.g. 'legacy `scp -O` hangs') must
    # not trip this, so a bare flag mention is not enough -- there has to be a
    # host:/path or an absolute/relative path argument.
    patterns = (
        r"(?<![\w/-])scp\s+[^\n]*\S+@\S+:\S",   # scp [flags] user@host:/dest
        r"(?<![\w/-])scp\s+-[rR]\s",            # recursive copy, the failure mode used
    )
    hits = [p for p in patterns if re.search(p, text)]
    assert not hits, (
        "the shipped README.txt must not contain a runnable scp command; scp cannot "
        "work against this device (no sftp-server subsystem). Matched: %r" % hits
    )


def test_readme_names_the_supported_ssh_path():
    """Removing scp without replacing it would leave users with no ssh route."""
    text = readme_heredoc()
    assert "install-astro-kit.sh" in text, (
        "the README must point at scripts/release/install-astro-kit.sh as the ssh "
        "path, not just delete the broken one"
    )


def test_readme_does_not_claim_scp_works():
    text = readme_heredoc()
    lowered = text.lower()
    # The original wording promised the layout "works" right before an scp line.
    assert "the same layout works" not in lowered, (
        "stale claim: this paragraph introduced a command that cannot succeed"
    )


def test_readme_still_documents_the_card_route():
    """The offline path must remain documented so the README is still usable."""
    text = readme_heredoc()
    assert "COPY-TO-SD-CARD-ROOT" in text, "the card-copy route must still be described"
    assert "site.conf" in text and "LAT" in text, (
        "LAT/LON are required and cannot be guessed; the README must keep saying so"
    )

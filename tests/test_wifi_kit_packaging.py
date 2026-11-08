"""The station-mode wifi kit must ship everything its own scripts invoke.

Issue #280: polaris-autojoin.sh and polaris-apsta.sh both call
`udhcpc -s "$WDIR/udhcpc.script"`, but build-astro.sh copied only five named
scripts into polaris-wifi/, so the DHCP bind hook was never in the bundle.
BusyBox udhcpc configures nothing itself -- it obtains a lease and hands it to
the script named by -s. With that file absent the lease is granted and silently
discarded, so auto-join associates, the log says "lease obtained", and the
interface has no address and no default route. Every release from b367ed8 to
caab172 shipped this.

These tests are static for the same reason the existing build-wrapper tests are:
the failure is a packaging omission, and it is visible in the text of the
scripts long before anything is built or deployed.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOW_LEVEL = ROOT / "build-astro.sh"
WRAPPER = ROOT / "scripts" / "build-astro-bundle.sh"
ONDISK = ROOT / "container" / "astro" / "ondisk"
WIFI_SCRIPTS = ("polaris-autojoin.sh", "polaris-apsta.sh")


def _wifi_copy_list(text: str) -> set[str]:
    """Return the ondisk filenames build-astro.sh copies into polaris-wifi/."""
    m = re.search(r"for s in ([^;]*); do cp \"/opt/patcher/astro/ondisk/\$s\" "
                  r"/out/COPY-TO-SD-CARD-ROOT/polaris-wifi/", text)
    assert m, "could not find the polaris-wifi copy loop in build-astro.sh"
    return set(m.group(1).split())


def test_dhcp_bind_hook_is_shipped_in_the_wifi_kit():
    assert "udhcpc.script" in _wifi_copy_list(LOW_LEVEL.read_text())


def test_every_file_the_wifi_scripts_invoke_is_shipped():
    """Catch the general class, not just udhcpc.script.

    A wifi script that references "$WDIR/<name>" where <name> is a file we
    maintain in container/astro/ondisk/ must have that file copied into the kit,
    or the device gets a script calling something it will never have.

    Deliberately scoped to names that exist in ondisk: the same references also
    cover the four cross-compiled binaries (copied by build_wifi.sh, not from
    ondisk) and files generated at runtime (.autojoin.conf, .wpa-pinned.conf,
    the logs), neither of which belongs in the copy list.
    """
    shipped = _wifi_copy_list(LOW_LEVEL.read_text())
    for name in WIFI_SCRIPTS:
        body = (ONDISK / name).read_text()
        for ref in re.findall(r'"\$WDIR/([A-Za-z0-9_.-]+)"', body):
            if not (ONDISK / ref).is_file():
                continue
            assert ref in shipped, (
                f"{name} references $WDIR/{ref}, which exists in "
                f"container/astro/ondisk/, but build-astro.sh does not copy it "
                f"into polaris-wifi/"
            )


def test_bind_hook_is_executable_and_gated_in_both_builders():
    # chmod 755 "$SD_WIFI"/*.sh would miss it -- udhcpc.script has no .sh suffix.
    low = LOW_LEVEL.read_text()
    assert 'chmod 755 "$SD_WIFI"/*.sh "$SD_WIFI"/udhcpc.script' in low
    assert '[ -x "$SD_WIFI/udhcpc.script" ]' in low

    # The release wrapper must fail closed on it too, and must verify the mode
    # stored inside the zip rather than trusting the staging directory.
    wrap = WRAPPER.read_text()
    assert 'bundle is missing polaris-wifi/udhcpc.script' in wrap
    assert "iw polaris-autojoin.sh setup-wifi.sh udhcpc.script" in wrap


def test_bind_hook_applies_dns_as_well_as_the_address():
    """Issue #281: the hook applied ip/router but never $dns.

    BusyBox udhcpc exports $dns alongside $ip/$router/$subnet and nothing else
    on this firmware consumes it -- there is no /etc/resolv.conf and no
    /usr/share/udhcpc/default.script to fall back on, so a joined network could
    reach raw IPs and resolve no names.
    """
    body = (ONDISK / "udhcpc.script").read_text()
    assert 'for ns in $dns' in body
    assert "nameserver $ns" in body
    # deconfig must undo it: unreachable nameservers make lookups hang instead
    # of failing fast, which is worse than the shipped state of no resolver.
    deconfig = body.split("deconfig)", 1)[1].split(";;", 1)[0]
    assert "rm -f" in deconfig and "$MARK" in deconfig


def test_unchanged_lease_writes_nothing_to_flash():
    """The renew guard must compare before writing, not after.

    The first version wrote a temp file and only then ran cmp, so every renew hit
    UBIFS anyway -- roughly hourly on a two-hour lease. That is the exact cost the
    guard was added to avoid, and it was invisible unless you read the order of
    operations. The comparison must therefore be against an in-memory string.
    """
    body = (ONDISK / "udhcpc.script").read_text()
    fn = body.split("write_resolv() {", 1)[1].split("\n}", 1)[0]
    write_at = fn.index("> \"$TMPRESOLV\"")
    compare_at = fn.index('= "$(cat "$RESOLV"')
    assert compare_at < write_at, (
        "write_resolv() touches flash before comparing; an unchanged lease "
        "would rewrite resolv.conf on every renew"
    )
    assert "cmp -s" not in fn, "cmp against a freshly written temp file proves nothing"


def test_resolver_failure_is_not_reported_as_success():
    """A failed replace must surface, not fall through with status 0."""
    body = (ONDISK / "udhcpc.script").read_text()
    fn = body.split("write_resolv() {", 1)[1].split("\n}", 1)[0]
    assert 'if ! mv "$TMPRESOLV" "$RESOLV"' in fn
    assert "return 1" in fn
    # The caller must branch on it and say so in the log, rather than printing the
    # offered servers as though they had been applied.
    bound = body.split("bound|renew)", 1)[1].split(";;", 1)[0]
    assert "if write_resolv; then" in bound
    assert "FAILED to write" in bound


def test_bind_hook_survives_busybox_sh():
    import subprocess

    script = ONDISK / "udhcpc.script"
    r = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

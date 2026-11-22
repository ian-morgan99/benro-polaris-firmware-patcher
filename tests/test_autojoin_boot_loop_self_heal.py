"""polaris-autojoin.sh must stop a boot loop by itself (issue #375 REQ-3 family).

Reproduced on the device: entering home credentials in the dashboard writes
wpa.conf and creates /app/sd/polaris-wifi/autojoin. The next boot runs this
script, which moves the AP off its own channel (stock: 5 GHz ch36) onto the home
network's channel and restarts hostapd, because the CYW43455 has ONE radio and
associating a station off-channel crashes it. If that transition crashes the
firmware the device reboots into the SAME path -- the flag is still on the card,
so boot runs the script again, which moves the AP again, which crashes again.

Nothing counted those attempts. A single bad credential set therefore produced an
endless loop with no way back in: the AP never stayed up long enough to reach the
dashboard, and the only recovery was pulling the microSD by hand. That is the
state this repo's own master issue says must not happen to a customer device.

Second defect found while fixing the first: when association is abandoned after
the AP has already been moved, the script called purge() but never restore_ap().
The operator was left on a channel they never chose, with the original config
sitting unread in hostapd.conf.autojoin-bak.

Design notes on the stubs:
  * iw and wpa_supplicant are invoked as "$WDIR/<name>", so the test supplies
    them inside WIFI_DIR -- no PATH games needed for the two binaries that
    actually touch the radio.
  * sleep is stubbed on PATH. It is not a shell builtin, so unlike `kill` (see
    test_apsta_down_stops_station.py) a PATH stub genuinely intercepts it. This
    keeps the retry/backoff loop instant without weakening what is asserted.
  * ps is stubbed to declare which processes exist, because the AP-restart check
    asks for hostapd and purge() asks for wpa_supplicant.
Nothing here touches a real interface: no radio, no hostapd, no /app.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "container" / "astro" / "ondisk" / "polaris-autojoin.sh"


def _stub(dir_: Path, name: str, body: str) -> Path:
    p = dir_ / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)
    return p


@pytest.fixture
def env(tmp_path):
    """A fake card, a fake hostapd.conf and stubs for the radio tooling."""
    wdir = tmp_path / "polaris-wifi"
    wdir.mkdir()

    hap = tmp_path / "hostapd.conf"
    hap.write_text("interface=wlan0\nssid=polestar_001\nchannel=36\nhw_mode=a\n")

    (wdir / "wpa.conf").write_text(
        'ctrl_interface=/var/run/wpa_supplicant\nnetwork={\n\tssid="HomeNet"\n'
        '\tpsk="whatever"\n}\n')

    # Default: the home network is NOT visible in a scan, so the script gives up
    # before it ever rewrites hostapd.conf. Tests that need the AP-move path
    # replace iw with one that reports a 2.4 GHz BSS.
    _stub(wdir, "iw", 'exit 0')
    _stub(wdir, "wpa_supplicant", 'exit 0')

    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub(bindir, "sleep", 'exit 0')
    _stub(bindir, "ifconfig", 'exit 0')
    _stub(bindir, "ps", 'echo "  1 root /bin/sh"')
    _stub(bindir, "udhcpc", 'exit 0')

    e = dict(os.environ)
    e.update({
        "WIFI_DIR": str(wdir),
        "HOSTAPD_CONF": str(hap),
        "AUTOJOIN_TRIES": "1",
        "AUTOJOIN_MAX_BOOTS": "3",
        "PATH": f"{bindir}:{e['PATH']}",
    })
    return e, wdir, hap


def _run(env):
    e, _, _ = env
    return subprocess.run(["sh", str(SCRIPT)], env=e, capture_output=True, text=True)


def _counter(wdir: Path) -> str | None:
    f = wdir / "autojoin-bootcount"
    return f.read_text().strip() if f.is_file() else None


def test_counter_persists_across_restarts(env):
    """The count must survive a reboot, because that is what a crash causes.

    This is the whole mechanism: a hard crash never reaches a failure branch, so
    the only way to see it is a number written before the radio is touched and
    read back after the device comes again.
    """
    e, wdir, _ = env
    _run(env)
    assert _counter(wdir) == "1", "first boot must record attempt 1"
    _run(env)
    assert _counter(wdir) == "2", "second boot must add to the first, not reset it"


def test_counter_is_on_the_card_not_tmp(env):
    """The counter must live on the microSD.

    /tmp is tmpfs: a crash-reboot wipes it, which would reset the count to zero
    every cycle and make the guard permanently unable to trip. appfs is 83% full
    and holds the payload being protected.
    """
    e, wdir, _ = env
    _run(env)
    assert (wdir / "autojoin-bootcount").is_file(), \
        "counter must be on the card, where it survives a crash-reboot"


def test_repeated_failures_disable_autojoin_and_restore_ap(env):
    """After MAX_BOOTS failed boots: disarm, restore the AP, and stop touching it.

    This is the recovery the device needed by hand. The flag is removed FIRST so
    the next boot never runs this script again -- otherwise the restore below
    would just be undone by another join attempt.
    """
    e, wdir, hap = env
    (wdir / "autojoin").write_text("1\n")

    for _ in range(3):
        _run(env)
    assert _counter(wdir) == "3", f"expected 3 recorded boots, got {_counter(wdir)}"

    r = _run(env)
    assert r.returncode == 8, f"4th boot must bail out, rc={r.returncode}\n{r.stdout}"
    assert not (wdir / "autojoin").is_file(), \
        "the autojoin flag must be removed so the next boot does not retry"
    assert _counter(wdir) is None, "counter must be cleared once disarmed"

    log = (wdir / "autojoin.log").read_text()
    assert "disabling auto-join" in log, log
    assert "AP will start normally next boot" in log, log


def test_disarm_clears_the_credentials_that_caused_the_loop(env):
    """Disarming removes wpa.conf as well as the flag.

    Removing the flag alone breaks the immediate loop, but the credential file is
    what drove the AP onto a channel this single-radio chip cannot survive.
    Leaving it behind means anything that reads it again -- re-enabling auto-join
    from the dashboard, or a manual `apsta up` -- replays the identical crash,
    and by then the counter has been cleared, so the guard starts counting from
    zero and burns three more boots before disarming again. Clearing the file
    makes the recovery terminal instead of deferred.

    The cost is retyping the password, which is trivial once the AP is reachable
    -- and a reachable AP is exactly what this branch restores.
    """
    e, wdir, _ = env
    (wdir / "autojoin").write_text("1\n")
    conf = wdir / "wpa.conf"

    for _ in range(4):
        _run(env)

    assert not (wdir / "autojoin").is_file(), "disarm must remove the flag"
    assert not conf.is_file(), "disarm must clear the credentials that caused it"
    log = (wdir / "autojoin.log").read_text()
    assert "credentials cleared" in log, f"the clearing must be logged:\n{log}"


def test_ap_is_restored_when_association_is_abandoned(env, tmp_path):
    """A failed join must put the AP back on the channel it started on.

    The script moves the AP to the home network's channel to make association
    possible. If the association is then abandoned, that move was paid for
    nothing and the operator is left on a channel they never chose -- previously
    purge() ran and restore_ap() did not.
    """
    e, wdir, hap = env

    # iw now reports HomeNet on 2437 MHz (channel 6), so the AP must move off 36.
    _stub(wdir, "iw", 'echo "BSS 00:11:22:33:44:55(on wlan1)"; '
                     'echo "\tfreq: 2437"; echo "\tsignal: -50 dBm"; '
                     'echo "\tSSID: HomeNet"; exit 0')
    # hostapd "restarts" successfully, so the script proceeds to associate.
    _stub(bind := Path(e["PATH"].split(":")[0]), "ps",
          'echo " 42 root ./hostapd -B /app/wifi/hostapd.conf"')
    # wpa_supplicant starts but never associates -> give-up path.
    _stub(wdir, "wpa_supplicant", 'exit 0')

    r = _run(env)
    assert r.returncode == 7, f"expected give-up, rc={r.returncode}\n{r.stdout}"

    log = (wdir / "autojoin.log").read_text()
    assert "moving it to 6" in log, f"AP should have moved: {log}"
    assert "AP restored to its original configuration" in log, \
        f"a failed join must put the AP back:\n{log}"
    assert "channel=36" in hap.read_text(), \
        f"hostapd.conf must be back on its original channel:\n{hap.read_text()}"


def test_success_clears_the_counter(env):
    """A working join must reset the counter.

    Leaving it set means a later, unrelated reboot that fails for some other
    reason could trip the guard and silently disable an auto-join that works.
    """
    e, wdir, hap = env
    _stub(wdir, "iw", 'echo "BSS 00:11:22:33:44:55(on wlan1)"; '
                      'echo "\tfreq: 2437"; echo "\tsignal: -50 dBm"; '
                      'echo "\tSSID: HomeNet"; exit 0')
    _stub(Path(e["PATH"].split(":")[0]), "ps",
          'echo " 42 root ./hostapd -B /app/wifi/hostapd.conf"')
    # Associates immediately.
    _stub(wdir, "wpa_supplicant",
          f'echo CTRL-EVENT-CONNECTED >> "{wdir}/wpa-autojoin.log"; exit 0')
    _stub(Path(e["PATH"].split(":")[0]), "ifconfig", 'echo "inet addr:10.0.0.5"')

    (wdir / "autojoin-bootcount").write_text("2\n")
    r = _run(env)
    assert r.returncode == 0, f"join should succeed:\n{r.stdout}\n{r.stderr}"
    assert _counter(wdir) is None, "a successful join must clear the boot counter"


def test_no_credentials_is_not_counted_as_a_failure(env):
    """With nothing configured the script must stay silent and harmless.

    Boot runs it whenever the flag exists; if a card has the flag but no
    wpa.conf that is not a crash and must not march toward disarming.
    """
    e, wdir, _ = env
    (wdir / "wpa.conf").unlink()
    r = _run(env)
    assert r.returncode == 0, f"absent config must exit 0, rc={r.returncode}"
    assert _counter(wdir) is None, "nothing was attempted, so nothing failed"

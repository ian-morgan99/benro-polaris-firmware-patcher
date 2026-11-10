"""polaris-apsta.sh down must actually stop the station (issue #283).

Reproduced on the device: `down` reported success and printed "AP untouched",
while a boot-time auto-join's wpa_supplicant and udhcpc kept running. `up` then
could not recover -- scanning returned EBUSY because the supplicant still held
the control socket.

Cause: sta_down() killed only /tmp/apsta-wpa.pid and /tmp/apsta-dhcp.pid, but
polaris-autojoin.sh starts its OWN pair under /tmp/autojoin-wpa.pid and
/tmp/autojoin-dhcp.pid. So `down` removed the interface out from under two live
processes. Second defect: nothing ever sent udhcpc a `deconfig`, so the dead
lease's nameservers stayed in /etc/resolv.conf and every lookup hung on timeout.

Design note on `kill`: it is a shell builtin, so putting a stub earlier in PATH
does NOT intercept it -- the builtin wins and the real signal goes out. (Checked:
a PATH stub for kill was bypassed entirely.) Stubbing it would have been both
ineffective and unsafe. Instead these tests spawn real children they own, point
the pidfiles at them, and assert those children are actually dead afterwards. The
kill is genuinely exercised, only ever against processes this test started, and a
regression that skips the kill is caught by an alive process rather than by a
missing log line.

`ps` is not a builtin, so it is stubbed -- that is how a test declares which
command line each pid claims, which the recycled-pid safety check needs.
"""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "container" / "astro" / "ondisk" / "polaris-apsta.sh"

PIDFILES = (
    "apsta-wpa.pid", "apsta-dhcp.pid",
    "autojoin-wpa.pid", "autojoin-dhcp.pid",
)


def stub_ps(table_path):
    """`ps` reporting a fixed pid -> command-line table.

    sta_down() greps the ps output for the process name before signalling, so
    this table is how a test says "this pid really is the supplicant" or "this
    pid has been recycled by sshd".
    """
    return (
        "#!/bin/sh\n"
        'echo "  PID  USER  TIME  COMMAND"\n'
        f'cat "{table_path}" 2>/dev/null\n'
        "exit 0\n"
    )


STUB_IFCONFIG = '#!/bin/sh\necho "ifconfig $*" >> "$STUB_DIR/ifconfig.txt"\nexit 0\n'


@pytest.fixture()
def env(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    table = tmp_path / "pslist.txt"
    table.write_text("")
    for name, body in (("ps", stub_ps(table)), ("ifconfig", STUB_IFCONFIG)):
        p = stub / name
        p.write_text(body)
        p.chmod(0o755)

    wdir = tmp_path / "wifi"
    wdir.mkdir()
    shutil.copy(SCRIPT, wdir / "polaris-apsta.sh")
    # sta_down calls "$WDIR/iw", not `iw` from PATH, so the kit copy has to do
    # the recording or the interface teardown is invisible.
    (wdir / "iw").write_text('#!/bin/sh\necho "iw $*" >> "$STUB_DIR/iw.txt"\nexit 0\n')
    (wdir / "iw").chmod(0o755)

    resolv = tmp_path / "resolv.conf"
    # Exactly what udhcpc.script writes.
    resolv.write_text("# added by polaris-wifi udhcpc.script\nnameserver 192.168.1.1\n")

    children = []
    yield {"stub": stub, "wdir": wdir, "resolv": resolv, "tmp": tmp_path,
           "table": table, "children": children}
    for c in children:
        try:
            os.kill(c.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass


def spawn_process(env):
    """Start a real long-lived child we own, and return its pid."""
    child = subprocess.Popen(
        ["/bin/sleep", "300"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    env["children"].append(child)
    return child.pid


def alive(env, pid):
    """True only for a genuinely running process.

    A killed child stays in the process table as a zombie until its parent reaps
    it, so os.kill(pid, 0) keeps succeeding after a perfectly good kill. Without
    reaping, these tests would report that a working fix stopped nothing. poll()
    reaps; /proc state Z is checked too, because poll() only updates on the call.
    """
    for child in env["children"]:
        if child.pid == pid:
            if child.poll() is not None:
                return False
            try:
                with open(f"/proc/{pid}/stat", "rb") as fh:
                    # comm can contain spaces and parens, so split after the last ')'.
                    if fh.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                        return False
            except OSError:
                return False
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_dead(env, pid, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not alive(env, pid):
            return True
        time.sleep(0.05)
    return False


def run_down(env):
    path = f"{env['stub']}{os.pathsep}{os.environ['PATH']}"
    return subprocess.run(
        ["/bin/sh", str(env["wdir"] / "polaris-apsta.sh"), "down"],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": path, "STUB_DIR": str(env["stub"]),
             "WIFI_DIR": str(env["wdir"]), "STA_IFACE": "wlan1",
             "APSTA_LOG": str(env["tmp"] / "apsta.log"),
             "RESOLV_CONF": str(env["resolv"]),
             "RESOLV_TMP": str(env["tmp"] / "polaris-resolv.conf")},
    )


def write_pidfile(name, pid):
    (Path("/tmp") / name).write_text(f"{pid}\n")


@pytest.fixture(autouse=True)
def clean_pidfiles():
    for n in PIDFILES:
        p = Path("/tmp") / n
        if p.exists():
            p.unlink()
    yield
    for n in PIDFILES:
        p = Path("/tmp") / n
        if p.exists():
            p.unlink()


def test_down_stops_the_autojoin_processes_too(env):
    """The core of #283: autojoin runs under different pidfiles and was ignored."""
    wpa = spawn_process(env)
    dhcp = spawn_process(env)
    write_pidfile("autojoin-wpa.pid", wpa)
    write_pidfile("autojoin-dhcp.pid", dhcp)
    env["table"].write_text(
        f"{wpa} /app/sd/polaris-wifi/wpa_supplicant -B -i wlan1 -P /tmp/autojoin-wpa.pid\n"
        f"{dhcp} udhcpc -i wlan1 -p /tmp/autojoin-dhcp.pid\n"
    )

    proc = run_down(env)
    assert proc.returncode == 0, proc.stderr
    assert wait_dead(env, wpa), (
        "autojoin wpa_supplicant survived `down` -- it holds the control socket, "
        "so the next scan returns EBUSY"
    )
    assert wait_dead(env, dhcp), (
        "autojoin udhcpc survived `down` -- it keeps renewing a lease on an "
        "interface that no longer exists"
    )


def test_down_stops_its_own_processes(env):
    wpa = spawn_process(env)
    dhcp = spawn_process(env)
    write_pidfile("apsta-wpa.pid", wpa)
    write_pidfile("apsta-dhcp.pid", dhcp)
    env["table"].write_text(
        f"{wpa} /app/sd/polaris-wifi/wpa_supplicant -B -i wlan1 -P /tmp/apsta-wpa.pid\n"
        f"{dhcp} udhcpc -i wlan1 -p /tmp/apsta-dhcp.pid\n"
    )
    run_down(env)
    assert wait_dead(env, wpa) and wait_dead(env, dhcp)


def test_stale_pidfile_is_not_killed_blindly(env):
    """A recycled pid must not be killed just because a pidfile names it.

    Two real processes are started; the pidfiles point at them, but ps says they
    are sshd and a login shell. Killing on file existence alone would take out
    both -- worse than the bug being fixed.
    """
    victim_a = spawn_process(env)
    victim_b = spawn_process(env)
    write_pidfile("apsta-wpa.pid", victim_a)
    write_pidfile("apsta-dhcp.pid", victim_b)
    env["table"].write_text(f"{victim_a} /usr/sbin/sshd -D\n{victim_b} -bash\n")

    proc = run_down(env)
    assert alive(env, victim_a), "killed a pid whose command line is not wpa_supplicant"
    assert alive(env, victim_b), "killed a pid whose command line is not udhcpc"
    assert "stale pidfile" in proc.stdout + proc.stderr, (
        "silently ignoring a stale pidfile hides the state"
    )


def test_pidfiles_are_removed_even_when_the_process_is_gone(env):
    """A leftover pidfile must not make the next `up` think it is already joined."""
    write_pidfile("apsta-wpa.pid", 999_999)
    write_pidfile("autojoin-wpa.pid", 999_998)
    run_down(env)
    for n in ("apsta-wpa.pid", "autojoin-wpa.pid"):
        assert not (Path("/tmp") / n).exists(), f"{n} left behind"


def test_down_removes_the_lease_resolver_it_wrote(env):
    """Nothing sends udhcpc a deconfig, so the cleanup has to live in sta_down."""
    proc = run_down(env)
    assert proc.returncode == 0, proc.stderr
    assert not env["resolv"].exists(), (
        "stale nameservers survive `down`; lookups then hang on timeout instead "
        "of failing fast"
    )


def test_down_never_removes_someone_elses_resolv_conf(env):
    """Only our own file. The firmware or an operator may own /etc/resolv.conf."""
    foreign = "nameserver 8.8.8.8\n"
    env["resolv"].write_text(foreign)
    run_down(env)
    assert env["resolv"].read_text() == foreign, "removed a resolv.conf it did not write"


def test_down_survives_a_missing_resolv_conf(env):
    env["resolv"].unlink(missing_ok=True)
    proc = run_down(env)
    assert proc.returncode == 0, proc.stderr


def test_down_reports_what_it_stopped(env):
    """`down` claimed success while doing nothing; the log has to say otherwise."""
    wpa = spawn_process(env)
    write_pidfile("autojoin-wpa.pid", wpa)
    env["table"].write_text(f"{wpa} wpa_supplicant -B -i wlan1\n")
    proc = run_down(env)
    out = proc.stdout + proc.stderr
    assert "stopped" in out and str(wpa) in out


def test_interface_is_torn_down(env):
    run_down(env)
    iw = env["stub"] / "iw.txt"
    assert iw.exists() and "dev wlan1 del" in iw.read_text()


def test_ap_is_never_touched(env):
    """The Benro app talks to 192.168.0.1:9090, so wlan0 must stay up."""
    run_down(env)
    ifc = (env["stub"] / "ifconfig.txt").read_text()
    assert "wlan0 down" not in ifc, "took the AP down"
    assert "wlan1 down" in ifc


def test_watchdog_revert_uses_the_same_teardown():
    """The timeout path used to kill two pidfiles and leave the resolver behind.

    Same symptom #283 reports for `down`, reached a different way, so it must not
    keep its own partial copy of the teardown.
    """
    text = SCRIPT.read_text()
    watchdog = text[text.index("WATCHDOG: no address"):]
    watchdog = watchdog[:watchdog.index("WATCHDOG: station interface removed")]
    assert "sta_down" in watchdog, "watchdog reverted with a partial teardown"
    assert 'kill "$(cat /tmp/apsta' not in watchdog

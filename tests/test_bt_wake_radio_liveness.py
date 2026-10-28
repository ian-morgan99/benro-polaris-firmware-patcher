"""Gate: an empty BLE scan must never be reported as the rig being asleep.

Why this file exists (2026-10-27). On the development workstation the built-in
adapter is a Qualcomm part (usb 0489:e10a) whose vendor RAM patch is never
loaded -- ``CONFIG_BT_HCIBTUSB_QCA`` is unset in the running kernel and ``btqca``
is not among the loaded modules. The controller answers HCI commands, so BlueZ
truthfully reports ``Powered: yes``, ``UP RUNNING`` and ``Discovering: yes``, yet
it has never carried a data packet::

    PC  hci0: RX bytes:8987 acl:0   TX bytes:7670 acl:0   events:601 commands:508
    rig hci0: RX bytes:3227 acl:96  TX bytes:3163 acl:80  (Cypress, works)

LE scan and classic inquiry both return zero devices. Every wake path in this
repo treated that as "the gimbal is asleep", which sent several sessions chasing
the device when the fault was the PC -- ``docs/evidence/
o-v17a-offline-validation-20261012`` records "host currently has no BT adapter"
for exactly this reason.

The fix is scripts/polaris-bt-probe.sh, which separates four states that used to
collapse into one: ALIVE / DEAF / NO_ADAPTER / PROBE_BLOCKED. This test pins the
distinction with stub binaries so it cannot silently regress on a machine that
happens to have a working radio -- which is precisely when the bug would go
unnoticed.

Two specific traps are asserted, because both were hit while writing the probe:

  * ``timeout N <shell-function>`` cannot work -- timeout execs a binary. The
    probe must apply the deadline to the real binary (bt_timeout/bt_bin_timeout).
  * ``$?`` after ``if ! cmd`` is the *negated* status, i.e. always 0, so
    ``case $?`` branches under it are dead code. Callers must capture with
    ``|| rc=$?``.

Offline-safe: stub binaries on PATH, no network, no rig, no adapter required.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "polaris-bt-probe.sh"
PREFLIGHT = ROOT / "scripts" / "polaris-preflight.sh"


def _write(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _stub_bluetoothctl(bin_dir: Path) -> None:
    """bluetoothctl stand-in driven by env vars.

    Shapes reproduced:
      * discovery starts but nothing is found (the inconclusive case);
      * discovery starts and a device is found;
      * discovery never starts (probe blocked);
      * `connect` prints "Attempting to connect" and exits 0 while the link is
        not actually held -- the OpenPolaris #97 false-success shape.

    Device lines are emitted in bluetoothctl's real colourised form, `[NEW]`,
    because matching that literal text is exactly what broke in production.
    """
    _write(bin_dir / "bluetoothctl", '''
        #!/usr/bin/env bash
        case "$*" in
          *list*)
            echo "Controller 00:11:22:33:44:55 stub [default]"
            exit 0;;
          *scan*)
            if [ "${STUB_DISCOVERING:-yes}" = "no" ]; then
              echo "SetDiscoveryFilter success"
              echo "Discovery failed"
              exit 0
            fi
            echo "SetDiscoveryFilter success"
            echo "Discovery started"
            echo "[CHG] Controller 00:11:22:33:44:55 Discovering: yes"
            n="${STUB_DEVICES:-0}"
            i=0
            while [ "$i" -lt "$n" ]; do
              # colourised like the real bluetoothctl under a PTY
              printf '[\033[0;92mNEW\033[0m] Device AA:BB:CC:DD:%02X:EE stub_%d\n' "$i" "$i"
              i=$((i + 1))
            done
            exit 0;;
          *connect*)
            # BlueZ resolves asynchronously: it prints this and exits 0 even
            # when the link aborts locally a second later.
            echo "Attempting to connect ${!#}"
            exit 0;;
          *info*)
            if [ "${STUB_CONNECTED:-no}" = "yes" ]; then
              echo "Device 48:E7:DA:D4:B5:72 polaris"
              echo "\tConnected: yes"
            else
              echo "Device 48:E7:DA:D4:B5:72 polaris"
              echo "\tConnected: no"
            fi
            exit 0;;
          *)
            exit 0;;
        esac
    ''')


def _stub_hcitool(bin_dir: Path, *, found: bool) -> None:
    mac = "11:22:33:44:55:66" if found else ""
    _write(bin_dir / "hcitool", f'''
        #!/usr/bin/env bash
        echo "Scanning ..."
        [ -n "{mac}" ] && echo "{mac}\tstub-peer"
        exit 0
    ''')


def _stub_hciconfig(bin_dir: Path, acl_rx: int) -> None:
    _write(bin_dir / "hciconfig", f'''
        #!/usr/bin/env bash
        cat <<'EOF'
        hci0:\tType: Primary  Bus: USB
        \tBD Address: 00:11:22:33:44:55  ACL MTU: 1024:7
        \tUP RUNNING PSCAN
        \tRX bytes:8987 acl:{acl_rx} sco:0 events:601 errors:0
        \tTX bytes:7670 acl:0 sco:0 commands:508 errors:0
        EOF
        exit 0
    ''')


def _stub_flatpak_spawn(bin_dir: Path) -> None:
    """flatpak-spawn stand-in that just drops `--host` and runs locally."""
    _write(bin_dir / "flatpak-spawn", '''
        #!/usr/bin/env bash
        [ "$1" = "--host" ] && shift
        exec "$@"
    ''')


def _stub_flatpak_spawn_failing(bin_dir: Path) -> None:
    """A portal that does NOT answer. Needed because this sandbox ships a real
    working flatpak-spawn, which would otherwise resolve a live host route and
    make the no-adapter assertions meaningless."""
    _write(bin_dir / "flatpak-spawn", '''
        #!/usr/bin/env bash
        exit 1
    ''')


def _run_bash(script: str, bin_dir: Path, extra_env: dict[str, str] | None = None):
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        # Point the local-route check at something that exists in a container.
        "POLARIS_BT_DEV": str(bin_dir),
        "BT_PORTAL_CWD": str(bin_dir),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "-c", f'. "{PROBE}"\n{script}'],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120,
    )


# --- route resolution -------------------------------------------------------

def test_probe_module_exists_and_parses():
    assert PROBE.is_file(), "scripts/polaris-bt-probe.sh is missing"
    r = subprocess.run(["bash", "-n", str(PROBE)], capture_output=True, text=True)
    assert r.returncode == 0, f"probe does not parse: {r.stderr}"


def test_local_route_resolved_when_dev_and_bluez_present(tmp_path):
    """A normal host must resolve route=local (regression guard: the old code
    keyed on /dev/hci0 literally and reported 'no adapter' inside a Flatpak)."""
    _stub_bluetoothctl(tmp_path)
    r = _run_bash('bt_resolve; echo "rc=$? route=$BT_ROUTE"', tmp_path)
    assert "rc=0 route=local" in r.stdout, r.stdout + r.stderr


def test_no_route_when_nothing_available(tmp_path):
    """With no bluetoothctl and no portal the verdict must be NO_ADAPTER (2),
    never a silent fall-through that lets a caller claim ASLEEP."""
    _stub_flatpak_spawn_failing(tmp_path)
    env = {
        "POLARIS_BT_DEV": str(tmp_path / "nonexistent"),
        # Neutralise the /run/host last-resort route too.
        "POLARIS_BT_HOST_BIN": str(tmp_path / "no-such-binary"),
    }
    r = _run_bash(
        'command -v bluetoothctl >/dev/null && exit 99; '
        'bt_resolve; echo "rc=$? route=$BT_ROUTE"', tmp_path, env)
    assert "rc=2 route=none" in r.stdout, r.stdout + r.stderr


def test_portal_route_used_when_dev_absent_but_spawn_answers(tmp_path):
    """Inside the VS Code Flatpak /dev/hci0 is missing but the portal reaches
    the host adapter. That must resolve to a usable route, not 'no adapter'."""
    _stub_bluetoothctl(tmp_path)
    _stub_flatpak_spawn(tmp_path)
    env = {"POLARIS_BT_DEV": str(tmp_path / "nonexistent")}
    r = _run_bash('bt_resolve; echo "rc=$? route=$BT_ROUTE"', tmp_path, env)
    assert "rc=0 route=portal" in r.stdout, r.stdout + r.stderr


# --- liveness classification ------------------------------------------------

def test_deaf_radio_is_deaf_not_asleep(tmp_path):
    """An empty scan must classify as LIVENESS_UNKNOWN (1), never as proof of a
    dead radio and never as the rig being asleep. A quiet room and a dead radio
    produce identical output here."""
    _stub_bluetoothctl(tmp_path)
    _stub_hciconfig(tmp_path, acl_rx=0)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_radio_liveness 1; echo "rc=$?"; '
        'echo "detail=$BT_LIVENESS_DETAIL"', tmp_path,
        {"STUB_DISCOVERING": "yes", "STUB_DEVICES": "0"})
    assert "rc=1" in r.stdout, f"empty scan must be inconclusive (1): {r.stdout}{r.stderr}"
    assert "le=0" in r.stdout, r.stdout


def test_alive_radio_when_advertisement_seen(tmp_path):
    _stub_bluetoothctl(tmp_path)
    _stub_hciconfig(tmp_path, acl_rx=96)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_radio_liveness 1; echo "rc=$?"', tmp_path,
        {"STUB_DISCOVERING": "yes", "STUB_DEVICES": "3"})
    assert "rc=0" in r.stdout, f"radio with devices must be alive: {r.stdout}"


def test_classic_only_response_counts_as_alive(tmp_path):
    """A radio that hears BR/EDR but no LE advertisements is still receiving;
    calling it deaf would be a false positive."""
    _stub_bluetoothctl(tmp_path)
    _stub_hcitool(tmp_path, found=True)
    _stub_hciconfig(tmp_path, acl_rx=5)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_radio_liveness 1; echo "rc=$?"', tmp_path,
        {"STUB_DISCOVERING": "yes", "STUB_DEVICES": "0"})
    assert "rc=0" in r.stdout, f"classic inquiry hit must mean alive: {r.stdout}"


def test_blocked_when_discovery_never_started(tmp_path):
    """'Discovery failed' proves nothing about the rig; it must not be read as
    deaf-and-therefore-asleep."""
    _stub_bluetoothctl(tmp_path)
    _stub_hciconfig(tmp_path, acl_rx=0)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_radio_liveness 1; echo "rc=$?"', tmp_path,
        {"STUB_DISCOVERING": "no"})
    assert "rc=3" in r.stdout, f"unstarted discovery must be PROBE_BLOCKED: {r.stdout}"


def test_liveness_refused_without_route(tmp_path):
    """No route -> 2 (NO_ADAPTER). Must never return 1, which callers map to a
    host fault distinct from 'cannot tell'."""
    _stub_hciconfig(tmp_path, acl_rx=0)
    _stub_flatpak_spawn_failing(tmp_path)
    r = _run_bash(
        'bt_resolve >/dev/null 2>&1; bt_radio_liveness 1; echo "rc=$?"', tmp_path,
        {"POLARIS_BT_DEV": str(tmp_path / "nonexistent"),
         "POLARIS_BT_HOST_BIN": str(tmp_path / "no-such-binary")})
    assert "rc=2" in r.stdout, r.stdout + r.stderr


# --- wake pulse honesty (OpenPolaris #97) -----------------------------------

def test_wake_pulse_rejects_false_success(tmp_path):
    """bluetoothctl prints 'Attempting to connect' and exits 0 before BlueZ has
    resolved anything. A zero exit from `connect` is NOT a delivered pulse."""
    _stub_bluetoothctl(tmp_path)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_wake_pulse 48:E7:DA:D4:B5:72; echo "rc=$?"',
        tmp_path, {"STUB_CONNECTED": "no"})
    assert "rc=1" in r.stdout, f"unheld link must not count as wake: {r.stdout}"


def test_wake_pulse_accepts_held_link(tmp_path):
    _stub_bluetoothctl(tmp_path)
    r = _run_bash(
        'bt_resolve >/dev/null; bt_wake_pulse 48:E7:DA:D4:B5:72; echo "rc=$?"',
        tmp_path, {"STUB_CONNECTED": "yes"})
    assert "rc=0" in r.stdout, f"held link must count as wake: {r.stdout}"


# --- the two implementation traps -------------------------------------------

def test_timeout_never_wraps_a_shell_function():
    """`timeout N some_function ...` fails silently: timeout execs a binary and
    cannot invoke a shell function, so the command never runs and the caller sees
    empty output / non-zero status.

    This bit twice here. `timeout 18 bt_exec scan on` made every scan look empty,
    and `timeout 15 run_host nmcli ...` made ap_visible() always report "not
    broadcasting" -- so polaris-preflight.sh returned ASLEEP against a rig that
    was awake, associated and serving SSH. Both failures were silent.
    """
    offenders = []
    for sh in sorted((ROOT / "scripts").glob("*.sh")):
        text = sh.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # comments describing the trap are expected, not violations
            if re.search(r"timeout\s+\S+\s+(run_host|bt_exec|bt_timeout|bt_bin_timeout)\b", line):
                offenders.append(f"{sh.name}:{i}: {line.strip()}")
    assert not offenders, (
        "timeout cannot exec a shell function; the wrapped command never runs. "
        "Apply the deadline to the real binary instead:\n  "
        + "\n  ".join(offenders))


def test_ap_detection_unescapes_nmcli_colons(tmp_path):
    """nmcli's terse output ESCAPES colons inside field values: a BSSID prints as
    `48\\:E7\\:DA\\:D4\\:B5\\:73`. Grepping for '48:E7:DA' never matches, so the AP
    always looked absent and an awake rig was reported ASLEEP. This was a
    pre-existing bug, present before any sandbox routing existed."""
    _stub_bluetoothctl(tmp_path)
    _stub_hciconfig(tmp_path, acl_rx=0)

    # Emulate nmcli exactly: escaped colons in the BSSID field.
    _write(tmp_path / "nmcli", r'''
        #!/usr/bin/env bash
        case "$*" in
          *wifi\ list*)
            printf '48\\:E7\\:DA\\:D4\\:B5\\:73:polaris_d13e86\n'
            exit 0;;
          *connection\ show*)
            printf 'polaris_d13e86:1:wlp8s0:activated\n'
            exit 0;;
          *) exit 0;;
        esac
    ''')
    _write(tmp_path / "ip", '''
        #!/usr/bin/env bash
        echo "192.168.0.1 dev wlp8s0 src 192.168.0.4 uid 1000"
        exit 0
    ''')
    _write(tmp_path / "ssh", '''
        #!/usr/bin/env bash
        echo "FwVer:6.0.0.54.76;date:2026.10.27;"
        exit 0
    ''')

    env = {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
        "POLARIS_BT_DEV": str(tmp_path),
        "WIFI_IFACE": "wlp8s0",
    }
    r = subprocess.run(
        ["bash", str(PREFLIGHT), "--scan", "1"],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
    assert "VERDICT=READY" in r.stdout, (
        "an awake rig whose AP is visible must be READY; escaped colons or a "
        f"broken run_host makes this fail:\n{r.stdout}\n{r.stderr}")
    assert r.returncode == 0, f"READY must exit 0, got {r.returncode}"


def _extract_function(path: Path, name: str) -> str:
    """Pull a top-level shell function definition out of a script so it can be
    exercised in isolation without running the script itself."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if not inside and line.startswith(f"{name}() {{"):
            inside = True
        if inside:
            out.append(line)
            if line == "}":
                break
    assert out, f"function {name}() not found in {path.name}"
    return "\n".join(out)


def test_run_host_applies_deadline_to_the_binary(tmp_path):
    """`run_host --timeout N cmd` must actually execute cmd and honour the
    deadline, on both the local and portal routes."""
    _write(tmp_path / "slowpoke", '''
        #!/usr/bin/env bash
        echo ran
        sleep 30
    ''')
    _write(tmp_path / "flatpak-spawn", '''
        #!/usr/bin/env bash
        [ "$1" = "--host" ] && shift
        exec "$@"
    ''')

    harness = f'''set -uo pipefail
PATH="{tmp_path}:$PATH"
{_extract_function(PREFLIGHT, "run_host")}
HOST_PREFIX=()
out="$(run_host --timeout 2 slowpoke 2>&1)"; rc=$?
echo "local rc=$rc out=$out"
HOST_PREFIX=(flatpak-spawn --host)
out="$(run_host --timeout 2 slowpoke 2>&1)"; rc=$?
echo "portal rc=$rc out=$out"
'''
    r = subprocess.run(["bash", "-c", harness], capture_output=True, text=True,
                       env={"PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
                       cwd=str(ROOT), timeout=60)
    assert "local rc=124 out=ran" in r.stdout, (
        f"local route must run the command and hit the deadline: {r.stdout}{r.stderr}")
    assert "portal rc=124 out=ran" in r.stdout, (
        f"portal route must run the command and hit the deadline: {r.stdout}{r.stderr}")


def test_run_host_without_timeout_runs_the_command(tmp_path):
    """The no-deadline form must still prefix HOST_PREFIX correctly. Getting this
    wrong (e.g. invoking `$@` without the prefix) silently runs the sandbox
    binary instead of the host one."""
    _write(tmp_path / "whoami-tool", '''
        #!/usr/bin/env bash
        echo "got:$1"
    ''')
    _write(tmp_path / "flatpak-spawn", '''
        #!/usr/bin/env bash
        [ "$1" = "--host" ] && shift
        exec "$@"
    ''')
    harness = f'''set -uo pipefail
PATH="{tmp_path}:$PATH"
{_extract_function(PREFLIGHT, "run_host")}
HOST_PREFIX=(flatpak-spawn --host)
echo "portal: $(run_host whoami-tool x)"
HOST_PREFIX=()
echo "local: $(run_host whoami-tool x)"
'''
    r = subprocess.run(["bash", "-c", harness], capture_output=True, text=True,
                       env={"PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
                       cwd=str(ROOT), timeout=60)
    assert "portal: got:x" in r.stdout, r.stdout + r.stderr
    assert "local: got:x" in r.stdout, r.stdout + r.stderr

def test_timeout_is_applied_to_a_binary_not_a_function(tmp_path):
    """`timeout N bt_exec ...` cannot work: timeout execs a binary and cannot
    invoke a shell function. bt_timeout must apply it to the real binary."""
    _stub_bluetoothctl(tmp_path)
    r = _run_bash(
        'bt_resolve >/dev/null; out="$(bt_timeout 5 --timeout 1 scan on 2>&1)"; '
        'echo "rc=$?"; printf "%s\\n" "$out" | grep -q "Discovering: yes" '
        '&& echo saw-discovery || echo NO-DISCOVERY', tmp_path,
        {"STUB_DEVICES": "0"})
    assert "NO-DISCOVERY" not in r.stdout, (
        "bt_timeout failed to invoke bluetoothctl -- deadline is probably being "
        f"applied to a shell function: {r.stdout}{r.stderr}")
    assert "saw-discovery" in r.stdout, r.stdout + r.stderr


def test_callers_capture_exit_code_without_negation(tmp_path):
    """`if ! cmd; then case $?` is always 0 -- those branches are dead. Every
    caller of bt_radio_liveness must capture with `|| rc=$?`."""
    offenders = []
    for sh in sorted((ROOT / "scripts").glob("*.sh")):
        text = sh.read_text(encoding="utf-8", errors="replace")
        if "bt_radio_liveness" not in text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if "if ! bt_radio_liveness" in s or "case $?" in s:
                offenders.append(f"{sh.name}:{i}: {s}")
    assert not offenders, (
        "exit code after `if ! cmd` is the negated status (always 0), so these "
        "branches can never fire; use `rc=0; cmd || rc=$?`:\n  "
        + "\n  ".join(offenders))


# --- preflight wiring -------------------------------------------------------

def test_preflight_asleep_on_ap_absence(tmp_path):
    """No AP -> ASLEEP (exit 1). The AP check uses nmcli's Wi-Fi scan, which does
    not depend on the Bluetooth stack, so it is the reliable signal. An empty BLE
    scan must NOT block this verdict -- the rig does not reliably advertise LE."""
    _stub_bluetoothctl(tmp_path)
    _stub_hciconfig(tmp_path, acl_rx=0)

    _write(tmp_path / "nmcli", r'''
        #!/usr/bin/env bash
        case "$*" in
          *wifi\ list*) exit 0;;                       # AP not visible
          *connection\ show*) exit 0;;                 # not associated
          *) exit 0;;
        esac
    ''')
    _write(tmp_path / "ip", '''
        #!/usr/bin/env bash
        echo "192.168.0.1 dev wlp8s0"
        exit 0
    ''')
    _write(tmp_path / "ssh", '''
        #!/usr/bin/env bash
        exit 255
    ''')

    env = {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
        "POLARIS_BT_DEV": str(tmp_path),
        "WIFI_IFACE": "wlp8s0",
    }
    r = subprocess.run(
        ["bash", str(PREFLIGHT), "--scan", "1"],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
    assert "VERDICT=ASLEEP" in r.stdout, (
        f"AP absence must give ASLEEP; got:\n{r.stdout}\n{r.stderr}")
    assert r.returncode == 1, f"ASLEEP must exit 1, got {r.returncode}"


def test_preflight_never_invents_a_deaf_radio_verdict():
    """RADIO_DEAF was removed on purpose: an empty scan cannot prove a radio is
    dead (BlueZ emits [NEW] once per cached device; a quiet room yields nothing).
    Reintroducing it would fabricate a host fault from absence of evidence."""
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "RADIO_DEAF" not in text, (
        "RADIO_DEAF is unsound: an empty scan proves nothing. ASLEEP must rest "
        "on AP absence via the Wi-Fi scan.")


def test_probe_strips_ansi_before_matching():
    """The original measurement bug. flatpak-spawn allocates a PTY, so bluetoothctl
    colourises output even when piped: `[NEW]` arrives as ESC[0;92mNEW ESC[0m.
    Without stripping, a healthy radio reads as deaf -- which is exactly what
    produced a false 'host radio cannot receive' conclusion on 2026-10-27."""
    text = PROBE.read_text(encoding="utf-8")
    assert "bt_strip" in text, "ANSI stripping helper is missing"
    # The scan pipeline must actually use it.
    assert re.search(r"scan on[^\n]*\|[^\n]*bt_strip", text), (
        "the LE scan output is not piped through bt_strip; colour codes will "
        "make every advertisement invisible")


def test_strip_helper_removes_colour_codes(tmp_path):
    """Directly exercise bt_strip on the exact byte sequence observed live."""
    # Real bytes. `cat -A` renders ESC as `^[`, so the live line
    # `^[[0;92mNEW^[[0m] Device ...` is bytes '[' ESC '[0;92m' 'NEW' ESC '[0m' ']'.
    coloured = b"[\x1b[0;92mNEW\x1b[0m] Device 5A:7A:CA:C1:3E:33 stub\n"
    (tmp_path / "coloured.txt").write_bytes(coloured)
    r = subprocess.run(
        ["bash", "-c", f'. "{PROBE}"; bt_strip < "{tmp_path}/coloured.txt"'],
        capture_output=True, text=True, cwd=str(ROOT), timeout=30)
    assert "[NEW] Device 5A:7A:CA:C1:3E:33" in r.stdout, (
        f"bt_strip did not remove the colour codes: {r.stdout!r}")


def test_preflight_help_documents_options():
    """The exit-code table is a contract callers branch on."""
    r = subprocess.run(["bash", str(PREFLIGHT), "--help"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=30)
    assert "5 HOST_TOOLING" in r.stdout, r.stdout
    assert "--no-radio-check" in r.stdout, r.stdout
    assert "set -uo pipefail" not in r.stdout, "help range overruns into code"

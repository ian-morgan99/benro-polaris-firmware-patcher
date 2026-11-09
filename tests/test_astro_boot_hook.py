"""Tests for the Astro boot hook (#265).

Root cause, measured on 6.0.0.54.101 (build_id v101) on 2026-11-09: the Astro
bundle is complete and its solver works -- polaris-solve returned RA 99.999992 /
Dec 14.989601 against a known synthetic field, 22/22 matches, in 1.385 s on-device.
The web UI never started for exactly one reason: nothing invokes
polaris-astro-boot.sh.

    ls -d /app/astro                                   -> DOES NOT EXIST
    [ -x /app/sd/polaris-astro/polaris-astro-boot.sh ]  -> yes, executable
    grep -rl "polaris-astro|astro-boot" /etc /app/etc /init.d -> (no matches)
    ps | grep polaris-httpd                            -> none running

The init chain is /etc/init.d/rcS, which runs only S00devs, S10mpp and S80network;
there is no rc.local. S10mpp runs /app/bootapp, and bootapp calls exactly two
optional hooks -- network_telnetd.sh and start_agent.sh. The bundle's own
install_astro.sh is what writes one of them, but it requires a manual run, so on a
fresh install nothing ever calls it: the card extracts correctly, the bundle is
valid, and the stack stays unreachable regardless of how correct it is.

These tests need no device. SD_ROOT and APP_ROOT are overridable precisely so the
launch decision and the ssh-chaining decision -- the one that determines whether a
user keeps ssh -- can be exercised here instead of only on hardware.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(ROOT, "container", "astro", "ondisk", "polaris-astro-hook.sh")
PATCH_SH = os.path.join(ROOT, "container", "patch.sh")


def run_hook(app_root, sd_root, wait=1, hook_path=None):
    """Run the launcher against a fake appfs and card root."""
    env = dict(os.environ, SD_ROOT=sd_root, APP_ROOT=app_root,
               ASTRO_CARD_WAIT=str(wait))
    return subprocess.run(["sh", hook_path or HOOK], capture_output=True,
                          text=True, timeout=60, env=env)


def wait_for(*paths, timeout=6.0):
    """Wait until every path exists.

    The launcher starts the card's boot script with `setsid ... &`, so it is still
    running when the hook returns. Returning early lets TemporaryDirectory's rmtree
    race the child creating its flag file, which fails cleanup with ENOTEMPTY -- a
    flake that depends on machine load. Waiting for every effect the test cares about
    makes it deterministic and also asserts more: the astro launch really happened.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(os.path.exists(p) for p in paths):
            return True
        time.sleep(0.1)
    return False


def make_card(tmp, with_boot_script=True):
    sd = os.path.join(tmp, "sd")
    card = os.path.join(sd, "polaris-astro")
    os.makedirs(card, exist_ok=True)
    if with_boot_script:
        path = os.path.join(card, "polaris-astro-boot.sh")
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\necho RAN > %s/ran.flag\n" % tmp)
        os.chmod(path, 0o755)
    return sd


# ── the hook exists and is well-formed ───────────────────────────────────────

def test_launcher_ships_with_the_patcher():
    """patch.sh installs /opt/patcher/astro/ondisk/polaris-astro-hook.sh; the
    Dockerfile copies container/ to /opt/patcher, so this exact path must exist."""
    assert os.path.isfile(HOOK), f"missing {HOOK}"


def test_launcher_path_in_patch_sh_resolves_under_docker_copy():
    """docker/Dockerfile does `COPY container/ /opt/patcher/`, so a source file at
    container/astro/ondisk/X lands at /opt/patcher/astro/ondisk/X. A path in
    patch.sh that omits ondisk would die at flash time."""
    src = open(PATCH_SH, encoding="utf-8").read()
    assert "/opt/patcher/astro/ondisk/polaris-astro-hook.sh" in src, (
        "patch.sh must reference the launcher at the path the Dockerfile produces")


def test_both_scripts_parse():
    for path in (HOOK, PATCH_SH):
        proc = subprocess.run(["sh", "-n", path], capture_output=True, text=True)
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


# ── the launch decision ──────────────────────────────────────────────────────

def test_no_card_exits_cleanly_without_launching():
    """A device with no astro card must boot normally. This is the common case for
    every non-astro install, so a nonzero exit here would be a regression on
    hardware that has nothing to do with astro."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_hook(os.path.join(tmp, "app"), os.path.join(tmp, "sd"))
    assert proc.returncode == 0, proc.stderr
    assert "astro not started" in proc.stdout


def test_card_without_boot_script_reports_it_rather_than_failing_silently():
    """A card that has the directory but not the script is a broken extraction.
    Saying nothing would reproduce the original silent failure."""
    with tempfile.TemporaryDirectory() as tmp:
        sd = make_card(tmp, with_boot_script=False)
        proc = run_hook(os.path.join(tmp, "app"), sd)
    assert proc.returncode == 0, proc.stderr
    assert "polaris-astro-boot.sh is missing" in proc.stdout


def test_card_with_boot_script_actually_launches_it():
    """The whole point of #265: the card's boot script must run at boot with no
    operator step. Assert on the effect, not on a log line."""
    with tempfile.TemporaryDirectory() as tmp:
        sd = make_card(tmp)
        proc = run_hook(os.path.join(tmp, "app"), sd)
        assert proc.returncode == 0, proc.stderr
        assert wait_for(os.path.join(tmp, "ran.flag")), (
            "the card's polaris-astro-boot.sh never ran -- #265 is not fixed")


def test_hook_does_not_block_on_a_missing_card():
    """bootapp runs hooks inline, so the wait must be bounded. With ASTRO_CARD_WAIT=1
    the no-card path must finish in a couple of seconds, not stall boot."""
    with tempfile.TemporaryDirectory() as tmp:
        start = time.monotonic()
        run_hook(os.path.join(tmp, "app"), os.path.join(tmp, "sd"), wait=1)
        elapsed = time.monotonic() - start
    assert elapsed < 10, f"hook blocked boot for {elapsed:.1f}s"


# ── ssh must survive ─────────────────────────────────────────────────────────

def test_displaced_hook_is_chained_first_so_ssh_survives():
    """/app/network_telnetd.sh and /app/start_agent.sh are single slots, and the
    patcher's --ssh-key option (#31) writes the same files. If this launcher takes a
    slot that previously held the ssh hook, the prior hook is saved as
    <name>.pre-astro.sh and must run BEFORE anything astro does -- losing it would
    lock us out of the device we are debugging."""
    with tempfile.TemporaryDirectory() as tmp:
        sd = make_card(tmp)
        app = os.path.join(tmp, "app")
        os.makedirs(app, exist_ok=True)
        installed = os.path.join(app, "start_agent.sh")
        with open(HOOK) as fh:
            body = fh.read()
        with open(installed, "w") as fh:
            fh.write(body)
        os.chmod(installed, 0o755)
        prior = os.path.join(app, "start_agent.sh.pre-astro.sh")
        with open(prior, "w") as fh:
            fh.write("#!/bin/sh\ntouch %s\n" % os.path.join(tmp, "ssh.flag"))
        os.chmod(prior, 0o755)

        proc = run_hook(app, sd, hook_path=installed)
        assert proc.returncode == 0, proc.stderr
        assert "chaining preserved hook" in proc.stdout, proc.stdout
        # Wait for both effects: ssh ran first, and astro was launched. Waiting for
        # the astro flag too is what keeps cleanup from racing the child.
        assert wait_for(os.path.join(tmp, "ssh.flag"), os.path.join(tmp, "ran.flag")), (
            "the displaced ssh hook or the card boot script never ran -- this launcher "
            "would lock the operator out of the device")


def test_card_boot_script_is_the_only_place_network_telnetd_prior_is_run():
    """polaris-astro-boot.sh already chains /app/network_telnetd.pre-astro.sh
    itself. This launcher must not chain that same file too, or ssh setup runs
    twice on every boot."""
    body = open(HOOK, encoding="utf-8").read()
    # Strip comments: the launcher documents in a comment that it deliberately
    # does NOT chain this file, and matching on raw text flags that note.
    code = "\n".join(line for line in body.splitlines()
                     if not line.strip().startswith("#"))
    assert "network_telnetd.pre-astro.sh" not in code, (
        "launcher chains network_telnetd.pre-astro.sh directly; the card's own "
        "boot script already does, so this would run ssh setup twice")


# ── flash-time installation ──────────────────────────────────────────────────

def test_patch_sh_installs_the_hook_only_when_asked():
    """Opt-in, like --ssh-key: a release must not start writing boot hooks onto
    devices whose owners never asked for astro."""
    src = open(PATCH_SH, encoding="utf-8").read()
    assert 'if [ -n "${ASTRO_BOOT:-}" ]' in src, "astro hook install must be opt-in"


def test_patch_sh_refuses_to_clobber_ssh():
    """Slot selection must skip whatever --ssh-key took in the same run and abort
    rather than overwrite it or edit bootapp."""
    src = open(PATCH_SH, encoding="utf-8").read()
    assert '[ "$cand" = "$SSH_HOOK" ] && continue' in src, (
        "astro slot selection must skip the slot --ssh-key already claimed")
    assert "refusing to modify bootapp or clobber ssh" in src, (
        "astro hook install must fail closed when no free slot exists")


def test_patch_sh_requires_bootapp_to_call_the_hook():
    """Same fail-closed rule as the ssh option: only use a hook bootapp provably
    calls, otherwise nothing would run and we would not know."""
    src = open(PATCH_SH, encoding="utf-8").read()
    section = src.split('if [ -n "${ASTRO_BOOT:-}" ]')[1][:2000]
    assert 'grep -q "$cand" "$BOOTAPP"' in section, (
        "must confirm bootapp actually calls the hook before installing it")

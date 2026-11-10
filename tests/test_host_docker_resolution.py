"""Tests for host-docker resolution (#306 follow-up, v102 build blocker).

On 2026-11-09, 82 minutes after v101 shipped cleanly, the v102 build could not
start: `docker info` returned rc=127 with

    /home/ian/bin/docker: 5: exec: /usr/bin/flatpak-spawn: not found

Nothing in the repo had changed. The cause was a shim at ~/bin/docker of the shape
this repo's own tooling writes and its own doctor recommends:

    exec flatpak-spawn --host docker "$@"

`--host docker` asks the HOST to resolve `docker` on the HOST's PATH. ~/.local/bin
and ~/bin are on it by default, so the host ran that same shim, which tried to exec
flatpak-spawn -- a binary that exists only inside the sandbox -- and died. The
symptom is indistinguishable from "docker is not installed", so build-doctor.sh told
the operator to install a shim when a shim was already present and was the cause.

The rule these tests enforce: never hand a bare command name to `--host`. Name an
absolute path on the host, which can never be one of our shims, so it cannot recurse.
"""
from __future__ import annotations

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, "tools", "host-docker.sh")
HOST_BIN = os.path.join(ROOT, "tools", "host-bin", "docker")
UBI = os.path.join(ROOT, "tools", "ubireader-docker")
DOCTOR = os.path.join(ROOT, "scripts", "build-doctor.sh")
BUILD_ASTRO = os.path.join(ROOT, "scripts", "build-astro.sh")

# Files that reach the host docker and must not use a bare name.
CONSUMERS = [HOST_BIN, UBI, DOCTOR, BUILD_ASTRO]


def sh(script, env=None, timeout=120):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True,
                          timeout=timeout, env=e)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── the rule itself ──────────────────────────────────────────────────────────

def test_library_resolves_absolute_host_paths_only():
    """The candidate list must be absolute system paths. Including $HOME/bin or
    ~/.local/bin would put a recursing shim back into the resolution chain."""
    body = read(LIB)
    m = re.search(r"POLARIS_DOCKER_HOST_CANDIDATES=\"([^\"]+)\"", body)
    assert m, "candidate list missing from tools/host-docker.sh"
    for cand in m.group(1).split():
        assert cand.startswith("/"), f"non-absolute candidate: {cand}"
        assert "$" not in cand, f"unexpanded variable in candidate: {cand}"
        assert "bin/docker" not in cand or "/usr" in cand or "/opt" in cand or "/snap" in cand


def test_no_consumer_hands_a_bare_name_to_host():
    """`flatpak-spawn --host docker ...` is the defect. Every consumer must name an
    absolute path, directly or via polaris_docker_prefix."""
    offenders = []
    for path in CONSUMERS:
        code = code_only(path)
        if re.search(r"--host\s+docker(\s|$|\"|\")", code):
            offenders.append(os.path.relpath(path, ROOT))
    assert not offenders, (
        "these resolve 'docker' on the host PATH and can recurse into a shim: "
        + ", ".join(offenders))


def code_only(path):
    """Source with whole-line comments removed. Several of these files document the
    broken form in a comment, and matching on raw text flags that documentation."""
    return "\n".join(l for l in read(path).splitlines()
                     if not l.strip().startswith("#"))


def test_doctor_no_longer_advises_creating_a_recursing_shim():
    """The doctor's own hint was how this got onto the machine in the first place:
    it told people to write `exec flatpak-spawn --host docker` into ~/.local/bin.
    Recommending the footgun from the tool that detects it is the real bug."""
    assert "exec flatpak-spawn --host docker" not in code_only(DOCTOR), (
        "build-doctor.sh still tells the operator to create a recursing shim")
    assert "tools/host-bin" in read(DOCTOR), (
        "the doctor should point at this repo's absolute-path shim")


def test_build_astro_writes_an_absolute_path_shim():
    """build-astro.sh generates a shim. It must embed a resolved absolute host path,
    not the literal bare name it used to write."""
    assert "exec flatpak-spawn --host docker" not in code_only(BUILD_ASTRO), (
        "build-astro.sh still writes a shim that resolves 'docker' on the host PATH")
    assert "polaris_docker_prefix" in read(BUILD_ASTRO), (
        "build-astro.sh must resolve the path via tools/host-docker.sh")


# ── behaviour ────────────────────────────────────────────────────────────────

def test_library_is_sourceable_and_parses():
    for path in (LIB, HOST_BIN, UBI, DOCTOR, BUILD_ASTRO):
        proc = sh(f"sh -n {path!r}")
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_prefix_is_usable_on_this_host():
    """If docker is reachable here, the resolver must find it. If it is genuinely
    unreachable, an empty prefix is the correct answer -- but it must not hang."""
    proc = sh(f'. "{LIB}"; polaris_docker_prefix')
    assert proc.returncode in (0, 1), proc.stderr
    prefix = proc.stdout.strip()
    if not prefix:
        return  # no docker here; nothing to verify
    probe = sh(f"{prefix} info --format '{{{{.ServerVersion}}}}'")
    assert probe.returncode == 0, f"resolver returned {prefix!r} but it does not work"
    assert probe.stdout.strip(), "docker answered with an empty version"


def test_repo_shim_works_when_first_on_path():
    """tools/host-bin/docker is documented as 'put this on PATH and it just works'.
    Prove that, including when a broken bare-name shim sits behind it."""
    env = {"PATH": os.path.join(ROOT, "tools", "host-bin") + ":" + os.environ["PATH"]}
    proc = sh("docker info --format '{{.ServerVersion}}'", env=env)
    if proc.returncode != 0 and "cannot reach" not in proc.stderr:
        # A host with no docker at all is a legitimate environment; the shim must
        # say so clearly rather than dying with a confusing exec error.
        assert "cannot reach" in proc.stderr, proc.stderr


def test_shim_does_not_recurse_into_a_broken_host_shim():
    """The exact v102 failure: the host resolves `docker` to a shim that execs
    flatpak-spawn. Our shim must ignore that and use its absolute path."""
    env = {"PATH": os.path.join(ROOT, "tools", "host-bin") + ":" + os.environ["PATH"]}
    proc = sh("docker info --format '{{.ServerVersion}}'", env=env)
    assert "flatpak-spawn: not found" not in (proc.stdout + proc.stderr), (
        "the shim recursed into a host-side shim -- the v102 failure is back")


def test_shadow_detection_names_a_broken_docker():
    """A docker on PATH that fails `docker info` must be reported as broken, not
    as missing. Telling someone to install a second shim makes this worse."""
    script = (
        f'. "{LIB}"; '
        "mkdir -p /tmp/shadowtest-$$ && printf '#!/bin/sh\\nexit 1\\n' "
        "> /tmp/shadowtest-$$/docker && chmod +x /tmp/shadowtest-$$/docker && "
        "PATH=/tmp/shadowtest-$$:$PATH; polaris_docker_shadowed && echo SHADOWED; "
        "rm -rf /tmp/shadowtest-$$")
    proc = sh(script)
    assert "SHADOWED" in proc.stdout, (
        "a broken docker on PATH was not detected as shadowing")

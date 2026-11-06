"""Regression tests for the build tooling added after the 2026-11-06 v97 failures.

Six separate build attempts failed that day, and every one reported itself as
something unrelated to its real cause. These tests pin down the two properties
that make the new tooling worth having:

  * a prerequisite is PROVEN, not merely looked for (build-doctor.sh), and
  * when something fails, the message names the ACTUAL cause (the bridge, the
    manifest script's ubireader probe, and build-astro.sh's guards).

Everything here runs against fixture trees and a fake docker on PATH. Nothing
depends on the host having Docker, ubireader, libgphoto2 or a camera, so these
run in CI and on a machine with none of them installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
DOCTOR = REPO / "scripts" / "build-doctor.sh"
BRIDGE = REPO / "tools" / "ubireader-docker"
WRAPPER = REPO / "scripts" / "build-astro.sh"
MANIFEST = REPO / "scripts" / "generate-fwpkt-manifest.py"


def run(cmd, env=None, cwd=None, input=None):
    return subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=cwd, input=input, timeout=300,
    )


def clean_env(**overrides) -> dict:
    """Strip ambient build-tooling state so a test cannot pass or fail by accident.

    The whole point of these scripts is that they behave correctly on a host where
    prerequisites are broken. If the developer's shell happens to have
    UBIREADER_EXTRACT_FILES set, or ~/.local/bin on PATH, tests silently exercise
    a different code path than the one under test.
    """
    env = dict(os.environ)
    for key in ("UBIREADER_EXTRACT_FILES", "POLARIS_IMAGE", "POLARIS_LIBGPHOTO2",
                "POLARIS_STOCK_FWPKT", "POLARIS_CATALOG", "POLARIS_V96_LIBSRC"):
        env.pop(key, None)
    env.update(overrides)
    return env


# ---------------------------------------------------------------------------
# The scripts must exist and be executable -- they are invoked directly.
@pytest.mark.parametrize("script", [DOCTOR, BRIDGE, WRAPPER], ids=["doctor", "bridge", "wrapper"])
def test_tooling_present_and_executable(script: Path):
    assert script.is_file(), f"missing {script}"
    assert os.access(script, os.X_OK), f"{script} is not executable"


@pytest.mark.parametrize("script", [DOCTOR, WRAPPER], ids=["doctor", "wrapper"])
def test_shell_syntax_is_valid(script: Path):
    assert run(["bash", "-n", str(script)]).returncode == 0


# ---------------------------------------------------------------------------
# tools/ubireader-docker
#
# The manifest script's probe is `[cand, "--help"]` and requires exit 0. If the
# bridge fails that probe it is silently rejected and step [3/7] dies with
# "no functional ubireader" -- the exact message that hid the real fault on
# 2026-11-06. So the probe contract is tested first, and without Docker.
def test_bridge_answers_help_probe():
    p = run([str(BRIDGE), "--help"])
    assert p.returncode == 0, p.stderr
    assert "usage" in p.stdout.lower()


def test_bridge_help_works_without_docker(tmp_path: Path):
    """--help must not touch the daemon; the probe runs before any extraction."""
    env = clean_env(PATH=str(tmp_path), POLARIS_IMAGE="nonexistent:tag")
    p = run([str(BRIDGE), "--help"], env=env)
    assert p.returncode == 0, p.stderr


def _fake_docker(bin_dir: Path, *, image_present: bool = True) -> Path:
    """A docker stand-in that records its arguments and answers the bridge's probes."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    script = bin_dir / "docker"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {log}\n'
        'if [ "$1" = "info" ]; then exit 0; fi\n'
        'if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then '
        + ("exit 0" if image_present else "exit 1")
        + "; fi\n"
        'if [ "$1" = "run" ]; then exit 0; fi\n'
        "exit 0\n"
    )
    script.chmod(0o755)
    return log


def test_bridge_requires_output_dir(tmp_path: Path):
    log = _fake_docker(tmp_path / "bin")
    src = tmp_path / "home" / "appfs.ubifs"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 16)
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    p = run([str(BRIDGE), str(src)], env=env)
    assert p.returncode == 2
    assert "-o OUTDIR is required" in p.stderr


def test_bridge_rejects_missing_input(tmp_path: Path):
    _fake_docker(tmp_path / "bin")
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    p = run([str(BRIDGE), "-o", str(tmp_path / "out"), str(tmp_path / "nope.ubifs")], env=env)
    assert p.returncode == 2
    assert "input not found" in p.stderr


def test_bridge_refuses_a_path_the_daemon_cannot_see(tmp_path: Path):
    """The whole point of the guard: a sandbox-private /tmp mounts EMPTY.

    Failing loudly here beats producing an empty extraction that the caller
    reports as "no functional ubireader", which is what sent us looking at the
    wrong thing on 2026-11-06.

    tmp_path lives under $HOME, which IS allowed, so the refusal has to be
    provoked with a path genuinely outside the allowlist.
    """
    log = _fake_docker(tmp_path / "bin")
    outside = Path("/dev/shm/polaris-bridge-test")
    outside.mkdir(parents=True, exist_ok=True)
    src = outside / "appfs.ubifs"
    try:
        src.write_bytes(b"\x00" * 16)
        env = clean_env(PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
        p = run([str(BRIDGE), "-o", str(tmp_path / "out"), str(src)], env=env)
        assert p.returncode == 2
        assert "not on a host-visible path" in p.stderr
        assert "TMPDIR" in p.stderr, "must tell the operator how to fix it"
        # The bridge legitimately calls 'docker info' and 'image inspect' before
        # this guard, so assert specifically that no container was started.
        assert not log.exists() or " run " not in f" {log.read_text()} ", \
            "must refuse BEFORE starting a container"
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_bridge_accepts_host_visible_path_and_mounts_at_same_path(tmp_path: Path):
    """Input and output must be mounted at IDENTICAL paths so -o behaves natively."""
    log = _fake_docker(tmp_path / "bin")
    src = tmp_path / "appfs.ubifs"
    src.write_bytes(b"\x00" * 16)
    env = clean_env(PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    p = run([str(BRIDGE), "-o", str(tmp_path / "out"), str(src)], env=env)
    if p.returncode == 2:
        # tmp_path is not under an allowed prefix on every CI host; refusing is
        # correct behaviour, just not the branch this test is about.
        assert "not on a host-visible path" in p.stderr
        pytest.skip(f"{tmp_path} is not a daemon-visible path here")
    assert p.returncode == 0, p.stderr
    calls = log.read_text()
    assert "--entrypoint ubireader_extract_files" in calls
    assert f"{src.parent}:{src.parent}:ro" in calls


def test_bridge_reports_missing_image(tmp_path: Path):
    _fake_docker(tmp_path / "bin", image_present=False)
    src = tmp_path / "appfs.ubifs"
    src.write_bytes(b"\x00" * 16)
    env = clean_env(
        PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        POLARIS_IMAGE="absent-image:tag",
    )
    p = run([str(BRIDGE), "-o", str(tmp_path / "out"), str(src)], env=env)
    if p.returncode == 2 and "host-visible" in p.stderr:
        pytest.skip(f"{tmp_path} is not a daemon-visible path here")
    assert p.returncode == 3
    assert "absent-image" in p.stderr


def test_bridge_reports_unreachable_daemon(tmp_path: Path):
    """No docker at all must say so, not fail with a bare 'command not found'."""
    src = tmp_path / "appfs.ubifs"
    src.write_bytes(b"\x00" * 16)
    env = clean_env(PATH=str(tmp_path))
    p = run([str(BRIDGE), "-o", str(tmp_path / "out"), str(src)], env=env)
    if p.returncode == 2 and "host-visible" in p.stderr:
        pytest.skip(f"{tmp_path} is not a daemon-visible path here")
    assert p.returncode == 3
    assert "Docker daemon" in p.stderr


# ---------------------------------------------------------------------------
# generate-fwpkt-manifest.py: the ubireader probe must say WHY it rejected things.
#
# On 2026-11-06 a wrapper existed at ~/.local/bin and was executable, but died at
# import time. resolve_ubireader correctly rejected it, then reported only "no
# functional ubireader" -- indistinguishable from "nothing installed".
def _load_manifest_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_fwpkt_manifest", MANIFEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_ubireader_names_a_broken_wrapper(tmp_path: Path):
    """A wrapper that exists but fails must be REPORTED as broken, not skipped.

    On 2026-11-06 ~/.local/bin/ubireader_extract_files existed and was executable
    but died at import. The probe rejected it correctly and then said nothing about
    it, so "no functional ubireader" was indistinguishable from "nothing installed".
    Whether some other candidate happens to work on this host is irrelevant -- the
    broken one must still be named in the notes.
    """
    mod = _load_manifest_module()
    broken = tmp_path / "ubireader_extract_files"
    broken.write_text("#!/bin/sh\necho \"ModuleNotFoundError: No module named 'ubireader'\" >&2\nexit 1\n")
    broken.chmod(0o755)

    env_backup = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}:{env_backup}"
    try:
        found, notes = mod.resolve_ubireader(None)
    finally:
        os.environ["PATH"] = env_backup

    text = " ".join(notes)
    assert str(broken) in text, f"must name the candidate it rejected: {notes}"
    assert "NOT functional" in text, f"must distinguish broken from absent: {notes}"
    assert "ModuleNotFoundError" in text, f"must carry the real error: {notes}"
    if found is None:
        assert text.strip(), "a total failure must still explain what was tried"


def test_resolve_ubireader_accepts_a_working_wrapper(tmp_path: Path):
    mod = _load_manifest_module()
    good = tmp_path / "ubireader_extract_files"
    good.write_text("#!/bin/sh\n[ \"$1\" = \"--help\" ] && echo usage && exit 0\nexit 0\n")
    good.chmod(0o755)
    env_backup = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}:{env_backup}"
    try:
        found, _notes = mod.resolve_ubireader(None)
    finally:
        os.environ["PATH"] = env_backup
    assert found == str(good)


def test_resolve_ubireader_reports_explicit_path_missing(tmp_path: Path):
    mod = _load_manifest_module()
    missing = tmp_path / "does-not-exist"
    found, notes = mod.resolve_ubireader(str(missing))
    assert found is None
    assert "does not exist" in " ".join(notes)


def test_extract_appfs_returns_the_tools_own_error(tmp_path: Path):
    """A tool that RUNS and fails must not be reported as 'not installed'."""
    mod = _load_manifest_module()
    failing = tmp_path / "ubi"
    failing.write_text("#!/bin/sh\necho 'OSError: cannot mount' >&2\nexit 1\n")
    failing.chmod(0o755)
    img = tmp_path / "appfs.ubifs"
    img.write_bytes(b"\x00" * 32)
    root, note = mod.extract_appfs(str(img), str(failing))
    assert root is None
    assert "OSError: cannot mount" in note, f"must surface the tool's error: {note}"


# ---------------------------------------------------------------------------
# scripts/build-astro.sh guards.
#
# These are the refusals that prevent a wasted 20-minute build and, more
# importantly, prevent shipping the wrong thing. Each is checked against a
# throwaway git repo so the real tree is never touched.
@pytest.fixture()
def wrapper_sandbox(tmp_path: Path):
    """A minimal repo containing only build-astro.sh, with its host paths overridden."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "tools").mkdir()
    shutil.copy(WRAPPER, root / "scripts" / "build-astro.sh")
    shutil.copy(DOCTOR, root / "scripts" / "build-doctor.sh")
    shutil.copy(BRIDGE, root / "tools" / "ubireader-docker")
    run(["git", "init", "-q"], cwd=root)
    run(["git", "config", "user.email", "t@t"], cwd=root)
    run(["git", "config", "user.name", "t"], cwd=root)
    (root / "README").write_text("x\n")
    run(["git", "add", "-A"], cwd=root)
    run(["git", "commit", "-qm", "base"], cwd=root)

    stock = tmp_path / "FwPkt.zip"
    stock.write_bytes(b"PK\x03\x04fake")
    catalog = tmp_path / "catalog" / "tiles"
    catalog.mkdir(parents=True)
    (tmp_path / "catalog" / "tiles.json").write_text("{}")

    summary = root / "docs" / "summary.json"
    summary.write_text(json.dumps({
        "baseline": {}, "purpose": "test", "changes": [],
        "known_limits": [], "validation_focus": [],
    }))
    return root, stock, tmp_path / "catalog", summary


def _wrapper(root: Path, *args, extra_env=None):
    env = clean_env(HOME=str(root.parent / "fakehome"))
    if extra_env:
        env.update(extra_env)
    return run(["bash", str(root / "scripts" / "build-astro.sh"), *args], env=env, cwd=root)


def _libgphoto2_fixture(path: Path) -> Path:
    """A minimal clean self-contained clone that passes the wrapper's source checks."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "configure.ac").write_text("AC_INIT([libgphoto2])\n")
    run(["git", "init", "-q"], cwd=path)
    run(["git", "config", "user.email", "t@t"], cwd=path)
    run(["git", "config", "user.name", "t"], cwd=path)
    run(["git", "add", "-A"], cwd=path)
    run(["git", "commit", "-qm", "base"], cwd=path)
    return path


def test_wrapper_requires_numeric_version(wrapper_sandbox):
    root, stock, catalog, summary = wrapper_sandbox
    p = _wrapper(root, "--version", "banana", "--stock", str(stock), "--catalog", str(catalog))
    assert p.returncode != 0
    assert "must be a number" in p.stderr


def test_wrapper_rejects_missing_stock(wrapper_sandbox):
    root, _stock, catalog, summary = wrapper_sandbox
    p = _wrapper(root, "--version", "99", "--catalog", str(catalog),
                 "--stock", "/nonexistent/FwPkt.zip")
    assert p.returncode != 0
    assert "stock FwPkt not found" in p.stderr


def test_wrapper_rejects_incomplete_catalog(wrapper_sandbox):
    root, stock, _catalog, summary = wrapper_sandbox
    p = _wrapper(root, "--version", "99", "--stock", str(stock),
                 "--catalog", str(root.parent / "nope"))
    assert p.returncode != 0
    assert "catalogue package" in p.stderr


def test_wrapper_writes_summary_template_and_stops(wrapper_sandbox):
    """It must never invent a change summary -- that file is the release's honest record."""
    root, stock, catalog, _summary = wrapper_sandbox
    p = _wrapper(root, "--version", "99", "--slug", "t", "--stock", str(stock),
                 "--catalog", str(catalog))
    assert p.returncode == 0, p.stderr
    written = root / "docs" / "release-change-summary-v99-astro.json"
    assert written.is_file(), "template should be written for the operator to fill in"
    data = json.loads(written.read_text())
    assert any("REPLACE" in json.dumps(v) for v in data.values()), \
        "template must contain obvious placeholders, not plausible-sounding defaults"
    assert "Fill it in" in p.stdout


def test_wrapper_rejects_invalid_summary_json(wrapper_sandbox):
    root, stock, catalog, summary = wrapper_sandbox
    summary.write_text("{not json")
    p = _wrapper(root, "--version", "99", "--stock", str(stock), "--catalog", str(catalog),
                 "--summary", str(summary))
    assert p.returncode != 0
    assert "not valid JSON" in p.stderr


def test_wrapper_refuses_dirty_patcher_tree(wrapper_sandbox):
    """Provenance records the commit; a dirty tree makes that record a lie."""
    root, stock, catalog, summary = wrapper_sandbox
    (root / "uncommitted").write_text("oops\n")
    p = _wrapper(root, "--version", "99", "--stock", str(stock), "--catalog", str(catalog),
                 "--summary", str(summary), "--skip-doctor",
                 "--libgphoto2", str(root))
    assert p.returncode != 0
    assert "dirty" in p.stderr


def test_wrapper_never_deletes_a_completed_candidate(wrapper_sandbox):
    """--force does rm -rf, so a mistyped re-run must not destroy a good build."""
    root, stock, catalog, summary = wrapper_sandbox
    src = _libgphoto2_fixture(root.parent / "libgp-ok")
    date = subprocess.run(["date", "+%Y%m%d"], capture_output=True, text=True).stdout.strip()
    prior = root / "out" / f"astro-v99-t-{date}"
    prior.mkdir(parents=True)
    manifest = prior / "astro-candidate-manifest.json"
    manifest.write_text('{"keep": true}')

    p = _wrapper(root, "--version", "99", "--slug", "t", "--stock", str(stock),
                 "--catalog", str(catalog), "--summary", str(summary), "--skip-doctor",
                 "--libgphoto2", str(src))
    assert p.returncode != 0
    assert "COMPLETED candidate" in p.stderr, p.stderr
    assert manifest.is_file(), "the completed candidate must still be on disk"


def test_wrapper_rejects_a_worktree_as_source(wrapper_sandbox):
    """A linked worktree's .gitfile is unresolvable inside the container mount."""
    root, stock, catalog, summary = wrapper_sandbox
    wt = root.parent / "worktree-src"
    wt.mkdir()
    (wt / "configure.ac").write_text("x\n")
    (wt / ".git").write_text(
        "gitdir: /somewhere/else/.git/worktrees/other\n"   # a FILE, not a directory
    )
    p = _wrapper(root, "--version", "99", "--stock", str(stock), "--catalog", str(catalog),
                 "--summary", str(summary), "--skip-doctor", "--libgphoto2", str(wt))
    assert p.returncode != 0
    assert "self-contained" in p.stderr, p.stderr


def test_wrapper_rejects_dirty_libgphoto2_source(wrapper_sandbox):
    """The build compiles what is on disk, so a dirty tree breaks pin provenance."""
    root, stock, catalog, summary = wrapper_sandbox
    src = root.parent / "libgp"
    (src / ".git").mkdir(parents=True)
    (src / "configure.ac").write_text("x\n")
    run(["git", "init", "-q"], cwd=src)
    (src / "dirty.txt").write_text("untracked\n")
    p = _wrapper(root, "--version", "99", "--stock", str(stock), "--catalog", str(catalog),
                 "--summary", str(summary), "--skip-doctor", "--libgphoto2", str(src))
    assert p.returncode != 0
    assert "dirty" in p.stderr


def test_wrapper_rejects_stale_build_dir_in_source(wrapper_sandbox):
    root, stock, catalog, summary = wrapper_sandbox
    src = root.parent / "libgp2"
    (src / ".git").mkdir(parents=True)
    (src / "configure.ac").write_text("x\n")
    run(["git", "init", "-q"], cwd=src)
    run(["git", "add", "-A"], cwd=src)
    run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"], cwd=src)
    (src / "build").mkdir()
    p = _wrapper(root, "--version", "99", "--stock", str(stock), "--catalog", str(catalog),
                 "--summary", str(summary), "--skip-doctor", "--libgphoto2", str(src))
    assert p.returncode != 0
    assert "stale build" in p.stderr


def test_wrapper_help_documents_the_failure_modes():
    """The header is the documentation; it must keep naming what went wrong."""
    p = run(["bash", str(WRAPPER), "--help"])
    assert p.returncode == 0
    out = p.stdout.lower()
    for phrase in ["firmwareinfo", "worktree", "orphan", "ubireader", "slirp4netns"]:
        assert phrase in out, f"header should still explain the '{phrase}' failure mode"


# ---------------------------------------------------------------------------
# scripts/build-doctor.sh
#
# The rule it enforces: prove a prerequisite WORKS, never merely that it exists.
# All six 2026-11-06 faults were "present but broken", so existence checks are
# precisely what failed. These tests use --offline plus fixture homes so they do
# not need Docker, and assert the diagnosis text rather than just an exit code.
def test_doctor_reports_gate_tools_off_path(tmp_path: Path):
    """bwrap/slirp4netns installed but off PATH must say 'not on PATH', not 'install it'."""
    fakehome = tmp_path / "home"
    (fakehome / ".local" / "bin").mkdir(parents=True)
    for tool in ("bwrap", "slirp4netns"):
        (fakehome / ".local" / "bin" / tool).write_text("#!/bin/sh\nexit 0\n")
        (fakehome / ".local" / "bin" / tool).chmod(0o755)

    env = clean_env(HOME=str(fakehome), PATH="/usr/bin:/bin", TMPDIR=str(tmp_path))
    p = run(["bash", str(DOCTOR), "--offline",
             "--libgphoto2", str(tmp_path / "nope"),
             "--stock", str(tmp_path / "nope.zip"),
             "--catalog", str(tmp_path / "nope-catalog")], env=env)
    assert p.returncode == 1
    out = p.stdout
    assert "NOT on PATH" in out, "must distinguish off-PATH from not-installed"
    assert "export PATH" in out, "must give the fix"


def test_doctor_distinguishes_worktree_from_non_git(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "configure.ac").write_text("x\n")
    (wt / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n")
    env = clean_env(TMPDIR=str(tmp_path))
    p = run(["bash", str(DOCTOR), "--offline", "--libgphoto2", str(wt),
             "--stock", str(tmp_path / "s.zip"), "--catalog", str(tmp_path / "c")], env=env)
    assert p.returncode == 1
    assert "WORKTREE" in p.stdout, p.stdout
    assert "git clone --no-checkout" in p.stdout, "must give the clone command"


def test_doctor_names_a_broken_ubireader(tmp_path: Path):
    fakehome = tmp_path / "home"
    bindir = fakehome / ".local" / "bin"
    bindir.mkdir(parents=True)
    wrapper = bindir / "ubireader_extract_files"
    wrapper.write_text("#!/bin/sh\necho \"ModuleNotFoundError: No module named 'ubireader'\" >&2\nexit 1\n")
    wrapper.chmod(0o755)
    # PATH must not contain a working ubireader, or the doctor would correctly
    # prefer it and this branch would never be reached.
    env = clean_env(HOME=str(fakehome), PATH=f"{bindir}:/usr/bin:/bin", TMPDIR=str(tmp_path))
    p = run(["bash", str(DOCTOR), "--offline", "--libgphoto2", str(tmp_path / "x"),
             "--stock", str(tmp_path / "s.zip"), "--catalog", str(tmp_path / "c")], env=env)
    assert p.returncode == 1
    assert "BROKEN" in p.stdout, p.stdout
    assert "ubireader-docker" in p.stdout, "must point at the committed bridge"


def test_doctor_exit_zero_needs_everything_green(tmp_path: Path):
    """A RED doctor must exit non-zero -- it gates build-astro.sh."""
    env = clean_env(TMPDIR=str(tmp_path))
    p = run(["bash", str(DOCTOR), "--offline", "--libgphoto2", str(tmp_path / "x"),
             "--stock", str(tmp_path / "s.zip"), "--catalog", str(tmp_path / "c")], env=env)
    assert p.returncode == 1
    assert "DOCTOR: RED" in p.stdout

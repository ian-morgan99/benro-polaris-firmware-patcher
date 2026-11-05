"""Offline tests for scripts/shipped-marker-check.sh.

No container, no camera, no cross-toolchain: the gate works on a git checkout and
plain files, so a synthetic repo plus fake .so blobs exercise every verdict.

The v95 defect this gate exists to catch: provenance said one thing, the shipped
ptp2.so carried something else. A green gate that cannot see that is worse than
no gate, so each verdict path is pinned here.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "shipped-marker-check.sh"

# Introduced by the baseline-only commit; 41 chars, inside the gate's 18-60 window.
MARKER = "cancelling deferred camera-timed fallback"
# The gate refuses any artifact with no pentax-bulb literals at all.
PROBE = "pentax-bulb: unrelated literal that survives compilation"


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=env)


def make_repo(tmp_path):
    """built branch lacks the fix; baseline branch carries it."""
    repo = tmp_path / "libgphoto2"
    (repo / "camlibs" / "ptp2").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "built")
    src = repo / "camlibs" / "ptp2" / "library.c"
    src.write_text('const char *a = "%s";\n' % PROBE + "// no fix here\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    built = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "-q", "-b", "baseline")
    src.write_text('const char *a = "%s";\n' % PROBE
                   + 'const char *b = "%s";\n' % MARKER)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pentax: honour cancel before deferred capture")
    baseline = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "built")
    return repo, built, baseline


def artifact(path, *literals):
    """A stripped .so is just bytes; `strings` reads literals from any file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"".join(s.encode() + b"\0" for s in literals))
    return path


def run(repo, so, built, baseline, ref=None):
    cmd = ["bash", str(SCRIPT), str(so), str(repo), built, baseline]
    if ref is not None:
        cmd.append(str(ref))
    return subprocess.run(cmd, capture_output=True, text=True)


def test_gate_script_exists_and_is_executable():
    assert SCRIPT.is_file(), "shipped-marker-check.sh must live in the repo it guards"
    assert os.access(SCRIPT, os.X_OK)


def test_missing_fix_fails_when_reference_proves_it(tmp_path):
    """The v95 signature: pin regressed, artifact agrees with the regressed pin."""
    repo, built, baseline = make_repo(tmp_path)
    so = artifact(tmp_path / "ptp2.so", PROBE)                      # no fix
    ref = artifact(tmp_path / "ref" / "ptp2.so", PROBE, MARKER)     # has fix
    r = run(repo, so, built, baseline, ref)
    assert r.returncode == 1
    assert "RESULT: FAIL (MISSING)" in r.stdout, r.stdout
    assert "Do not describe this release as carrying the baseline" in r.stdout


def test_leak_fails_when_artifact_carries_unpinned_code(tmp_path):
    repo, built, baseline = make_repo(tmp_path)
    so = artifact(tmp_path / "ptp2.so", PROBE, MARKER)   # present, but not in built tree
    ref = artifact(tmp_path / "ref" / "ptp2.so", PROBE)
    r = run(repo, so, built, baseline, ref)
    assert r.returncode == 1
    assert "RESULT: FAIL (LEAK)" in r.stdout, r.stdout


def test_no_reference_is_inconclusive_never_a_pass(tmp_path):
    """Agreement with a regressed pin is exactly the v95 failure, so it must not pass."""
    repo, built, baseline = make_repo(tmp_path)
    so = artifact(tmp_path / "ptp2.so", PROBE)
    r = run(repo, so, built, baseline)
    assert r.returncode == 1
    assert "RESULT: INCONCLUSIVE" in r.stdout, r.stdout


def test_artifact_without_log_literals_is_inconclusive(tmp_path):
    """Logging compiled out means markers cannot discriminate; never call that clean."""
    repo, built, baseline = make_repo(tmp_path)
    so = tmp_path / "ptp2.so"
    so.write_bytes(b"\x7fELF\x02\x01\x01\x00no debug strings here at all")
    r = run(repo, so, built, baseline)
    assert r.returncode == 1
    assert "RESULT: INCONCLUSIVE" in r.stdout, r.stdout


def test_candidate_carrying_baseline_passes(tmp_path):
    """Nothing missing -> nothing to verify."""
    repo, built, baseline = make_repo(tmp_path)
    so = artifact(tmp_path / "ptp2.so", PROBE, MARKER)
    ref = artifact(tmp_path / "ref" / "ptp2.so", PROBE, MARKER)
    # built == baseline: the candidate carries everything the baseline has.
    r = run(repo, so, baseline, baseline, ref)
    assert r.returncode == 0, r.stdout
    assert "RESULT: PASS" in r.stdout, r.stdout


def test_scope_is_derived_from_the_artifact_name(tmp_path):
    """A camlib .so only contains its own directory; testing others yields false MISSING."""
    repo, built, baseline = make_repo(tmp_path)
    so = artifact(tmp_path / "ptp2.so", PROBE)
    r = run(repo, so, built, baseline)
    assert "scope    : camlibs/ptp2" in r.stdout, r.stdout


def test_unrecognised_artifact_name_is_refused(tmp_path):
    repo, built, baseline = make_repo(tmp_path)
    weird = tmp_path / "not-an-artifact.txt"
    weird.write_text("x")
    r = run(repo, weird, built, baseline)
    assert r.returncode == 1
    assert "unrecognized artifact name" in (r.stdout + r.stderr)


def test_missing_arguments_fail_closed():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode != 0

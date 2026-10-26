"""Gate: is plate solving actually merged into this branch, and buildable? (#234-adjacent)

Plate solving lives entirely on ``upstream/astro-plate-solving``, 124 commits ahead of
``main``. As of writing NONE of its code is on ``main`` -- only prose about it
(``docs/analysis/astro-mode-*.md``) and the camera *frame adapters* from ``1ac5ee5``,
whose diff adds zero solver code.

That distinction is the whole point of this file. Two things make it easy to believe
the feature has landed when it has not:

  * ``grep -ri 'plate sol'`` hits 18 times across 8 files, and every hit is a comment
    or a document. ``container/stage2_loader.c`` calls plate solving a "future
    on-demand use"; ``stage2_ipolar_adapter.h`` names it as a direction of travel.
    Neither is a solver.
  * ``git log --all -i --grep='plate.solve'`` prints ~20 commits, because ``--all``
    includes the remote branch. Only ``1ac5ee5`` is reachable from ``main``, and it
    touches ``stage2_ipolar_adapter.c`` / ``stage2_starshoot_adapter.c`` only.

So this gate keys off files, not words. It is red until the merge lands and green
after -- never skipped in the normal case, because a suite that skips instead of
asserting reads green while testing nothing (same reasoning as
tests/test_verify_shipped_artifacts.py: "a gate that cannot fail is a rubber stamp").

Prerequisites are checked alongside presence, because "merged" is not enough to
build: astrometry.net is fetched and cross-compiled at build time, so a checkout with
the sources but no toolchain still cannot produce a bundle.

Offline-safe: shells out to ``git`` against this repository only. No network, no rig.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# The branch that carries the feature, and where it is expected to come from.
SOURCE_BRANCH = "upstream/astro-plate-solving"
SOURCE_REMOTE = "upstream"
SOURCE_REMOTE_URL = "https://github.com/blaineam/benro-polaris-firmware-patcher.git"

# Deliberate, visible opt-out. Mirrors the repo's fail-closed convention
# (ALLOW_DIRTY_SOURCE in build_ptp2.sh): the only way past a closed gate is an
# explicit, unusual value -- never a silent default, and never mere truthiness.
ACK_ENV = "PLATE_SOLVING_NOT_MERGED_ACK"
ACK_VALUE = "acknowledged-not-merged"

# --- what "the feature is present" means ------------------------------------
# Keyed on files that exist ONLY as part of plate solving. Every entry was verified
# PRESENT on the source branch with `git cat-file -e <branch>:<path>`, so a green run
# proves the merge carried them rather than that this list was written from guesswork.
SOLVER_SOURCES = [
    "build-astro.sh",                     # build entry point (repo root)
    "container/astro/build_solver.sh",    # fetches + builds astrometry.net 0.98
    "container/astro/fetch-indexes.sh",   # index files for a focal range
    "container/astro/embed_webui.py",     # webui -> header, compiled into httpd
    "container/astro/polaris-solve.c",    # solver front end (GPL)
    "container/astro/polaris-extract.c",  # JPEG -> star list (MIT)
    "container/astro/polaris-skysim.c",   # synthetic sky field: solves with no camera
    "container/astro/polaris-mount.c",    # wire protocol + astronomical calcs
    "container/astro/polaris-httpd.c",    # serves the solve/align UI
]

# The GSL shim is what keeps the patcher MIT: astrometry.net needs GSL, gsl-an is
# GPLv3, so a BSD-3 shim is linked instead. Losing it silently changes the license of
# everything it links against, hence it is gated rather than left to review.
GSL_SHIM = [
    "container/astro/gslshim/gsl_shim.c",
    "container/astro/gslshim/include/gsl/gsl_matrix.h",
    "container/astro/gslshim/test_gsl_shim.c",
]

# On-device orchestration + the UI it drives.
ONDISK_ENTRY = "container/astro/ondisk/polaris-autosolve.sh"
WEBUI = [
    "container/astro/webui/index.html",
    "container/astro/webui/app.js",
    "container/astro/webui/app.css",
]

# Docs that travel with the feature. These sit at docs/ on the branch, NOT under
# container/astro/docs/ -- our own docs/analysis/ notes claim the latter and are wrong
# about it, so asserting the real paths also corrects that record.
DOCS = [
    "docs/PLATE-SOLVING.md",
    "docs/LICENSE-AUDIT.md",
    "docs/ASTRO.md",
    # HOW-IT-WORKS.md is already tracked on main, so it never fails here; kept so a
    # merge that *replaces* it with the branch's astro-flavoured version is visible.
    "docs/HOW-IT-WORKS.md",
]

# Everything build-astro.sh feeds to arm-linux-gnueabi-gcc on one line. A merge that
# brings polaris-httpd.c but not its siblings produces a link error deep in a docker
# run, which reads as "the build is broken" rather than "the merge was partial".
HTTPD_COMPILE_INPUTS = [
    "container/astro/polaris-link.c",     # single registered TCP session
    "container/astro/polaris-jog.c",      # lease-based jog, server-side dead-man
    "container/astro/polaris-prog.c",     # program engine
    "container/astro/polaris-astro.c",    # astro session lifecycle
]
STANDALONE_TOOLS = [
    "container/astro/polaris-logwatch.c",
    "container/astro/polaris-match.c",
]
# Headers are embedded at build time: embed_webui.py writes webui.h, which
# polaris-httpd.c includes with -I/tmp.
DOCKERFILE = "docker/Dockerfile"
SITE_CONF_EXAMPLE = "container/astro/ondisk/site.conf.example"

# astrometry.net is GPL v2+. Fetched at build time and run as a separate process;
# vendoring it into the MIT tree would relicense the patcher.
VENDORED_SOLVER_DIR = "container/astrometry"

# MIT-licensed astro sources that must never include a GPL header directly.
MIT_SOURCES_FOR_BOUNDARY = [
    "container/astro/polaris-httpd.c",
    "container/astro/polaris-extract.c",
    "container/astro/polaris-mount.c",
]

# Build-time prerequisites, read from build-astro.sh / build_solver.sh on the branch.
#
# build_solver.sh does NOT run astrometry.net's configure. It hand-compiles a curated
# subset -- util/*.c, libkd/*.c, qfits-an/*.c, gslshim/gsl_shim.c and four solver files
# (solver.c, quad-utils.c, verify.c, tweak2.c) -- straight into $CC, archives them with
# $AR, and links polaris-solve against that. libjpeg 9f is fetched and built from
# source. So swig / wcslib / netpbm are NOT required; the real floor is a C toolchain,
# ar, make (for libjpeg), curl-or-wget, and docker for build-astro.sh itself.
#
# Observed in this VS Code Flatpak sandbox: gcc/make/autoconf present. The docker CLI
# is NOT on PATH here -- VS Code runs as a Flatpak, so /var/run/docker.sock is not
# bind-mounted and the host binary only shows up at /run/host/usr/bin/docker. It is
# still reachable through the portal: `flatpak-spawn --host docker info` returns the
# host daemon (verified: 29.1.3, root=/var/lib/docker), and workspace paths mount into
# containers with correct uid mapping. So docker_available() checks both routes.
#
# Caveat found the hard way: the sandbox /tmp is private. flatpak-spawn starts in our
# cwd, so a portal docker call made while cd'd into sandbox /tmp fails with
# "Failed to change to directory" even though docker itself is fine. Run portal docker
# from a host-visible directory (the workspace).
BUILD_PREREQS_HARD = [
    ("docker", "build-astro.sh: `command -v docker || exit 1`, then `docker info`"),
]
BUILD_PREREQS_SOFT = [
    ("make", "libjpeg 9f is configured and built from source by build_solver.sh"),
    ("gcc", "host-side solver build (build_solver.sh target=host)"),
    ("ar", "build_solver.sh: `$AR rcs libpolarisastro.a obj/*.o`"),
]
# The arm build additionally needs the cross toolchain, which the Dockerfile installs
# via apt (gcc-arm-linux-gnueabi). Checked only when it is expected outside docker.
CROSS_TOOLCHAIN = "arm-linux-gnueabi-gcc"


def docker_available():
    """Return how docker is reachable: 'local', 'portal', or None.

    build-astro.sh calls `command -v docker` and then `docker info`, so a daemon that
    is merely installed is not enough -- it must answer. Inside a Flatpak the CLI is
    absent from PATH but the host daemon answers via flatpak-spawn, which is a real,
    working path (build-astro.sh runs fine with a one-line shim on PATH).
    """
    if shutil.which("docker"):
        probe = subprocess.run(["docker", "info"], capture_output=True, text=True)
        if probe.returncode == 0:
            return "local"
    if shutil.which("flatpak-spawn"):
        probe = subprocess.run(
            ["flatpak-spawn", "--host", "docker", "info"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if probe.returncode == 0:
            return "portal"
    return None



def git(*args):
    """Run git in the repo. Returns stdout, or None if it failed."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True, text=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def tracked_paths():
    """Paths in the index. In CI this equals HEAD; locally it also covers staged."""
    out = git("ls-files")
    if out is None:
        pytest.skip("not a git checkout -- cannot assert merge state")
    return {line.strip() for line in out.splitlines() if line.strip()}


def branch_exists(ref):
    return git("rev-parse", "--verify", "--quiet", ref) is not None


def merged():
    """True when the solver's build entry point and front end are both tracked."""
    return {"build-astro.sh", "container/astro/polaris-solve.c"} <= tracked_paths()


def acknowledged():
    """The opt-out fires ONLY on the exact sentinel value."""
    return os.environ.get(ACK_ENV) == ACK_VALUE


# Red until merged, green once merged. Skips only on an explicit acknowledgement, so a
# release branch cut before the merge can still go green -- deliberately, and loudly.
unless_acknowledged = pytest.mark.skipif(
    acknowledged(),
    reason=f"gap acknowledged via {ACK_ENV}={ACK_VALUE}",
)


def _missing(paths):
    present = tracked_paths()
    return [p for p in paths if p not in present]


def _fmt(paths):
    return "\n      ".join(paths) if paths else "(none)"


# ---------------------------------------------------------------------------
# 1. The feature itself -- fails while unmerged, passes after the merge
# ---------------------------------------------------------------------------

@unless_acknowledged
def test_solver_sources_present():
    missing = _missing(SOLVER_SOURCES)
    assert not missing, (
        "plate-solving sources are not tracked on this branch:\n      "
        + _fmt(missing)
        + f"\n  They exist only on {SOURCE_BRANCH}. Merge that branch, or set "
        f"{ACK_ENV}={ACK_VALUE} to ship without it."
    )


@unless_acknowledged
def test_build_entry_point_is_executable():
    """build-astro.sh is invoked as ./build-astro.sh; mode 100644 breaks it."""
    path = ROOT / "build-astro.sh"
    if not path.is_file():
        pytest.skip("build-astro.sh not merged yet")
    assert os.access(path, os.X_OK), (
        f"{path} is present but not executable. Fix with:\n"
        "      git update-index --chmod=+x build-astro.sh"
    )


@unless_acknowledged
def test_ondisk_orchestration_present():
    missing = _missing([ONDISK_ENTRY])
    assert not missing, (
        "on-device solve orchestration is missing:\n      " + _fmt(missing)
    )


@unless_acknowledged
def test_webui_present():
    missing = _missing(WEBUI)
    assert not missing, (
        "solve/align web UI is missing; embed_webui.py fails without it:\n      "
        + _fmt(missing)
    )


@unless_acknowledged
def test_docs_travel_with_feature():
    """Assert the real docs/ paths -- our analysis notes say container/astro/docs/."""
    missing = _missing(DOCS)
    assert not missing, (
        "plate-solving docs are missing (they live at docs/ on the source branch, "
        "not container/astro/docs/):\n      " + _fmt(missing)
    )


@unless_acknowledged
def test_httpd_compile_inputs_present():
    """polaris-httpd is one binary from five .c files; a partial merge cannot link."""
    missing = _missing(HTTPD_COMPILE_INPUTS + STANDALONE_TOOLS)
    assert not missing, (
        "polaris-httpd compile inputs are missing -- build-astro.sh compiles these "
        "on a single arm-linux-gnueabi-gcc line:\n      " + _fmt(missing)
    )


@unless_acknowledged
def test_dockerfile_present():
    """build-astro.sh does `docker build -f docker/Dockerfile`; without it, exit 1."""
    missing = _missing([DOCKERFILE])
    assert not missing, (
        f"{DOCKERFILE} is missing; build-astro.sh builds its cross toolchain from "
        "it."
    )


@unless_acknowledged
def test_site_conf_example_ships():
    """build-astro.sh copies it into the bundle; LAT/LON are required on-device."""
    missing = _missing([SITE_CONF_EXAMPLE])
    assert not missing, (
        f"{SITE_CONF_EXAMPLE} is missing; build-astro.sh copies it into the bundle "
        "and the README tells the user to edit LAT/LON in it."
    )


# ---------------------------------------------------------------------------
# 2. Licensing boundary -- holds before AND after the merge
# ---------------------------------------------------------------------------

def test_gpl_solver_is_never_vendored():
    """astrometry.net (GPL v2+) is fetched at build time, never committed."""
    vendored = [p for p in tracked_paths() if p.startswith(VENDORED_SOLVER_DIR + "/")]
    assert not vendored, (
        f"{len(vendored)} GPL solver files are committed under "
        f"{VENDORED_SOLVER_DIR}/ -- e.g. {vendored[:3]}. astrometry.net must be "
        "downloaded by build_solver.sh and run as a separate process so the "
        "patcher stays MIT."
    )


def test_gsl_shim_present_when_solver_present():
    """gsl-an is GPLv3; the BSD-3 shim is what keeps the linked binary clean."""
    if not merged():
        pytest.skip("solver not merged yet -- nothing links GSL")
    missing = _missing(GSL_SHIM)
    assert not missing, (
        "solver is merged but the BSD-3 GSL shim is not:\n      " + _fmt(missing)
        + "\n  Without it the build pulls in GPLv3 gsl-an."
    )


def test_mit_sources_do_not_include_gpl_headers():
    """The process boundary is also an #include boundary; one stray -I breaks it."""
    if not merged():
        pytest.skip("solver not merged yet")
    offenders = []
    for rel in MIT_SOURCES_FOR_BOUNDARY:
        path = ROOT / rel
        if not path.is_file():
            continue
        for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#include") and any(
                tok in stripped for tok in ("astrometry", "gsl", "an-")
            ):
                offenders.append(f"{rel}:{n}: {stripped}")
    assert not offenders, (
        "MIT source includes a GPL header, breaking the process boundary:\n      "
        + _fmt(offenders)
    )


# ---------------------------------------------------------------------------
# 3. Prerequisites -- the merge is not "done" until it can actually be built
# ---------------------------------------------------------------------------

def test_source_branch_is_fetched():
    """The merge cannot happen if we cannot see what we are merging."""
    if merged():
        pytest.skip("solver already merged -- branch ref no longer required")
    assert branch_exists(SOURCE_BRANCH), (
        f"{SOURCE_BRANCH} is not present locally. Fetch it first:\n"
        f"      git remote add {SOURCE_REMOTE} {SOURCE_REMOTE_URL}\n"
        f"      git fetch {SOURCE_REMOTE} astro-plate-solving"
    )


def test_source_branch_is_what_we_think_it_is():
    """Guard against merging a stale or wrong ref: it must carry everything.

    Checks every list this gate asserts on HEAD, so the expected paths are proven
    against upstream rather than assumed. If upstream stops carrying one, the
    assertion above is wrong and must be updated -- not quietly deleted.
    """
    if merged() or not branch_exists(SOURCE_BRANCH):
        pytest.skip("solver merged, or source branch not fetched")
    out = git("ls-tree", "-r", "--name-only", SOURCE_BRANCH) or ""
    tree = {line.strip() for line in out.splitlines()}
    expected = (
        SOLVER_SOURCES + GSL_SHIM + [ONDISK_ENTRY] + WEBUI + DOCS
        + HTTPD_COMPILE_INPUTS + STANDALONE_TOOLS
        + [DOCKERFILE, SITE_CONF_EXAMPLE]
    )
    absent = [p for p in expected if p not in tree]
    assert not absent, (
        f"{SOURCE_BRANCH} does not contain paths this gate expects:\n      "
        + _fmt(absent)
        + "\n  The branch moved, the wrong ref was fetched, or this gate's "
        "expected lists are stale."
    )


def test_source_branch_does_not_vendor_the_gpl_solver():
    """The upstream we merge from must itself keep astrometry.net out of git."""
    if not branch_exists(SOURCE_BRANCH):
        pytest.skip(f"{SOURCE_BRANCH} not fetched")
    out = git("ls-tree", "-r", "--name-only", SOURCE_BRANCH) or ""
    vendored = [line.strip() for line in out.splitlines()
                if line.strip().startswith(VENDORED_SOLVER_DIR + "/")]
    assert not vendored, (
        f"{SOURCE_BRANCH} commits {len(vendored)} files under "
        f"{VENDORED_SOLVER_DIR}/ -- e.g. {vendored[:3]}. Merging it would vendor "
        "GPL code into the MIT tree."
    )


def test_source_branch_is_still_ahead():
    """Informational: how much is unmerged. Fails only if it reads as merged."""
    if merged() or not branch_exists(SOURCE_BRANCH):
        pytest.skip("solver merged, or source branch not fetched")
    out = git("rev-list", "--count", f"HEAD..{SOURCE_BRANCH}")
    ahead = int(out.strip()) if out and out.strip().isdigit() else 0
    assert ahead > 0, (
        f"{SOURCE_BRANCH} reports 0 commits ahead of HEAD yet its sources are not "
        "tracked -- the merge is partial or the ref is wrong."
    )


def test_build_toolchain_prerequisites():
    """'Merged' is not 'buildable'. Skips rather than fails: a missing toolchain is
    an environment gap, not an unmerged feature, and CI hosts legitimately lack
    docker."""
    if not merged():
        pytest.skip("solver not merged yet")
    route = docker_available()
    assert route, (
        "solver sources are merged but the build cannot run: no reachable docker "
        "daemon. build-astro.sh exits 1 without docker, and again if `docker info` "
        "fails. Inside a Flatpak sandbox a shim like "
        "'exec flatpak-spawn --host docker \"$@\"' on PATH is sufficient."
    )
    soft_missing = [name for name, _ in BUILD_PREREQS_SOFT
                    if shutil.which(name) is None]
    if soft_missing:
        pytest.skip(
            "docker present, but host-build tools are absent: "
            + ", ".join(f"{n} ({why})" for n, why in BUILD_PREREQS_SOFT
                        if n in soft_missing)
            + " -- the docker cross build is still possible"
        )


# ---------------------------------------------------------------------------
# 4. The gate can fail -- prove it, so a green run means something
# ---------------------------------------------------------------------------

def test_no_partial_merge():
    """merged() must not go True while the rest of the stack is still absent.

    The failure mode this guards: build-astro.sh lands but polaris-extract.c does
    not. Sections 1-2 would then half-run, and a reviewer reading "solver merged"
    would ship a bundle that cannot link.
    """
    if not merged():
        pytest.skip("nothing merged yet")
    missing = _missing(SOLVER_SOURCES)
    assert not missing, (
        "partial merge: build entry point is tracked but these are not:\n      "
        + _fmt(missing)
    )


def test_missing_helper_reports_every_gap():
    """A gate that names one file hides the other eight. Assert it lists all."""
    probe = ["container/astro/definitely_not_real_a.c",
             "container/astro/definitely_not_real_b.c"]
    found = _missing(probe)
    assert found == probe, f"_missing() under-reported: asked for {probe}, got {found}"


@pytest.mark.parametrize("value,expected", [
    (None, False), ("", False), ("1", False), ("true", False), ("yes", False),
    ("ACKNOWLEDGED-NOT-MERGED", False), (ACK_VALUE, True),
])
def test_opt_out_requires_exact_sentinel(monkeypatch, value, expected):
    """Fail closed: truthy-but-wrong values must NOT silence the gate."""
    if value is None:
        monkeypatch.delenv(ACK_ENV, raising=False)
    else:
        monkeypatch.setenv(ACK_ENV, value)
    assert acknowledged() is expected, (
        f"{ACK_ENV}={value!r} {'silenced' if expected else 'did not silence'} the "
        "gate; only the exact sentinel may"
    )

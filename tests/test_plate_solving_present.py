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
import re
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
# 4. GPL corresponding source -- the bundle must never ship GPL binaries bare
# ---------------------------------------------------------------------------

GPL_TEXT = "container/astro/licenses/GPL-2.txt"

# What build-astro.sh must actually *write*, matched at command position. Matching
# bare filenames is useless -- they also appear in the README text we generate, so
# deleting the copy command leaves the needle present and the test green. Each
# pattern must anchor on the command that produces the artifact.
OFFER_COMMANDS = [
    (r'^cp\s+\S+\s+"\$LIC/astrometry\.net-', "astrometry.net source copied into licenses/"),
    (r'^cp\s+\S+\s+"\$LIC/jpeg-', "libjpeg source copied into licenses/"),
    (r'^tar czf "\$LIC/polaris-build-recipe', "build recipe + GSL shim archived"),
    (r'^cp\s+\S+\s+"\$LIC/COPYING-GPL-2', "GPL text copied into licenses/"),
    (r'^cat > "\$SD_ASTRO/SOURCE-OFFER\.txt"', "written offer created inside the card tree"),
    (r'^cp\s+\S+\s+"\$SD_ASTRO/COPYING-GPL-2', "GPL text copied into the card tree"),
    (r'sha256sum "\$LIC/', "shipped tarballs fingerprinted"),
]


def _build_script():
    return (ROOT / "build-astro.sh").read_text(errors="replace")


def test_gpl_text_is_vendored():
    """The GPL text must be in the repo, not fetched at build time.

    A build that downloads the licence text fails offline and can silently ship a
    bundle with no licence file if the fetch is skipped.
    """
    path = ROOT / GPL_TEXT
    assert path.is_file(), (
        f"{GPL_TEXT} is missing; build-astro.sh copies it into every bundle."
    )
    text = path.read_text(errors="replace")
    assert "Version 2, June 1991" in text, (
        f"{GPL_TEXT} does not look like the GPL v2 text -- first line: "
        f"{text.splitlines()[0] if text else '(empty)'!r}"
    )
    assert len(text) > 15000, f"{GPL_TEXT} is truncated ({len(text)} bytes)"


def test_build_script_ships_corresponding_source():
    """polaris-solve/polaris-skysim are GPL v2+; §3 requires source with the binary."""
    script = _build_script()
    missing = [why for pat, why in OFFER_COMMANDS
               if not re.search(pat, script, re.MULTILINE)]
    assert not missing, (
        "build-astro.sh no longer produces a complete corresponding-source set:\n"
        "      " + _fmt(missing)
    )


def test_source_offer_step_is_fail_closed():
    """A licence failure must remove the GPL binaries, not just print a warning.

    The step runs after the container build (the container is what fetches the
    tarballs), so by the time it can fail the GPL binaries are already in the
    bundle. Exiting 1 alone would leave them there for anyone who ignores the
    exit code -- so the guard deletes them.
    """
    script = _build_script()
    assert "no_source()" in script, "the fail-closed licence guard was removed"
    body = script.split("no_source(){", 1)[-1].split("\n}", 1)[0]
    for needle in ("polaris-solve", "polaris-skysim", "exit 1"):
        assert needle in body, (
            f"no_source() no longer handles {needle!r}; an incomplete bundle could "
            "be dragged onto an SD card with GPL binaries and no source"
        )


def test_incomplete_bundle_drops_gpl_binaries(tmp_path):
    """Behavioural: run build-astro.sh with a stub docker and no cached source.

    This is the only way to test the guard without a cross toolchain or an 11 MB
    download. The stub stands in for `docker build`/`docker run` and writes the same
    bundle files the real container would, so the licence step runs against a
    realistic tree. Expected: exit non-zero AND polaris-solve/polaris-skysim gone.
    """
    if not merged():
        pytest.skip("solver not merged yet")

    work = tmp_path / "repo"
    shutil.copytree(
        ROOT, work,
        ignore=shutil.ignore_patterns("out", ".git", "__pycache__", "*.pyc"),
        symlinks=True,
    )
    stub = tmp_path / "stubbin"
    stub.mkdir()
    (stub / "docker").write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do case "$a" in run) MODE=run;; build) MODE=build;; esac; done\n'
        'if [ "$MODE" = run ]; then\n'
        '  D="$FAKE_OUT/COPY-TO-SD-CARD-ROOT/polaris-astro"\n'
        '  mkdir -p "$D"\n'
        '  for b in polaris-solve polaris-extract polaris-skysim polaris-mount '
        'polaris-httpd polaris-logwatch polaris-match; do : > "$D/$b"; done\n'
        '  : > "$D/README.txt"\n'
        'fi\n'
        "exit 0\n"
    )
    (stub / "docker").chmod(0o755)

    out = tmp_path / "out"
    env = dict(os.environ, PATH=f"{stub}:{os.environ['PATH']}", FAKE_OUT=str(out))
    proc = subprocess.run(
        ["sh", "build-astro.sh", "--no-indexes", "--out", str(out),
         "--src-cache", str(tmp_path / "cold-cache")],
        cwd=str(work), env=env, capture_output=True, text=True,
    )
    card = out / "COPY-TO-SD-CARD-ROOT" / "polaris-astro"
    assert proc.returncode != 0, (
        "build succeeded with no corresponding source available; the guard is inert. "
        f"stdout tail: {proc.stdout[-400:]}"
    )
    for gpl in ("polaris-solve", "polaris-skysim"):
        assert not (card / gpl).exists(), (
            f"{gpl} survived a failed licence step -- it would be shipped without "
            "corresponding source, violating GPL v2 §3"
        )
    # The MIT/BSD-3 half of the bundle is fine to keep; only the GPL binaries must go.
    assert (card / "polaris-extract").exists(), (
        "the guard removed more than the GPL binaries"
    )


def test_bundle_on_disk_is_licence_complete():
    """If a bundle has been built here, it must be licence-complete.

    Skips when no bundle exists -- out/ is gitignored and CI never builds one.
    """
    bundle = ROOT / "out" / "astro-bundle"
    if not bundle.is_dir():
        pytest.skip("no bundle built locally (out/ is gitignored)")
    lic = bundle / "licenses"
    card = bundle / "COPY-TO-SD-CARD-ROOT" / "polaris-astro"
    solver = card / "polaris-solve"
    if not solver.is_file():
        pytest.skip("bundle has no polaris-solve -- nothing GPL to offer source for")
    assert lic.is_dir(), (
        f"{solver} is GPL v2+ but {lic} is absent -- §3 violation"
    )
    for name in ("astrometry.net-0.98.tar.gz", "jpeg-9f.tar.gz",
                 "COPYING-GPL-2.txt", "polaris-build-recipe.tar.gz",
                 "README-GPL.txt"):
        assert (lic / name).is_file(), f"licenses/{name} missing from the bundle"
    for name in ("SOURCE-OFFER.txt", "COPYING-GPL-2.txt"):
        assert (card / name).is_file(), (
            f"{name} missing: users drag only COPY-TO-SD-CARD-ROOT/ onto the card, "
            "so an offer outside it never reaches the device"
        )


def test_bundle_licence_census_matches_the_source():
    """Re-derive the licence census and check the shipped README-GPL.txt agrees.

    This exists because the first version of that text claimed "176 files, 156 BSD,
    1 GPL" -- it counted the glob expansion rather than what is compiled, and a
    regex matched "3-clause BSD" as GPLv3 because it contains a digit. Both errors
    were invisible to every other check here. Skips unless the source cache is
    present, since the tree is downloaded at build time and not committed.
    """
    cache = ROOT / "out" / ".astro-src-cache"
    src = next(iter(sorted(cache.glob("astrometry.net-*"))), None)
    readme = ROOT / "out" / "astro-bundle" / "licenses" / "README-GPL.txt"
    if src is None or not readme.is_file():
        pytest.skip("no astrometry.net source cache / bundle to check against")

    # Mirror skip_file() from build_solver.sh.
    skip = {
        "md5", "ctmf", "simplexy", "bl-nl", "bl-nl-sort", "dfind2", "tpv",
        "index_pyutils", "pyspherematch", "jpl", "os-features-test",
        "qsort_reentrant", "cairoutils", "plotstuff", "dimage", "dallpeaks",
        "dcen3x3", "dfind", "dmedsmooth", "dobjects", "dselip", "dsmooth",
        "downsample-fits", "convolve-image", "coadd", "resample", "wcs-resample",
        "wcs-pv2sip", "wcs-to-tan", "wcsinfo", "hpsplit", "search-index",
        "get-healpix", "histogram2d", "sparsematrix", "wcs-match",
    }

    def skipped(p: Path) -> bool:
        stem = p.stem
        return (stem in skip or stem.startswith("test_") or stem.endswith("_test")
                or stem.startswith("kdtree_internal") or stem.startswith("plot")
                or stem.startswith("image2xy") or stem in
                {"an-pnmtofits", "an-fitstopnm"})

    counts = {"bsd": 0, "gpl2": 0, "gpl3": 0, "other": 0}
    total = 0
    paths = [p for sub in ("util", "libkd", "qfits-an")
             for p in sorted((src / sub).glob("*.c"))]
    # build_solver.sh also names these four explicitly rather than by glob.
    paths += [src / "solver" / n for n in
              ("solver.c", "quad-utils.c", "verify.c", "tweak2.c")]
    for p in paths:
        if not p.is_file() or skipped(p):
            continue
        total += 1
        low = p.read_text(errors="replace").lower()
        if "3-clause bsd" in low or "bsd style license" in low:
            counts["bsd"] += 1
        elif "either version 2 of the license" in low or "gpl v2 or later" in low:
            counts["gpl2"] += 1
        elif "version 3 of the license" in low or "gpl v3" in low:
            counts["gpl3"] += 1
        else:
            counts["other"] += 1

    # The claim under test: no GPLv3-only file is compiled, so the binary's
    # copyleft floor is GPL v2+, not the v3+ astrometry.net's own LICENSE asserts.
    assert counts["gpl3"] == 0, (
        f"{counts['gpl3']} GPLv3-only files are in the compiled set; the bundle's "
        "README-GPL.txt claims the copyleft floor is GPL v2-or-later and would be "
        "wrong. Re-check which files build_solver.sh skips."
    )
    assert counts["gpl2"] > 0, (
        "no GPL v2+ files found in the compiled set -- if qfits-an really went BSD "
        "then the bundle is not GPL and the whole source offer is unnecessary"
    )

    shipped = readme.read_text(errors="replace")
    # The README states the object count as 100 (99 glob files + our gsl_shim.c).
    assert f"{total} files from" in shipped or f"{total + 1} objects" in shipped, (
        f"README-GPL.txt does not match the re-derived compiled file count "
        f"({total} + gsl_shim.c = {total + 1} objects)"
    )
    assert f"{counts['bsd']}  3-clause BSD" in shipped, (
        f"README-GPL.txt BSD count is wrong; re-derived {counts['bsd']}"
    )
    assert f"{counts['gpl2']}  GPL v2-or-later" in shipped, (
        f"README-GPL.txt GPL count is wrong; re-derived {counts['gpl2']}"
    )


# ---------------------------------------------------------------------------
# 5. The gate can fail -- prove it, so a green run means something
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


def test_offer_patterns_are_not_vacuous():
    """Deleting any one licence step must actually fail the gate above.

    Substring needles were tried first and were useless: every artifact name also
    appears in the README text we generate, so commenting out the `cp` left the
    needle present and the test green. Each pattern is therefore anchored on the
    command that produces the artifact, and this test proves it by deleting that
    whole line and re-checking.
    """
    script = _build_script()
    for pat, why in OFFER_COMMANDS:
        hits = [ln for ln in script.splitlines() if re.search(pat, ln)]
        assert hits, f"pattern {pat!r} matches nothing already ({why})"
        stripped = "\n".join(ln for ln in script.splitlines()
                             if not re.search(pat, ln))
        assert not re.search(pat, stripped, re.MULTILINE), (
            f"pattern {pat!r} still matches after its command line was deleted -- "
            f"it is matching prose, not the step it claims to guard ({why})"
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

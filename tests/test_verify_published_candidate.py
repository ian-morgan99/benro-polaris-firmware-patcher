"""Regression tests for scripts/verify-published-astro-candidate.py (issue #292).

The bug class this gate exists to catch is "a check ran against a staging
directory, passed, and the archive actually published was incomplete" -- #58,
#280, #281 and #286 all shipped that way.  So these tests build real .zip files
and hand the verifier the archive, never a directory listing.

Fixtures are constructed here rather than read from out/, because out/ is
gitignored: a test that depends on a local build product passes on my machine
and silently does nothing in CI, which is the same failure mode being fixed.
"""

import os
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFIER = os.path.join(ROOT, "scripts", "verify-published-astro-candidate.py")

WIFI_SCRIPTS = [
    "polaris-autojoin.sh",
    "polaris-apsta.sh",
    "setup-wifi.sh",
    "wifi-keepalive.sh",
    "wifi-watch.sh",
]
WIFI_LICENSES = [
    "LICENCE-wifi.txt",
    "COPYING-LGPL-2.1.txt",
    "NOTICE-iw.txt",
    "NOTICE-wpa_supplicant.txt",
]


def run(candidate):
    proc = subprocess.run(
        [sys.executable, VERIFIER, candidate],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def add(zpath, root, name, data, mode):
    info = zipfile.ZipInfo(f"{root}/{name}")
    info.external_attr = (mode & 0xFFFF) << 16
    with zipfile.ZipFile(zpath, "a") as zf:
        zf.writestr(info, data)


GOOD_OFFER = (
    b"LGPL v2.1 applies to libnl 3.7.0; iw 5.19 is ISC; wpa_supplicant 2.10\n"
    b"is BSD-style. Corresponding source: the tarballs named above.\n"
)


def make_wifi_zip(path, *, licences=True, hook=True, exec_bit=True, offer=None,
                  empty_licence=None):
    mode = 0o100755 if exec_bit else 0o100644
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("polaris-wifi/", b"")
    for s in WIFI_SCRIPTS:
        add(path, "polaris-wifi", s, b"#!/bin/sh\necho hi\n", mode)
    for b in ("wpa_supplicant", "wpa_cli", "wpa_passphrase", "iw"):
        add(path, "polaris-wifi", b, b"\x7fELF\x02\x01\x01\x00" + b"\0" * 64, 0o100755)
    if hook:
        add(path, "polaris-wifi", "udhcpc.script", b"#!/bin/sh\n# bind hook\n", mode)
    if licences:
        add(path, "polaris-wifi", "LICENCE-wifi.txt",
            offer if offer is not None else GOOD_OFFER, 0o100644)
        copying = b"" if empty_licence == "COPYING-LGPL-2.1.txt" else \
            b"GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1\n"
        add(path, "polaris-wifi", "COPYING-LGPL-2.1.txt", copying, 0o100644)
        add(path, "polaris-wifi", "NOTICE-iw.txt", b"iw is ISC licensed.\n", 0o100644)
        add(path, "polaris-wifi", "NOTICE-wpa_supplicant.txt", b"wpa_supplicant is BSD-style.\n", 0o100644)


def make_astro_zip(path, *, exec_bit=True):
    mode = 0o100755 if exec_bit else 0o100644
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("polaris-astro/", b"")
    for s in ("install_astro.sh", "uninstall_astro.sh", "polaris-astro-boot.sh",
              "polaris-apsta.sh", "polaris-autojoin.sh", "autofocus.sh"):
        add(path, "polaris-astro", s, b"#!/bin/sh\necho hi\n", mode)
    add(path, "polaris-astro", "COPYING-GPL-2.txt", b"GNU GENERAL PUBLIC LICENSE\nVersion 2\n", 0o100644)
    add(path, "polaris-astro", "SOURCE-OFFER.txt", b"Complete corresponding source is offered.\n", 0o100644)


def make_candidate(tmp_path, *, wifi_kwargs=None, astro_exec=True):
    sd = tmp_path / "COPY-TO-SD-CARD-ROOT"
    sd.mkdir()
    make_wifi_zip(sd / "polaris-wifi.zip", **(wifi_kwargs or {}))
    make_astro_zip(sd / "polaris-astro.zip", exec_bit=astro_exec)
    # The offer check derives required version strings from the upstream
    # tarballs staged beside the bundle, so the fixture has to stage them too --
    # otherwise the check reports UNKNOWN and the version test proves nothing.
    lic = tmp_path / "licenses"
    lic.mkdir()
    for name in ("libnl-3.7.0.tar.gz", "iw-5.19.tar.gz", "wpa_supplicant-2.10.tar.gz"):
        (lic / name).write_bytes(b"\x1f\x8b stub")
    return str(tmp_path)


def test_good_candidate_is_consistent(tmp_path):
    rc, out = run(make_candidate(tmp_path))
    assert rc == 0, out
    assert "0 fail" in out
    assert "offer-names-versions: PASS" in out or "names every staged upstream version" in out


def test_missing_wifi_licences_fails(tmp_path):
    """Reproduces #286 exactly: copyleft binaries with no licence alongside them."""
    rc, out = run(make_candidate(tmp_path, wifi_kwargs={"licences": False}))
    assert rc == 1
    for name in WIFI_LICENSES:
        assert name in out, f"{name} omission not reported"


def test_missing_dhcp_hook_fails(tmp_path):
    """Reproduces #280: the kit calls `udhcpc -s $WDIR/udhcpc.script` but never shipped it."""
    rc, out = run(make_candidate(tmp_path, wifi_kwargs={"hook": False}))
    assert rc == 1
    assert "udhcpc.script" in out


def test_empty_licence_is_not_a_licence(tmp_path):
    """`[ -f ]` passes on a zero-byte COPYING; LGPL s4 does not.

    Built as a single archive member rather than appended over an existing one:
    two members with the same name make "which one wins" extractor-defined, so
    appending would assert on luck rather than on the check.
    """
    cand = make_candidate(tmp_path, wifi_kwargs={"empty_licence": "COPYING-LGPL-2.1.txt"})
    rc, out = run(cand)
    assert rc == 1
    assert "empty" in out


def test_non_executable_scripts_fail(tmp_path):
    """Boot gates features on `[ -x ]`, so a 644 script silently disables them."""
    rc, out = run(make_candidate(tmp_path, wifi_kwargs={"exec_bit": False}))
    assert rc == 1
    assert "executable-mode" in out


def test_astro_scripts_need_exec_bit(tmp_path):
    """The defect that shipped in .99: seven astro scripts were 644 in the archive."""
    rc, out = run(make_candidate(tmp_path, astro_exec=False))
    assert rc == 1
    assert "executable-mode" in out


def test_offer_must_name_a_version(tmp_path):
    """'libnl-, iw-' reads like an offer and provides none.

    The archive is rebuilt with the bad text rather than having a second member
    appended: appending leaves two members with the same name, and which one an
    extractor keeps is implementation-defined -- the test would then be asserting
    on whichever Python happened to pick.
    """
    cand = make_candidate(
        tmp_path,
        wifi_kwargs={"offer": b"libnl-, iw- are under LGPL/ISC. Source available on request.\n"},
    )
    rc, out = run(cand)
    assert rc == 1
    assert "offer-names-versions" in out


def test_traversal_entry_fails(tmp_path):
    cand = make_candidate(tmp_path)
    zpath = os.path.join(cand, "COPY-TO-SD-CARD-ROOT", "polaris-wifi.zip")
    add(zpath, "..", "evil.sh", b"#!/bin/sh\n", 0o100755)
    rc, out = run(cand)
    assert rc == 1
    assert "path-safety" in out


def test_symlink_member_fails(tmp_path):
    """SD is FAT; a symlink cannot survive extraction there."""
    cand = make_candidate(tmp_path)
    zpath = os.path.join(cand, "COPY-TO-SD-CARD-ROOT", "polaris-wifi.zip")
    info = zipfile.ZipInfo("polaris-wifi/evil-link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(zpath, "a") as zf:
        zf.writestr(info, "/etc/passwd")
    rc, out = run(cand)
    assert rc == 1
    assert "no-symlinks" in out


def test_corrupt_zip_fails(tmp_path):
    cand = make_candidate(tmp_path)
    zpath = os.path.join(cand, "COPY-TO-SD-CARD-ROOT", "polaris-wifi.zip")
    with open(zpath, "r+b") as fh:
        fh.seek(30)
        fh.write(b"\x00\x00\x00\x00")
    rc, out = run(cand)
    assert rc == 1


def test_candidate_without_sd_root_is_refused(tmp_path):
    rc, _ = run(str(tmp_path))
    assert rc == 1


def test_verifier_reads_archives_not_staging_dirs():
    """The gate must open the archive.

    scripts/verify-shipped-artifacts.py walks a tree with os.walk() and so
    cannot see an archive that differs from its staging directory -- which is
    precisely how #286 shipped.  Asserting this here keeps a future rewrite from
    quietly reverting to the weaker check.

    Decided on the AST, not a text search: this module's own docstring names
    os.walk while explaining what must not be done, so a substring test matches
    prose and reports a false violation.
    """
    import ast

    tree = ast.parse(open(VERIFIER, encoding="utf-8").read())
    walked = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "walk"
    ]
    assert not walked, f"staging-directory walk at line(s) {walked} is the bug class #292 fixes"

    opened = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert {"is_zipfile", "testzip"} <= opened, "must open and CRC-check the archives"


def test_build_astro_chmods_astro_kit():
    """Both producers call build-astro.sh; neither used to chmod the astro kit.

    A fix on one build path is not a fix -- that is what let .99 ship.  The
    wifi kit already had its chmod; the astro kit did not, so seven scripts
    shipped 644 and four boot features gated on `[ -x ]` silently never ran.
    """
    src = open(os.path.join(ROOT, "build-astro.sh"), encoding="utf-8").read()
    assert 'chmod 755 "$SD_ASTRO"/*.sh' in src
    # And it must be paired with an assertion, not just a best-effort chmod.
    assert "not executable -- boot's [ -x ] test would skip it" in src


def test_both_producers_invoke_the_gate():
    """A gate nobody calls is not a gate.

    This turns #292's own bug class back on the fix.  The licence check in
    scripts/build-astro-bundle.sh was an ancestor of the patcher commit recorded
    in .99's provenance and never ran, because the release was built by
    scripts/build-astro-candidate.sh, which does not call the wrapper.  Shipping a
    verifier that only works when someone remembers to run it reproduces that
    failure with extra steps.

    Checked on both producers, so dropping the call from either one fails here.
    """
    for name in (os.path.join("scripts", "build-astro-candidate.sh"),
                 os.path.join("scripts", "build-astro-bundle.sh")):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "verify-published-astro-candidate.py" in src, (
            f"{name} produces kit archives but never runs the artifact gate"
        )
        # It must be able to abort the build.  A bare call whose status is
        # discarded prints FAIL and then ships the bytes anyway.
        tail = src[src.index("verify-published-astro-candidate.py"):][:400]
        assert "die" in tail, f"{name} runs the gate but ignores its exit status"


def test_gate_runs_after_the_archives_exist():
    """Calling the verifier before the archives exist would pass vacuously.

    The verifier reports NOT_APPLICABLE for an absent archive rather than failing,
    so a call placed too early prints a green verdict over nothing at all -- which
    is the same shape of bug as a [ -f ] guard that silently skips.
    """
    src = open(os.path.join(ROOT, "scripts", "build-astro-candidate.sh"),
               encoding="utf-8").read()
    call = src.index('python3 "$ROOT/scripts/verify-published-astro-candidate.py"')
    assert src.index("zip -qrX polaris-wifi.zip") < call, (
        "gate runs before polaris-wifi.zip is created"
    )
    assert src.index('tar -C "$OUT/astro-bundle"') < call, (
        "gate runs before astro-bundle.tar.gz is created"
    )


def test_the_wired_block_actually_aborts(tmp_path):
    """The wiring must stop a build, not just print a warning.

    Text assertions can be satisfied by a call whose exit status is thrown away,
    which prints FAIL and ships the bytes anyway.  So extract the block from the
    real script -- not a hand-written copy -- run it against a candidate tree
    whose wifi archive is missing its licence, and require a non-zero status.
    """
    src = open(os.path.join(ROOT, "scripts", "build-astro-candidate.sh"),
               encoding="utf-8").read()
    start = src.index("if command -v python3 >/dev/null 2>&1; then\n"
                      '  python3 "$ROOT/scripts/verify-published-astro-candidate.py"')
    end = src.index("\nfi\n", start) + len("\nfi\n")
    block = src[start:end]
    assert "die" in block, "extracted block cannot abort"

    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(VERIFIER, root / "scripts" / "verify-published-astro-candidate.py")

    out = tmp_path / "out"
    sd = out / "COPY-TO-SD-CARD-ROOT" / "polaris-wifi"
    sd.mkdir(parents=True)
    (sd / "wpa_supplicant").write_text("#!/bin/sh\n")
    (sd / "wpa_supplicant").chmod(0o755)
    with zipfile.ZipFile(out / "COPY-TO-SD-CARD-ROOT" / "polaris-wifi.zip", "w") as zf:
        zf.writestr("polaris-wifi/wpa_supplicant", "#!/bin/sh\n")
    (out / "astro-bundle.tar.gz").write_bytes(b"\x1f\x8b stub")

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/bin/sh\n"
        f'ROOT="{root}"\nOUT="{out}"\n'
        'die() { echo "ABORTED: $*" >&2; exit 1; }\n'
        + block + "\nexit 0\n"
    )
    harness.chmod(0o755)

    proc = subprocess.run(["/bin/sh", str(harness)], capture_output=True, text=True)
    assert proc.returncode != 0, (
        "the gate ran against a licence-less archive and the build continued anyway"
    )
    assert "ABORTED" in proc.stderr


def test_every_shipped_shell_script_is_executable_in_git():
    """A shebang without an exec bit ships a script that cannot run.

    6.0.0.54.102 published polaris-astro.zip with eight .sh files at mode 0644.
    polaris-goto-solve.sh is guarded by `[ ! -x ] && exit 2`, so the goto solver
    aborts on the device; frame-watch, goto-watch and pointing-model are guarded by
    `[ -x ]` and silently disable instead.  The archive-level gate catches this after
    a build, which is ~15 minutes too late and only fires if someone builds.  This
    assertion runs in milliseconds against the index, so the mode cannot be committed
    wrong in the first place.

    Checked against git's recorded mode rather than the working tree, because the
    working tree can be chmod'd locally while the commit still ships 100644.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-s", "--", "container/astro/ondisk"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    offenders = []
    for line in listing:
        mode, _, rest = line.partition(" ")
        path = rest.rpartition("\t")[2]
        if not path.endswith(".sh"):
            continue
        first = open(os.path.join(ROOT, path), "rb").readline()
        if not first.startswith(b"#!"):
            continue          # sourced-only file, not meant to be executed
        if mode != "100755":
            offenders.append(f"{path} is {mode}")
    assert not offenders, (
        "shipped scripts with a shebang but no exec bit: " + ", ".join(offenders)
    )

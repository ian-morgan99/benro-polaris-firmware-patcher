#!/usr/bin/env python3
"""Assert the shipped stage-2 artifact set is loadable on the device (#214 D1, D2).

Two failure modes this replaces:

D1 -- the release gate runs upstream's tests against a *meson* build configured
`-Dcamlibs=ptp2,pentax,directory`, while the shipped libraries come from an *autotools*
build configured `--without-libxml-2.0 --without-jpeg --without-libcurl`. Same commit,
different dependency graph, so the 21 upstream tests never exercise what actually ships.
Rather than trying to make the two configurations agree, assert the artifact directly:
every DT_NEEDED of every shipped .so must be resolvable either inside the shipped tree
or from the device's own runtime.

D2 -- the libgphoto2 version is pinned in four places. `container/build_ptp2.sh` reads it
from configure.ac and fails on mismatch, but the loader's compiled-in module directories
and the manifest's mandatory paths are separate literals. A bump that leaves one behind
produces a build that passes the gate and then dlopens a directory that does not exist --
caught only on hardware.

Both checks run against a built tree, so they need no device and no container runtime.

Usage:
    verify-shipped-artifacts.py STAGE2_DIR [--source SRC_DIR] [--allowlist FILE]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

# Shared objects the device's own /app/lib provides. Derived from a captured stage-2
# loader trace on real hardware (docs/evidence/o-v16b-full-test-20261008/raw/
# stage2-crash.log), which lists what the dynamic linker actually resolved. Anything not
# shipped and not listed here is treated as unsatisfiable -- fail closed, because a
# missing library at dlopen time is exactly the hardware-only failure this gate exists to
# prevent.
DEVICE_RUNTIME_ALLOWLIST = {
    "libc.so.0", "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0",
    "librt.so.1", "libgcc_s.so.1", "libltdl.so.7", "libexif.so.12",
    "libusb-1.0.so.0", "libudev.so.1", "libz.so.1", "liblzma.so.5",
    "libgomp.so.1", "libsecurec.so", "libuproc.so", "libtimers.so",
    # The ARM dynamic linker; present on the device as ld-linux.so.3.
    "ld-linux.so.3", "ld-linux-armhf.so.3",
}

NEEDED_RE = re.compile(r"Shared library: \[([^\]]+)\]")


def readelf_needed(path: str, tool: str) -> list[str]:
    out = subprocess.run([tool, "-d", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{tool} -d {path} failed: {out.stderr.strip()}")
    return NEEDED_RE.findall(out.stdout)


def shipped_lib_names(stage2_dir: str) -> dict[str, str]:
    """Map soname-ish basename -> path for everything we ship."""
    found: dict[str, str] = {}
    for root, _dirs, files in os.walk(stage2_dir):
        for name in files:
            if ".so" in name:
                found.setdefault(name, os.path.join(root, name))
    return found


def parse_device_lib_listing(text: str) -> set[str]:
    """Extract sonames from an `ls -1 /app/lib` capture.

    Accepts plain filenames or full paths, one per line, and ignores anything that is not
    a shared object.

    IMPORTANT: the listing must include *symlink* names, because DT_NEEDED records a
    soname (`libc.so.6`) while the file on disk may be named `libc-2.24.so`. Use
    `ls -1 /app/lib`, which lists both; do not derive this from a loader trace or a
    `find -name 'lib*.so*'` that follows only real files, or every glibc dependency will
    be reported unsatisfiable. `check_dependencies` warns when that appears to have
    happened rather than emitting a wall of false failures.
    """
    names: set[str] = set()
    for line in text.splitlines():
        token = line.strip().split()[-1] if line.strip() else ""
        base = os.path.basename(token)
        if ".so" in base:
            names.add(base)
    return names


def check_dependencies(stage2_dir: str, tool: str,
                       allowlist: set[str],
                       allowlist_is_authoritative: bool = False) -> list[str]:
    shipped = shipped_lib_names(stage2_dir)
    problems: list[str] = []
    unresolved: list[tuple[str, str]] = []
    for name, path in sorted(shipped.items()):
        try:
            needed = readelf_needed(path, tool)
        except RuntimeError as exc:
            problems.append(str(exc))
            continue
        for dep in needed:
            if dep in shipped or dep in allowlist:
                continue
            unresolved.append((name, dep))

    # A listing that resolves none of the core C library sonames is almost certainly a
    # capture of real filenames without their symlinks (libc-2.24.so vs libc.so.6).
    # Reporting every glibc dependency as unsatisfiable would bury any genuine finding,
    # so say what is wrong with the input instead.
    core = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2"}
    missing_core = {dep for _name, dep in unresolved if dep in core}
    if allowlist_is_authoritative and len(missing_core) >= 2:
        print(f"WARNING: the --device-libs listing resolves none of the core C library "
              f"sonames ({sorted(missing_core)}). It probably lists real file names "
              f"(e.g. libc-2.24.so) without their symlinks (libc.so.6). Re-capture with "
              f"`ls -1 /app/lib`. Skipping these as an input problem, not a build one.")
        unresolved = [(n, d) for n, d in unresolved if d not in missing_core]

    for name, dep in unresolved:
        problems.append(
            f"{name}: DT_NEEDED {dep!r} is neither shipped nor provided by the "
            f"device runtime allowlist")
    return problems


def source_versions(src_dir: str) -> tuple[str, str]:
    """Return (libgphoto2 version, libgphoto2_port version) from configure.ac."""
    def read(path: str) -> str | None:
        if not os.path.exists(path):
            return None
        text = open(path, encoding="utf-8", errors="replace").read()
        match = re.search(r"AC_INIT\s*\(\s*\[?[^,\]]*\]?\s*,\s*\[?([0-9][0-9.]*)\]?",
                          text)
        return match.group(1) if match else None

    gp = read(os.path.join(src_dir, "configure.ac"))
    port = read(os.path.join(src_dir, "libgphoto2_port", "configure.ac"))
    return gp or "", port or ""


def check_version_pins(stage2_dir: str, repo_root: str, src_dir: str | None) -> list[str]:
    """The loader's compiled-in dirs and the manifest paths must match the built tree."""
    problems: list[str] = []

    # What the built tree actually contains -- derived from disk, not from a literal.
    camlibs_dirs = [d for d in os.listdir(os.path.join(stage2_dir, "libgphoto2"))
                    if os.path.isdir(os.path.join(stage2_dir, "libgphoto2", d))] \
        if os.path.isdir(os.path.join(stage2_dir, "libgphoto2")) else []
    iolibs_dirs = [d for d in os.listdir(os.path.join(stage2_dir, "libgphoto2_port"))
                   if os.path.isdir(os.path.join(stage2_dir, "libgphoto2_port", d))] \
        if os.path.isdir(os.path.join(stage2_dir, "libgphoto2_port")) else []

    if not camlibs_dirs:
        problems.append("no libgphoto2/<version> directory in the shipped tree")
    if not iolibs_dirs:
        problems.append("no libgphoto2_port/<version> directory in the shipped tree")

    loader = os.path.join(repo_root, "container", "stage2_loader.c")
    if os.path.exists(loader):
        text = open(loader, encoding="utf-8", errors="replace").read()
        for macro, built in (("STAGE2_CAMLIBS_DIR", camlibs_dirs),
                             ("STAGE2_IOLIBS_DIR", iolibs_dirs)):
            match = re.search(rf'#define\s+{macro}\s+"([^"]+)"', text)
            if not match:
                problems.append(f"{macro} not found in stage2_loader.c")
                continue
            compiled_in = match.group(1).rstrip("/").split("/")[-1]
            if built and compiled_in not in built:
                problems.append(
                    f"{macro} is compiled in as {compiled_in!r} but the shipped tree "
                    f"contains {built}. The device would dlopen a directory that does "
                    f"not exist.")

    manifest = os.path.join(repo_root, "scripts", "generate-fwpkt-manifest.py")
    if os.path.exists(manifest):
        text = open(manifest, encoding="utf-8", errors="replace").read()
        # Each mandatory path looks like lib/stage2/libgphoto2/<v>/x.so or
        # lib/stage2/libgphoto2_port/<v>/x.so. Check each against the tree it names
        # rather than guessing from surrounding text.
        for kind, pinned in re.findall(
                r'"lib/stage2/(libgphoto2(?:_port)?)/([^/"]+)/', text):
            built = iolibs_dirs if kind == "libgphoto2_port" else camlibs_dirs
            if pinned not in built:
                problems.append(
                    f"generate-fwpkt-manifest.py pins {kind}/{pinned}, which is not "
                    f"present in the shipped tree ({built})")

    if src_dir:
        gp, port = source_versions(src_dir)
        for version, label, built in ((gp, "libgphoto2", camlibs_dirs),
                                      (port, "libgphoto2_port", iolibs_dirs)):
            if version and built and version not in built:
                problems.append(
                    f"source {label} configure.ac says {version!r} but the shipped tree "
                    f"has {built}")
    return problems


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage2_dir")
    parser.add_argument("--source", help="libgphoto2 source tree (enables D2 source check)")
    parser.add_argument("--repo-root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--allowlist", help="extra sonames the device provides, one per "
                                            "line; added to the built-in list")
    parser.add_argument("--device-libs", help="authoritative `ls /app/lib` capture from "
                                              "the target device. REPLACES the built-in "
                                              "allowlist: only what this file lists, plus "
                                              "what is shipped, counts as resolvable.")
    args = parser.parse_args(argv[1:])

    tool = shutil.which("readelf") or shutil.which("llvm-readelf")
    if not tool:
        print("ERROR: readelf is required", file=sys.stderr)
        return 2

    allowlist_is_authoritative = False
    if args.device_libs:
        if not os.path.exists(args.device_libs):
            print(f"ERROR: --device-libs file {args.device_libs} not found", file=sys.stderr)
            return 2
        allowlist = parse_device_lib_listing(
            open(args.device_libs, encoding="utf-8", errors="replace").read())
        allowlist_is_authoritative = True
        print(f"device runtime allowlist: {len(allowlist)} sonames "
              f"(authoritative, from {args.device_libs})")
    else:
        allowlist = set(DEVICE_RUNTIME_ALLOWLIST)
        print(f"device runtime allowlist: {len(allowlist)} sonames (built-in, derived "
              f"from a captured loader trace of successful resolutions -- pass "
              f"--device-libs with `ls -1 /app/lib` for an authoritative reading)")
    if args.allowlist and os.path.exists(args.allowlist):
        allowlist |= {line.strip() for line in open(args.allowlist)
                      if line.strip() and not line.startswith("#")}

    if not os.path.isdir(args.stage2_dir):
        print(f"ERROR: {args.stage2_dir} is not a directory", file=sys.stderr)
        return 2

    shipped = shipped_lib_names(args.stage2_dir)
    print(f"shipped shared objects: {len(shipped)}")
    problems = check_dependencies(args.stage2_dir, tool, allowlist,
                                  allowlist_is_authoritative)
    problems += check_version_pins(args.stage2_dir, args.repo_root, args.source)

    if problems:
        print(f"\nFAIL ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("PASS: every DT_NEEDED is satisfiable and all version pins agree with the "
          "shipped tree")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

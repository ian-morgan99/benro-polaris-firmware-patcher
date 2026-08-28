#!/usr/bin/env python3
"""Structural validator for finished Benro Polaris FwPkt packages.

This is the finished-package structural validator called for in
ian-morgan99/benro-polaris-firmware-patcher issue #21. It exists
because the on-board updater (polestar_app -> getFwInfo.sh -> crcInfo)
only re-MD5s and re-sizes the entries the package's firmwareInfo
claims exist. A package that is structurally wrong (extra top-level
directory, missing required path, duplicate member, dropped gimbal
binary, silently re-pointed stock component) is indistinguishable
from a corrupt upload to the device: the device just reboots and the
firmware disappears.

This script is run after the final ZIP is assembled. It walks the
package, enforces the layout, and cross-checks the components that
are supposed to be unchanged-from-stock against recorded SHA-256
values. The components that intentionally change (currently appfs,
plus any added/removed lines in firmwareInfo) are deliberately NOT
cross-checked: they are expected to drift, and their drift is
detected by the separate verify_firmwareinfo.py (MD5/size
self-consistency).

Acceptance per issue #21:
  - reject unexpected top-level layout
  - reject duplicate members
  - check required paths
  - cross-check stock components against recorded stock SHA-256
  - output a concise package manifest
  - run after final ZIP creation
  - future builds fail closed on wrong nesting, duplicate members,
    missing required files, or unintended stock-component drift

Usage:
    validate_fw_package.py [--stock-sha256s PATH] <FwPkt_or_zip>

Exit 0 on success, 1 on any structural failure, 2 on usage error.

Stdlib only.
"""
import argparse
import hashlib
import os
import sys
import zipfile

CHUNK = 1 << 20

# Stock components that must be byte-identical between a clean Pentax
# build and a stock Polaris. These are the files Pentax's libgphoto2
# fork does not touch. If they drift we have either copied a
# different stock input, or a re-pack (e.g. HDMI geometry tweak) has
# accidentally written through to one of them.
#
# Recomputed on 2026-08-28 from firmware/FwPkt.zip (the canonical
# stock package).
DEFAULT_STOCK_SHA256S = {
    "camera/config":                   "ef68d937a2d646daa4847950d7e2ca15c6c732807e131652e6b10bc60cc36155",
    "camera/uImage":                   "d1b54246dc9c01202ba05192860f45c618200e2e6a4a647e07f52e5162770580",
    "camera/rootfs.ubifs":             "26d4787fcddc49f577c60a21988d0cff49e245dd02ed35a21a1dfa1b5e9a3d37",
    "gimbal/polaris403_2.0.0.22.bin":  "35f8d0646339715e5e5e5d6ec01743f411d16325bc0b36fd58b590584fedf0b9",
    "gimbal/polaris413_2.0.0.22.bin":  "34d3f4186185c541adb9c8e57b3e2ec13e402dfb4bb3e9b2262cbf03f1a5c112",
}


def sha256_bytes(data):
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def list_members_from_dir(root):
    """Mirror the `zip` layout for a dir-mode input."""
    members = []
    members.append(("FwPkt/", None, 0, True))
    members.append(("FwPkt/camera/", None, 0, True))
    members.append(("FwPkt/gimbal/", None, 0, True))
    for sub in ("camera", "gimbal"):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if not os.path.isfile(full):
                continue
            members.append(("FwPkt/%s/%s" % (sub, name), full, os.path.getsize(full), False))
    fi = os.path.join(root, "firmwareInfo")
    if os.path.isfile(fi):
        members.append(("FwPkt/firmwareInfo", fi, os.path.getsize(fi), False))
    return members


def list_members_from_zip(zip_path):
    members = []
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            members.append((info.filename, None, info.file_size, info.is_dir()))
    return members


def read_member_bytes(zip_path, member_path):
    with zipfile.ZipFile(zip_path, "r") as z:
        try:
            return z.read(member_path)
        except KeyError:
            return None


def read_member_fs(root, member_path):
    rel = member_path[len("FwPkt/"):] if member_path.startswith("FwPkt/") else member_path
    full = os.path.join(root, rel)
    with open(full, "rb") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("package", help="Path to a finished FwPkt.zip or a FwPkt directory")
    ap.add_argument("--stock-sha256s",
                    help="Path to a stock SHA-256 manifest (one 'relpath hash' per line). "
                         "If omitted, uses the in-script defaults for firmware/FwPkt.zip.")
    args = ap.parse_args()

    pkg = args.package
    if not os.path.exists(pkg):
        sys.stderr.write("error: package not found: %s\n" % pkg)
        return 2

    if os.path.isdir(pkg):
        members = list_members_from_dir(pkg)
        def reader(mp):
            return read_member_fs(pkg, mp)
    else:
        members = list_members_from_zip(pkg)
        def reader(mp):
            return read_member_bytes(pkg, mp)

    # Load stock SHA-256 expectations
    if args.stock_sha256s:
        stock_sha = {}
        with open(args.stock_sha256s) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                rel, h = line.split(None, 1)
                stock_sha[rel] = h.strip().lower()
    else:
        stock_sha = dict(DEFAULT_STOCK_SHA256S)

    errors = []
    seen = set()

    # 1. Top-level layout: exactly one top-level entry, 'FwPkt/'.
    top_levels = set()
    for path, _, _, is_dir in members:
        head = path.rstrip("/").split("/", 1)[0]
        top_levels.add(head)
    if top_levels != {"FwPkt"}:
        errors.append("top-level layout must contain exactly one entry, 'FwPkt/'; "
                      "found: %s" % sorted(top_levels))

    # 2. Duplicate members
    for path, _, _, _ in members:
        if path in seen:
            errors.append("duplicate member: %s" % path)
        seen.add(path)

    # 3. Required paths
    file_paths = {p.rstrip("/") for p, _, _, is_dir in members if not is_dir}
    for required in ["FwPkt/firmwareInfo",
                     "FwPkt/camera/config",
                     "FwPkt/camera/uImage",
                     "FwPkt/camera/rootfs.ubifs",
                     "FwPkt/camera/appfs.ubifs"]:
        if required not in file_paths:
            errors.append("missing required file: %s" % required)
    gimbal_files = [p for p in file_paths
                    if p.startswith("FwPkt/gimbal/") and p.endswith(".bin")]
    if not gimbal_files:
        errors.append("missing required files: FwPkt/gimbal/*.bin (no polaris*/oms bins)")
    else:
        for gf in gimbal_files:
            base = os.path.basename(gf)
            if not (base.startswith("polaris") or base.startswith("oms")):
                errors.append("unexpected gimbal file (must be polaris*_*.bin or oms_*): %s" % gf)

    # 4. Cross-check stock-component SHA-256
    for rel, expected in stock_sha.items():
        mp = "FwPkt/" + rel
        if mp not in file_paths:
            errors.append("stock cross-check: missing expected file %s" % mp)
            continue
        data = reader(mp)
        if data is None:
            errors.append("stock cross-check: cannot read %s" % mp)
            continue
        actual = sha256_bytes(data)
        if actual.lower() != expected.lower():
            errors.append("stock cross-check FAILED for %s:\n"
                          "    expected: %s\n"
                          "    actual:   %s\n"
                          "    This file is supposed to be byte-identical to stock. "
                          "Either the stock input was different, or a repack "
                          "accidentally wrote through to it." % (mp, expected, actual))

    # 5. Concise manifest
    print("=== FwPkt manifest ===")
    for path, _, size, is_dir in members:
        clean = path.rstrip("/")
        if is_dir:
            print("  %s/" % clean)
        else:
            print("  %-44s %10d B" % (clean, size))
    print()
    if gimbal_files:
        print("gimbal binaries: %d" % len(gimbal_files))
    print("stock components cross-checked: %d" % len(stock_sha))
    print("layout: %s" % ("OK" if top_levels == {"FwPkt"} else "BAD"))
    print("duplicates: %s" % ("none" if len(seen) == len(members) else "PRESENT"))

    if errors:
        print()
        print("FAIL: %d structural error(s)" % len(errors))
        for e in errors:
            print("  - %s" % e)
        print()
        print("The on-board updater would silently reject this FwPkt.")
        print("Do NOT put it on an SD card. Rebuild and re-run this validator.")
        return 1

    print("OK: FwPkt package is structurally sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

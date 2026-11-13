#!/usr/bin/env python3
"""Verify the ARCHIVES a user receives, not the directory a build left behind.

Issue #292.  Every silent-failure release bug in this project's history (#58,
#280, #281, #286) shipped for the same reason: a check ran against a staging
directory, passed, and the archive that was actually published did not contain
what the directory did.  scripts/verify-shipped-artifacts.py walks a tree with
os.walk() and never opens an archive, so it cannot see this class at all.

This script reopens the finished .zip/.tar.gz members themselves and checks:

  1. integrity      -- CRC, truncation, no traversal/absolute/symlink entries,
                       no duplicate conflicting members, one consistent root.
  2. mandatory      -- copyleft text accompanies copyleft binaries; the DHCP
                       hook ships; licences are non-empty (an empty COPYING is
                       not a licence).
  3. consumer drift -- every sibling file a SHIPPED script references actually
                       exists in a shipped kit, resolved by on-device path so a
                       reference crossing from polaris-astro to polaris-wifi is
                       checked too.  This is derived from the consumers rather
                       than hardcoded, so it catches the next omission of this
                       class, not just the last one.
  4. modes          -- scripts and ELF binaries carry an executable bit inside
                       the archive.

A PASS means ARTIFACTS_INTERNALLY_CONSISTENT.  It is explicitly NOT
HARDWARE_QUALIFIED: nothing here proves /app/network_telnetd.sh exists after a
flash, that polaris-httpd binds 8090, or that an installed binary matches SD
content.  Those need the device matrix (#265).

Usage:
    verify-published-astro-candidate.py <candidate-dir> [--json out.json]
Exit 0 = ARTIFACTS_INTERNALLY_CONSISTENT, 1 = at least one mandatory FAIL,
2 = usage/IO error.
"""

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import time
import zipfile

CONTRACT_VERSION = "astro-release-contract-v1"

# SD kits unpacked at the card root, and where they land on the device.
SD_KITS = {
    "polaris-wifi": "/app/sd/polaris-wifi",
    "polaris-astro": "/app/sd/polaris-astro",
}

# Copyleft text that must sit *inside* the kit archive, beside the binaries.
# Names come from the gate in scripts/build-astro-bundle.sh, not invented here:
# a fix that satisfies LGPL but renames what the gate checks will be "corrected"
# by someone renaming the wrong one.
REQUIRED_MEMBERS = {
    "polaris-wifi": [
        "LICENCE-wifi.txt",
        "COPYING-LGPL-2.1.txt",
        "NOTICE-iw.txt",
        "NOTICE-wpa_supplicant.txt",
        # #280: polaris-autojoin.sh and polaris-apsta.sh both pass this to
        # `udhcpc -s` and BusyBox configures nothing without it.  It existed in
        # the tree the whole time; it was never packaged.
        "udhcpc.script",
    ],
    "polaris-astro": [
        "COPYING-GPL-2.txt",
        "SOURCE-OFFER.txt",
    ],
}

# Files a kit creates at runtime.  A script referencing one is not declaring a
# dependency on a shipped file, so the drift check must not demand it.
RUNTIME_GENERATED = re.compile(
    r"\.(log|conf|pid|tmp|lock|csv|json|dng|jpg|jpeg|png|ptp|err|out|bak|swp)$"
)

# `$WDIR/foo`, `${WDIR}/foo`, "$SD_ROOT/polaris-wifi/foo" -- a sibling reference.
SIBLING_REF = re.compile(
    r"\$\{?(?P<var>WDIR|SD_ROOT|KIT_DIR|HERE|DIR|SELF_DIR)\}?/(?P<name>[A-Za-z0-9_.\-]+)"
)

ELF_MAGIC = b"\x7fELF"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Report:
    def __init__(self) -> None:
        self.checks = []

    def add(self, component: str, check: str, verdict: str, reason: str) -> None:
        self.checks.append(
            {"component": component, "check": check, "verdict": verdict, "reason": reason}
        )

    def mandatory_failures(self):
        return [c for c in self.checks if c["verdict"] == "FAIL"]

    def unknowns(self):
        return [c for c in self.checks if c["verdict"] == "UNKNOWN"]


def find_sd_root(candidate: str):
    """Both producer routes lay the tree out differently; accept either.

    build-astro-bundle.sh writes <candidate>/COPY-TO-SD-CARD-ROOT, while
    build-astro-candidate.sh writes <candidate>/astro-bundle/COPY-TO-SD-CARD-ROOT.
    A gate that only understood one of them would be a gate on one build path --
    which is the defect this script exists to catch.
    """
    for rel in ("COPY-TO-SD-CARD-ROOT", os.path.join("astro-bundle", "COPY-TO-SD-CARD-ROOT")):
        cand = os.path.join(candidate, rel)
        if os.path.isdir(cand):
            return cand
    return None


def open_zip(path: str, component: str, rep: Report):
    """Return {name: bytes} for a zip, or None after recording why not."""
    if not zipfile.is_zipfile(path):
        rep.add(component, "archive-readable", "FAIL", f"{os.path.basename(path)} is not a valid zip")
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                rep.add(component, "crc", "FAIL", f"CRC mismatch on member {bad!r}")
                return None
            members = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                data = zf.read(info)
                if len(data) != info.file_size:
                    rep.add(
                        component, "truncation", "FAIL",
                        f"{info.filename}: header says {info.file_size} bytes, read {len(data)}",
                    )
                    return None
                members[info.filename] = data
            modes = {i.filename: i.external_attr >> 16 for i in zf.infolist()}
        rep.add(component, "archive-readable", "PASS", f"{os.path.basename(path)}: CRC ok, {len(members)} members")
        return members, modes
    except (zipfile.BadZipFile, OSError) as exc:
        rep.add(component, "archive-readable", "FAIL", f"cannot read {path}: {exc}")
        return None


def check_entry_names(component: str, names, rep: Report) -> None:
    roots = set()
    seen = {}
    for n in names:
        if n.startswith("/") or ".." in n.split("/"):
            rep.add(component, "path-safety", "FAIL", f"{n!r} is absolute or traverses out of the root")
        if "\\" in n:
            rep.add(component, "path-safety", "FAIL", f"{n!r} contains a backslash")
        roots.add(n.split("/")[0])
        base = os.path.basename(n.rstrip("/"))
        if not base:
            continue
        # Two members with the same basename in different directories would
        # collide when unpacked flat, and a duplicate exact name silently keeps
        # whichever the extractor writes last.
        key = n
        if key in seen:
            rep.add(component, "duplicate-entry", "FAIL", f"{n!r} appears more than once")
        seen[key] = True
    if len(roots) != 1:
        rep.add(component, "single-root", "FAIL", f"archive has {len(roots)} top-level roots: {sorted(roots)}")
    else:
        rep.add(component, "single-root", "PASS", f"single root {sorted(roots)[0]!r}")


def check_symlinks(component: str, path: str, rep: Report) -> None:
    """Zip stores symlinks as regular members with a symlink mode bit."""
    try:
        with zipfile.ZipFile(path) as zf:
            links = [i.filename for i in zf.infolist() if stat.S_ISLNK(i.external_attr >> 16)]
    except (zipfile.BadZipFile, OSError):
        return
    if links:
        rep.add(component, "no-symlinks", "FAIL", f"symlink members {links} -- SD is FAT, they cannot survive")
    else:
        rep.add(component, "no-symlinks", "PASS", "no symlink members")


def basenames(members) -> dict:
    out = {}
    for name, data in members.items():
        base = os.path.basename(name.rstrip("/"))
        if base:
            out[base] = data
    return out


def check_required(component: str, members, rep: Report) -> None:
    want = REQUIRED_MEMBERS.get(component, [])
    have = basenames(members)
    for req in want:
        data = have.get(req)
        if data is None:
            rep.add(
                component, "mandatory-member", "FAIL",
                f"{req} is not a member of the archive a user unpacks",
            )
        elif not data.strip():
            # An empty licence file satisfies `[ -f ]` and satisfies nothing else.
            rep.add(component, "mandatory-member", "FAIL", f"{req} is present but empty")
        else:
            rep.add(component, "mandatory-member", "PASS", f"{req} present ({len(data)} bytes)")


def check_versions_named(component: str, members, rep: Report) -> None:
    """An offer that names no version is not an offer.

    'libnl-, iw-' reads like a source offer and provides none: there is no
    version to fetch.  Derive the versions from the tarballs actually staged in
    licenses/ and require each one to appear in the offer text.
    """
    if component != "polaris-wifi":
        return
    have = basenames(members)
    offer = have.get("LICENCE-wifi.txt")
    if not offer:
        rep.add(component, "offer-names-versions", "UNKNOWN", "no LICENCE-wifi.txt to inspect")
        return
    text = offer.decode("utf-8", "replace")
    # libnl-3.7.0.tar.gz -> 3.7.0 ; iw-5.19.tar.gz -> 5.19
    staged = []
    for path in find_license_tarballs():
        base = os.path.basename(path)
        m = re.match(r"^(libnl|iw|wpa_supplicant)-([0-9][0-9a-zA-Z.\-]*)\.tar\.(gz|xz)$", base)
        if m:
            staged.append((m.group(1), m.group(2)))
    if not staged:
        rep.add(component, "offer-names-versions", "UNKNOWN", "no upstream tarballs found to derive versions from")
        return
    missing = [f"{p}-{v}" for p, v in sorted(set(staged)) if v not in text]
    if missing:
        rep.add(
            component, "offer-names-versions", "FAIL",
            f"LICENCE-wifi.txt does not name the version of: {', '.join(missing)} -- "
            "an offer that names no version is not an offer",
        )
    else:
        rep.add(component, "offer-names-versions", "PASS", "names every staged upstream version")


LICENSE_DIR_CANDIDATES = ("licenses", os.path.join("astro-bundle", "licenses"))


def find_license_tarballs() -> list:
    """Best-effort: the source tarballs staged next to the bundle, if present."""
    out = []
    for rel in LICENSE_DIR_CANDIDATES:
        d = os.path.join(_candidate_root, rel)
        if os.path.isdir(d):
            out.extend(os.path.join(d, f) for f in os.listdir(d))
    return out


def check_executable_modes(component: str, members, modes, rep: Report) -> None:
    bad = []
    for name, data in members.items():
        base = os.path.basename(name.rstrip("/"))
        if not base:
            continue
        needs = base.endswith(".sh") or base.endswith(".script") or data[:4] == ELF_MAGIC
        if not needs:
            continue
        mode = modes.get(name, 0)
        if not (mode & stat.S_IXUSR):
            bad.append(f"{base} (mode {oct(mode)})")
    if bad:
        rep.add(
            component, "executable-mode", "FAIL",
            f"not executable inside the archive: {', '.join(sorted(bad))}",
        )
    else:
        rep.add(component, "executable-mode", "PASS", "all scripts and ELF binaries carry an exec bit")


def device_index(kits: dict) -> dict:
    """Map every shipped file to its on-device path, across all SD kits."""
    idx = {}
    for kit, members in kits.items():
        dest = SD_KITS.get(kit)
        if not dest:
            continue
        for name in members:
            base = os.path.basename(name.rstrip("/"))
            if base:
                idx[f"{dest}/{base}"] = (kit, base)
    return idx


def check_consumer_drift(component: str, members, kits: dict, rep: Report) -> None:
    """Every sibling a shipped script references must exist in some shipped kit.

    Derived from the consumers themselves, not from a list of known-bad names,
    so the next script that gains a dependency cannot ship without it.  A
    reference from polaris-astro's copy of polaris-apsta.sh to
    /app/sd/polaris-wifi/udhcpc.script is resolved across kits, because that is
    how the kit actually runs.
    """
    idx = device_index(kits)
    dest = SD_KITS.get(component)
    if not dest:
        return
    missing = []
    checked = 0
    for name, data in members.items():
        base = os.path.basename(name.rstrip("/"))
        if not (base.endswith(".sh") or base.endswith(".script")):
            continue
        try:
            text = data.decode("utf-8", "replace")
        except UnicodeDecodeError:
            continue
        for m in SIBLING_REF.finditer(text):
            target = m.group("name")
            if RUNTIME_GENERATED.search(target):
                continue
            # Only executable-shaped siblings are load-bearing dependencies.
            # $DIR/camera-death-state and $DIR/camera-death-$TS.log are runtime
            # state the script creates, not files it expects to be shipped;
            # demanding them would make the gate cry instead of catch.
            if not (target.endswith(".sh") or target.endswith(".script")):
                continue
            if target.endswith("-"):  # truncated interpolation fragment
                continue
            checked += 1
            # WDIR points at this kit for the wifi scripts; for the astro copies
            # of the same scripts it points at /app/sd/polaris-wifi, so try both.
            candidates = [f"{dest}/{target}"]
            if component == "polaris-astro":
                candidates.append(f"/app/sd/polaris-wifi/{target}")
            if not any(c in idx for c in candidates):
                missing.append(f"{base} -> {target}")
    if missing:
        rep.add(
            component, "consumer-drift", "FAIL",
            "shipped scripts reference files that are in no shipped kit: "
            + ", ".join(sorted(set(missing))),
        )
    else:
        rep.add(component, "consumer-drift", "PASS", f"{checked} sibling references resolve")


def check_fw_pkt(candidate: str, rep: Report) -> None:
    """The watcher reads an EXTRACTED tree; an archive alone is ignored (#58)."""
    pkt = os.path.join(candidate, "FwPkt")
    if not os.path.isdir(pkt):
        rep.add("FwPkt", "extracted-tree", "UNKNOWN", "no FwPkt/ directory in this candidate")
        return
    need = ["camera/uImage", "camera/rootfs.ubifs", "camera/appfs.ubifs", "FwVer", "firmwareInfo"]
    absent = [n for n in need if not os.path.isfile(os.path.join(pkt, n))]
    if absent:
        rep.add("FwPkt", "extracted-tree", "FAIL", f"missing {absent} -- the on-boot watcher reads this tree and silently ignores an archive")
    else:
        rep.add("FwPkt", "extracted-tree", "PASS", "camera/{uImage,rootfs.ubifs,appfs.ubifs}, FwVer, firmwareInfo present")


def check_tar(candidate: str, rep: Report) -> None:
    """astro-bundle.tar.gz is the other thing a user may be handed."""
    for rel in ("astro-bundle.tar.gz", os.path.join("astro-bundle", "..", "astro-bundle.tar.gz")):
        path = os.path.join(candidate, rel)
        if not os.path.isfile(path):
            continue
        try:
            with tarfile.open(path, "r:gz") as tf:
                names = tf.getnames()
        except (tarfile.TarError, OSError) as exc:
            rep.add("astro-bundle.tar.gz", "archive-readable", "FAIL", f"cannot read: {exc}")
            return
        bad = [n for n in names if n.startswith("/") or ".." in n.split("/")]
        if bad:
            rep.add("astro-bundle.tar.gz", "path-safety", "FAIL", f"unsafe members: {bad[:5]}")
        else:
            rep.add("astro-bundle.tar.gz", "archive-readable", "PASS", f"{len(names)} members, no traversal")
        # Issue #331: the bundle's top-level licenses/ sits OUTSIDE
        # COPY-TO-SD-CARD-ROOT, so it reaches nobody who follows this bundle's
        # own README and copies only the SD tree.  That used to be reported as
        # UNKNOWN because no route had been chosen.  One has been: build-astro-
        # bundle.sh now copies the licence texts into polaris-astro/licenses/ and
        # writes a written source offer beside the GPL binaries, mirroring what
        # the wifi kit already did.  The check is therefore decidable and this is
        # a real pass/fail from here on -- silence would be the wrong outcome,
        # because a bundle that ships polaris-solve with no licence text is not
        # merely unverified, it is non-compliant.
        lic = [n for n in names if "/licenses/" in n and n.endswith(".txt")]
        outside = [n for n in lic if "COPY-TO-SD-CARD-ROOT" not in n]
        sd_lic = sorted(
            n for n in names
            if "COPY-TO-SD-CARD-ROOT/polaris-astro/licenses/" in n and n.endswith(".txt")
        )
        offer = [n for n in names if n.endswith("COPY-TO-SD-CARD-ROOT/polaris-astro/LICENCE-astro.txt")]
        gpl_bin = [n for n in names if n.endswith("/polaris-astro/polaris-solve")]
        if not gpl_bin:
            rep.add("astro-bundle.tar.gz", "licence-reachability", "NOT_APPLICABLE",
                    "no GPL binaries in this bundle")
        elif sd_lic and offer:
            rep.add(
                "astro-bundle.tar.gz", "licence-reachability", "PASS",
                f"{len(sd_lic)} licence text(s) plus LICENCE-astro.txt ship inside "
                "COPY-TO-SD-CARD-ROOT/polaris-astro, so a user copying the SD tree "
                f"receives them with the GPL binaries ({len(outside)} archive-only "
                "copies remain outside, covered by the written offer)",
            )
        else:
            missing = []
            if not sd_lic:
                missing.append("no licence texts under polaris-astro/licenses/")
            if not offer:
                missing.append("no LICENCE-astro.txt beside the GPL binaries")
            rep.add(
                "astro-bundle.tar.gz", "licence-reachability", "FAIL",
                "GPL binaries reach the user without their licences: " + "; ".join(missing),
            )
        return
    rep.add("astro-bundle.tar.gz", "archive-readable", "NOT_APPLICABLE", "no tarball in this candidate")


def main() -> int:
    global _candidate_root
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    if not os.path.isdir(args.candidate):
        print(f"not a directory: {args.candidate}", file=sys.stderr)
        return 2
    _candidate_root = os.path.abspath(args.candidate)

    rep = Report()
    sd_root = find_sd_root(_candidate_root)
    if sd_root is None:
        print("no COPY-TO-SD-CARD-ROOT found -- nothing a user could unpack here", file=sys.stderr)
        return 1

    kits = {}
    for kit in SD_KITS:
        zpath = os.path.join(sd_root, f"{kit}.zip")
        if not os.path.isfile(zpath):
            rep.add(kit, "archive-present", "NOT_APPLICABLE", f"{kit}.zip not built in this candidate")
            continue
        opened = open_zip(zpath, kit, rep)
        if opened is None:
            continue
        members, modes = opened
        kits[kit] = members
        check_entry_names(kit, members.keys(), rep)
        check_symlinks(kit, zpath, rep)
        check_required(kit, members, rep)
        check_versions_named(kit, members, rep)
        check_executable_modes(kit, members, modes, rep)

    # Drift needs every kit loaded first: references cross package boundaries.
    for kit in kits:
        check_consumer_drift(kit, kits[kit], kits, rep)

    check_fw_pkt(_candidate_root, rep)
    check_tar(_candidate_root, rep)

    fails = rep.mandatory_failures()
    unknowns = rep.unknowns()
    verdict = "ARTIFACTS_INTERNALLY_CONSISTENT" if not fails else "FAIL"
    if not fails and unknowns:
        verdict = "ARTIFACTS_INTERNALLY_CONSISTENT_WITH_UNKNOWN"

    payload = {
        "contract_version": CONTRACT_VERSION,
        "candidate": os.path.relpath(_candidate_root),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "verdict": verdict,
        "note": "PASS means the archives are internally consistent. It is NOT "
                "HARDWARE_QUALIFIED: installed-file hashes, boot-hook persistence, "
                "HTTP binding and a real plate solve require the device matrix (#265).",
        "counts": {
            "checks": len(rep.checks),
            "fail": len(fails),
            "unknown": len(unknowns),
        },
        "checks": rep.checks,
    }

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")

    for c in rep.checks:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "UNKNOWN": "????", "NOT_APPLICABLE": "--  "}[c["verdict"]]
        print(f"[{mark}] {c['component']}: {c['check']} -- {c['reason']}")
    print(f"\nVERDICT: {verdict}  ({len(rep.checks)} checks, {len(fails)} fail, {len(unknowns)} unknown)")
    if fails:
        print("Do not promote this candidate. A FAIL here means the bytes a user "
              "unpacks are missing something a shipped script needs.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

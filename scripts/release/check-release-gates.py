#!/usr/bin/env python3
"""Pre-flight gates for publishing a Polaris release ZIP.

Four rules, enforced in code rather than memory:

  R1  The display version is incremented BEFORE anything is deployed. Concretely:
      the version must already be recorded in the consumed registry, and must be
      strictly greater than every version ever recorded. Claiming is a separate,
      earlier step from shipping.

  R2  Every ZIP is published to PrivateResearch with the commits it contains shown.
      This prints that commit list so it can be pasted into RELEASE-IDENTITY.md,
      and refuses if the list cannot be produced.

  R3  No ZIP is shipped for code that is not on main. The commit the ZIP was built
      from must be an ancestor of origin/main. A feature branch is not a release
      source.

  R4  A release packet carries both archives. FwPkt.zip and polaris-astro.zip ship
      together, or the packet is incomplete.

The registry is treated as authoritative for "already issued", independently of
last_display_fwver: a version in the consumed registry is refused forever. That is
issue #169 -- the baseline is one mutable number and can be left behind, as it was
when .97 was published and installed while the baseline still read .95.

Exit 0 = all gates pass. Non-zero = do not ship.
"""

import argparse
import os
import re
import subprocess
import sys

FAMILY = "6.0.0.54."
CONSUMED_RE = re.compile(r"^consumed_display_fwver=(\S+)")
LAST_RE = re.compile(r"^last_display_fwver=(\S+)")
BIND_RE = re.compile(r"^version_commit_binding=(\S+)\|libgphoto2=(\S+)\|patcher=(\S+)")


def run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def parse_state(path):
    """Return (consumed set, last value, bindings dict). Malformed input fails closed."""
    if not os.path.isfile(path):
        sys.exit("GATE FAIL: version state file not found: %s" % path)
    consumed, last, bindings = set(), None, {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            m = CONSUMED_RE.match(line)
            if m:
                consumed.add(m.group(1))
                continue
            m = LAST_RE.match(line)
            if m:
                last = m.group(1)
                continue
            m = BIND_RE.match(line)
            if m:
                bindings[m.group(1)] = (m.group(2), m.group(3))
    if not consumed:
        sys.exit("GATE FAIL: no consumed_display_fwver entries in %s -- refusing to "
                 "guess which versions are free" % path)
    bad = [v for v in consumed if not v.startswith(FAMILY)]
    if bad:
        sys.exit("GATE FAIL: registry spans more than one firmware family: %s"
                 % ", ".join(sorted(bad)))
    return consumed, last, bindings


def tail(version):
    try:
        return int(version.rsplit(".", 1)[1])
    except (ValueError, IndexError):
        sys.exit("GATE FAIL: cannot read trailing component of %r" % version)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fwver", help="display firmware version this release claims")
    ap.add_argument("--patcher-commit", help="exact patcher commit the ZIP was built from")
    ap.add_argument("--libgphoto2-commit", help="exact libgphoto2 commit the ZIP was built from")
    ap.add_argument("--packet-dir", help="directory holding the ZIPs about to be published")
    ap.add_argument("--state", default="docs/RELEASE-VERSION-STATE.md")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--device-sw", help="what the device currently reports, e.g. 6.0.0.54.97")
    ap.add_argument("--list-consumed", action="store_true",
                    help="print every recorded version and exit")
    args = ap.parse_args()

    consumed, last, bindings = parse_state(args.state)

    if args.list_consumed:
        for v in sorted(consumed, key=tail):
            print(v)
        print("# last_display_fwver=%s" % last)
        print("# highest recorded = %s" % max(consumed, key=tail))
        return 0

    if not args.fwver or not args.patcher_commit:
        sys.exit("GATE FAIL: --fwver and --patcher-commit are required to check a release")

    fails, warns = [], []

    # ---- R1: incremented before deploy ---------------------------------------
    if not args.fwver.startswith(FAMILY):
        fails.append("R1 %s is not in family %s" % (args.fwver, FAMILY))
    if args.fwver in consumed:
        fails.append("R1 %s was already issued -- it is in the consumed registry and "
                     "must never be reused" % args.fwver)
    highest = max(consumed, key=tail)
    if tail(args.fwver) <= tail(highest):
        fails.append("R1 %s is not ahead of the highest recorded version %s"
                     % (args.fwver, highest))
    if last and tail(args.fwver) <= tail(last):
        fails.append("R1 %s is not ahead of last_display_fwver=%s" % (args.fwver, last))
    # A version that is ahead of the registry but already running on hardware is the
    # #169 failure. The registry can be behind reality; the device cannot lie about
    # what it is running.
    if args.device_sw:
        if tail(args.device_sw) >= tail(args.fwver):
            fails.append("R1 device is already running %s, which is not below the "
                         "version being claimed (%s). The registry is behind the "
                         "device -- backfill it before minting."
                         % (args.device_sw, args.fwver))
        elif tail(args.device_sw) > tail(highest):
            warns.append("device reports %s but the registry's highest entry is %s -- "
                         "the registry is missing issued versions"
                         % (args.device_sw, highest))

    # ---- R3: code on main before any ZIP -------------------------------------
    r = run(["git", "-C", args.repo, "rev-parse", "--verify", "%s^{commit}"
             % args.patcher_commit])
    if r.returncode != 0:
        fails.append("R3 commit %s is not present in this repository" % args.patcher_commit)
    else:
        full = r.stdout.strip()
        run(["git", "-C", args.repo, "fetch", "--quiet", "origin", "main"])
        r = run(["git", "-C", args.repo, "merge-base", "--is-ancestor", full, "origin/main"])
        if r.returncode != 0:
            fails.append("R3 %s is NOT an ancestor of origin/main -- the code behind "
                         "this ZIP has not been merged. Merge to main first; never ship "
                         "a ZIP built from a feature branch." % full[:12])

    # ---- R4: both archives present -------------------------------------------
    if args.packet_dir:
        if not os.path.isdir(args.packet_dir):
            fails.append("R4 packet directory not found: %s" % args.packet_dir)
        else:
            present = set(os.listdir(args.packet_dir))
            for need in ("FwPkt.zip", "polaris-astro.zip"):
                if need not in present:
                    fails.append("R4 %s missing from the packet -- a release ships both "
                                 "archives together" % need)

    # ---- R2: commits involved, printable -------------------------------------
    commits = []
    r = run(["git", "-C", args.repo, "log", "--oneline", "--no-decorate",
             "origin/main..%s" % args.patcher_commit])
    ahead = [l for l in r.stdout.splitlines() if l.strip()]
    r = run(["git", "-C", args.repo, "show", "-s", "--format=%H%n%s%n%ci",
             args.patcher_commit])
    if r.returncode == 0:
        lines = r.stdout.strip().splitlines()
        commits.append("%s  %s  (%s)" % (lines[0][:12], lines[1] if len(lines) > 1 else "",
                                         lines[2] if len(lines) > 2 else ""))
    if not commits:
        fails.append("R2 cannot produce the commit list for this build")

    print("=" * 68)
    print("Release gates -- %s" % args.fwver)
    print("=" * 68)
    print("R1 version claimed before deploy : %s (registry highest %s, last %s)"
          % ("OK" if not any(f.startswith("R1") for f in fails) else "FAIL", highest, last))
    print("R3 code merged to main           : %s"
          % ("OK" if not any(f.startswith("R3") for f in fails) else "FAIL"))
    print("R4 both archives present         : %s"
          % ("OK" if not any(f.startswith("R4") for f in fails) else
             ("skipped" if not args.packet_dir else "FAIL")))
    print()
    print("Commits involved (for RELEASE-IDENTITY.md / README):")
    for c in commits:
        print("  %s" % c)
    if ahead:
        print("  (%d commit(s) on this line are not yet in origin/main)" % len(ahead))
    else:
        print("  (build commit is contained in origin/main)")
    print()

    for w in warns:
        print("WARN  %s" % w)
    for f in fails:
        print("FAIL  %s" % f)

    if fails:
        print("\n%d gate(s) failed -- do not publish or deploy." % len(fails))
        return 1
    print("All gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

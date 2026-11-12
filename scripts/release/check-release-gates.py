#!/usr/bin/env python3
"""Pre-flight gates for publishing a Polaris release ZIP.

Five rules, enforced in code rather than memory:

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

  R5  The shipped on-disk scripts are byte-identical to the commit the build claims.
      R3 proves only that the build commit is an ancestor of origin/main, so a build
      made from a commit that is merged but BEHIND main passes R3 while shipping
      stale payload. R5 compares every file in container/astro/ondisk/ against the
      copy inside the built astro bundle and fails on any difference.

The registry is treated as authoritative for "already issued", independently of
last_display_fwver: a version in the consumed registry is refused forever. That is
issue #169 -- the baseline is one mutable number and can be left behind, as it was
when .97 was published and installed while the baseline still read .95.

R5 exists because of a real miss on 2026-11-12. The v106 candidate was built from
patcher commit 73e3066123b7, which is an ancestor of origin/main, so R3 printed
"OK" and "(build commit is contained in origin/main)". main had moved on by 20
commits, two of which change files that ship inside the packet:

    container/astro/ondisk/polaris-autosolve.sh   #321 solve duration + frame dims
    container/astro/ondisk/polaris-align.sh       #321 TIMEOUT classification

The built copies differed by digest and lacked the #321 code entirely -- the packet
copy of polaris-autosolve.sh has zero occurrences of FRAME_DIMS_FILE where main has
three -- yet every gate was green. Ancestry answers "was this merged", never "is
this current".

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


# Paths in the patcher repository whose contents ship INSIDE the astro packet.
# container/astro/ondisk/*.sh and site.conf.example are copied verbatim into
# COPY-TO-SD-CARD-ROOT/polaris-astro/, and a subset of the same directory is
# copied into polaris-wifi/. A change to any of them changes what a user runs,
# so a build that predates such a change is shipping different code than its
# recorded commit implies. Kept as a list of repo-relative prefixes rather than
# a hardcoded file list so new ondisk scripts are covered automatically.
SHIPPED_PATHS = ("container/astro/ondisk",)


def find_shipped_dir(packet_dir, subdir):
    """Locate COPY-TO-SD-CARD-ROOT/<subdir> under a candidate or bundle directory.

    Callers pass either the candidate directory (which contains astro-bundle/) or
    the bundle itself. Returns None when not found; the caller must treat that as
    a failure, never as a pass.
    """
    candidates = [
        os.path.join(packet_dir, "astro-bundle", "COPY-TO-SD-CARD-ROOT", subdir),
        os.path.join(packet_dir, "COPY-TO-SD-CARD-ROOT", subdir),
        os.path.join(packet_dir, subdir),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def blob_at(repo, commit, path):
    """Blob hash of <path> at <commit>, or None if it does not exist there."""
    r = run(["git", "-C", repo, "ls-tree", commit, "--", path])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    # mode SP type SP hash TAB path
    try:
        return r.stdout.split("\t", 1)[0].split()[2]
    except IndexError:
        return None


def blob_of_file(repo, path, relpath=None):
    """Blob hash of a working-tree file, with the same filters git applied at
    commit time. Returns None if the file cannot be hashed.

    --path is required for correctness here. This repo sets '* text=auto eol=lf'
    in .gitattributes, and the file being hashed lives OUTSIDE the worktree (it is
    inside a built candidate under /home/ian/polaris-v101/out/...), so git cannot
    infer which attributes apply. Without --path git hashes the raw bytes; if the
    packet copy ever carries CRLF the comparison would pass while the shipped
    script has a bad shebang interpreter -- upstream issue #1.
    """
    cmd = ["git", "-C", repo, "hash-object"]
    if relpath:
        cmd += ["--path", relpath]
    cmd += ["--", path]
    r = run(cmd)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


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
    ap.add_argument("--allow-partial", action="store_true",
                    help="explicitly permit a release that ships fewer than both ZIPs")
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
    # Bound up front: R5 and the summary line both need it, and if rev-parse fails
    # they must report that rather than raise NameError and exit with no verdict.
    full = None
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
    # Reporting OK for a check that never ran is worse than no check: it turns an
    # omitted argument into a green light. --allow-partial must be explicit.
    r4 = "OK"
    if args.packet_dir:
        if not os.path.isdir(args.packet_dir):
            fails.append("R4 packet directory not found: %s" % args.packet_dir)
            r4 = "FAIL"
        else:
            present = set(os.listdir(args.packet_dir))
            missing = [n for n in ("FwPkt.zip", "polaris-astro.zip") if n not in present]
            for need in missing:
                fails.append("R4 %s missing from the packet -- a release ships both "
                             "archives together" % need)
            r4 = "FAIL" if missing else "OK"
    elif args.allow_partial:
        r4 = "SKIPPED (--allow-partial)"
    else:
        r4 = "NOT CHECKED"
        fails.append("R4 no --packet-dir given, so the archives were never checked. "
                     "Pass --packet-dir DIR, or --allow-partial if this release "
                     "deliberately ships fewer than both ZIPs.")

    # ---- R5: shipped payload matches the commit it claims --------------------
    # Two distinct questions, both needed:
    #   (a) integrity  -- does the packet contain exactly the ondisk files of the
    #                     recorded patcher commit?
    #   (b) currency   -- do those same paths differ between the recorded commit
    #                     and origin/main? A commit can be merged (R3 green) and
    #                     still be 20 commits behind main.
    # R3 cannot answer either: ancestry says nothing about how far behind main a
    # commit is, and it never looks at file contents.
    r5 = "OK"
    if not args.packet_dir or not os.path.isdir(args.packet_dir):
        r5 = "NOT CHECKED"
        fails.append("R5 no usable --packet-dir, so the shipped on-disk scripts were "
                     "never compared. A build can be merged to main and still ship "
                     "payload 20 commits behind it; only a content comparison sees "
                     "that.")
    elif full is None:
        r5 = "NOT CHECKED"
        fails.append("R5 cannot compare shipped files because the build commit %s could "
                     "not be resolved (see R3)." % args.patcher_commit)
    else:
        repo = os.path.abspath(args.repo)
        shipped = {"polaris-astro": find_shipped_dir(args.packet_dir, "polaris-astro"),
                   "polaris-wifi": find_shipped_dir(args.packet_dir, "polaris-wifi")}
        found = [d for d in shipped.values() if d]
        if not found:
            r5 = "FAIL"
            fails.append("R5 could not locate COPY-TO-SD-CARD-ROOT/polaris-astro under "
                         "%s. Refusing to report OK for a comparison that did not run." %
                         args.packet_dir)
        else:
            # (b) currency: shipped paths changed between the build commit and main.
            diff = run(["git", "-C", repo, "diff", "--name-only",
                        "%s..origin/main" % full, "--"] + list(SHIPPED_PATHS))
            if diff.returncode != 0:
                r5 = "FAIL"
                fails.append("R5 could not diff %s..origin/main for the shipped paths: %s"
                             % (full[:12], diff.stderr.strip() or "git diff failed"))
            else:
                drifted = [l.strip() for l in diff.stdout.splitlines() if l.strip()]
                if drifted:
                    r5 = "FAIL"
                    fails.append(
                        "R5 %s is merged but BEHIND origin/main on files that ship "
                        "inside this packet (%d changed):\n      %s\n    "
                        "The packet contains the OLD copies. Rebuild from the current "
                        "origin/main tip; do not ship this ZIP." % (
                            full[:12], len(drifted), "\n      ".join(drifted)))

            # (a) integrity: every shipped ondisk file matches its blob at the commit.
            checked = 0
            for name, dest in shipped.items():
                if not dest:
                    continue
                for entry in sorted(os.listdir(dest)):
                    src = os.path.join("container/astro/ondisk", entry)
                    want = blob_at(repo, full, src)
                    if want is None:
                        continue  # binary built here, or copied from elsewhere
                    got = blob_of_file(repo, os.path.join(dest, entry), relpath=src)
                    checked += 1
                    if got != want:
                        r5 = "FAIL"
                        fails.append(
                            "R5 %s/%s does not match container/astro/ondisk/%s at "
                            "%s (packet blob %s, commit blob %s). The packet ships "
                            "different code than its recorded provenance." % (
                                name, entry, entry, full[:12],
                                (got or "?")[:12], want[:12]))
            if checked == 0:
                r5 = "FAIL"
                fails.append("R5 compared 0 shipped files against %s. A vacuous pass is "
                             "worse than no check -- the ondisk mapping has probably "
                             "moved. Update SHIPPED_PATHS in this script." % full[:12])

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
    print("R4 both archives present         : %s" % r4)
    print("R5 shipped payload current       : %s" % r5)
    print()
    print("Commits involved (for RELEASE-IDENTITY.md / README):")
    for c in commits:
        print("  %s" % c)
    if ahead:
        print("  (%d commit(s) on this line are not yet in origin/main)" % len(ahead))
    else:
        # Wording matters: "contained in origin/main" reads like an all-clear and
        # it is not. A commit merged months ago is contained and can be far behind.
        behind = "?"
        if full:
            behind = run(["git", "-C", args.repo, "rev-list", "--count",
                          "%s..origin/main" % full]).stdout.strip() or "?"
        print("  (build commit is contained in origin/main; origin/main is %s "
              "commit(s) ahead -- R5 checks whether any of them ship in this packet)"
              % behind)
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

#!/usr/bin/env python3
"""Compare two candidates' shipped artifacts (#214 follow-up).

Two failure modes this catches, both of which have actually happened here:

A -- a new display version is issued for a tree whose shipped bytes are unchanged.
   `.70` built from today's `main` would carry ten manifest files byte-identical to
   `.69`, because every commit since the `.69` claim touched docs, tests or host
   tooling. Benro Connect would show two firmwares that cannot behave differently.
   `version_commit_binding` cannot see this: it binds commit shas, and the patcher
   sha moves whenever a README is edited.

B -- one display version quietly carries changes in more than one shipped component.
   `.69` was registered as "only behavioural change is libgphoto2 23008c229 (dark-frame
   budget)". It also carried `76e0920`, a change to the shipped loader, so both
   `ptp2.so` and `libpolaris_stage2.so` moved under one number. Anyone reasoning about
   what `.69` did -- or rolling it back -- would have been working from an incomplete
   description.

Exit codes: 0 pass (warnings allowed), 1 a check failed or a manifest is missing,
2 usage error. A missing manifest on the candidate being built is a real failure -- the
build did not produce one -- so it does not skip.

Usage:
    verify_candidate_differential.py --previous out/<cand> [--current out/<cand>]
    verify_candidate_differential.py --auto-detect --current out/<cand>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Components whose movement means a version spans more than one subsystem.
COMPONENTS = {
    "ptp2.so": "libgphoto2 PTP driver (camera protocol behaviour)",
    "pentax.so": "libgphoto2 Pentax driver",
    "libpolaris_stage2.so": "Stage-2 loader (shim/preload layer)",
    "polestar_app": "Benro appliance application",
    "pgphoto.stage2ondisk": "pgphoto wrapper",
}

# The normal candidate contains the PTP stack plus the USB transport used by
# ordinary cameras.  The release flow may also add this deliberately optional
# transport for K-5 II/K-5 IIs support.  A change to any other path remains a
# hard file-set failure; this allowlist prevents the optional legacy transport
# from being mistaken for an accidental package drift.
OPTIONAL_FILE_SET = {
    "/app/lib/stage2/libgphoto2_port/0.12.2/usbscsi.so",
}

FWVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)")


def load_manifest(candidate_dir: str) -> dict:
    path = os.path.join(candidate_dir, "install-manifest.json")
    if not os.path.isfile(path):
        raise SystemExit(f"ERROR: no install-manifest.json in {candidate_dir}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "files" not in data or not isinstance(data["files"], list):
        raise SystemExit(f"ERROR: {path} has no files[] list")
    return data


def digest_map(manifest: dict) -> dict[str, str]:
    return {f["path"]: f["sha256"] for f in manifest["files"]}


def version(manifest: dict) -> tuple[int, ...] | None:
    m = FWVER_RE.search(manifest.get("fwver_content", "") or "")
    return tuple(int(x) for x in m.groups()) if m else None


def component(path: str) -> str | None:
    base = os.path.basename(path)
    return base if base in COMPONENTS else None


def auto_previous(out_dir: str, current: str) -> str | None:
    """Most recent other candidate under out/ that has a manifest, newest first."""
    if not os.path.isdir(out_dir):
        return None
    entries = []
    for name in os.listdir(out_dir):
        d = os.path.join(out_dir, name)
        if not os.path.isdir(d) or os.path.abspath(d) == os.path.abspath(current):
            continue
        if name.startswith(("REJECTED", "partial")):
            continue
        mf = os.path.join(d, "install-manifest.json")
        if os.path.isfile(mf):
            entries.append((os.path.getmtime(mf), d))
    if not entries:
        return None
    return max(entries)[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--current", required=True, help="candidate being built/checked")
    ap.add_argument("--previous", help="candidate to compare against")
    ap.add_argument(
        "--auto-detect",
        action="store_true",
        help="pick the newest other candidate under out/ as --previous",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat a multi-component version span as a failure, not a warning",
    )
    args = ap.parse_args()

    if not args.previous:
        if not args.auto_detect:
            print("ERROR: give --previous or --auto-detect", file=sys.stderr)
            return 2
        args.previous = auto_previous(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out"),
            args.current,
        )
        if not args.previous:
            print("SKIP: no previous candidate with a manifest to compare against")
            return 0

    cur = load_manifest(args.current)
    prev = load_manifest(args.previous)
    cur_v, prev_v = version(cur), version(prev)
    if cur_v is None or prev_v is None:
        print("SKIP: a manifest lacks a parseable FwVer")
        return 0

    cur_files, prev_files = digest_map(cur), digest_map(prev)
    name_cur = cur.get("candidate", os.path.basename(args.current))
    name_prev = prev.get("candidate", os.path.basename(args.previous))
    print(f"comparing {name_prev} ({'.'.join(map(str, prev_v))}) -> "
          f"{name_cur} ({'.'.join(map(str, cur_v))})")

    only_cur = sorted(set(cur_files) - set(prev_files))
    only_prev = sorted(set(prev_files) - set(cur_files))
    file_set_delta = set(only_cur) | set(only_prev)
    if file_set_delta:
        if file_set_delta <= OPTIONAL_FILE_SET:
            print("WARN: optional legacy transport file set changed")
            for p in only_cur:
                print(f"  added optional file: {p}")
            for p in only_prev:
                print(f"  removed optional file: {p}")
        else:
            print("FAIL: the mandatory file set differs between candidates")
            for p in only_cur:
                print(f"  only in current: {p}")
            for p in only_prev:
                print(f"  only in previous: {p}")
            return 1

    changed = [p for p in sorted(set(cur_files) & set(prev_files))
               if cur_files[p] != prev_files[p]]
    changed.extend(file_set_delta)

    # Failure mode A: a new version number describing identical shipped bytes.
    if not changed:
        if cur_v == prev_v:
            print("FAIL: same display version on two candidates")
            return 1
        print(f"FAIL: display version advanced to {'.'.join(map(str, cur_v))} but all "
              f"{len(cur_files)} shipped files are byte-identical to "
              f"{'.'.join(map(str, prev_v))}")
        print("  This version would describe a build that cannot behave differently "
              "from the previous one. Put real content in it, or do not claim it.")
        return 1

    print(f"{len(changed)} of {len(cur_files)} shipped files changed:")
    for p in changed:
        comp = component(p)
        suffix = f"  <- {COMPONENTS[comp]}" if comp else ""
        print(f"  {p}{suffix}")

    # Failure mode B: one version spanning more than one shipped component.
    moved = sorted({component(p) for p in changed if component(p)})
    if len(moved) > 1:
        print(f"WARN: this single display version moves {len(moved)} shipped components:")
        for c in moved:
            print(f"  - {c}: {COMPONENTS[c]}")
        print("  The registry entry must describe every one of them, or a later "
              "diagnosis/rollback will reason from an incomplete description.")
        if args.strict:
            return 1

    print("PASS: shipped artifacts differ and the change set is reported")
    return 0


if __name__ == "__main__":
    sys.exit(main())

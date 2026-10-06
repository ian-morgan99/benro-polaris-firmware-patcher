#!/usr/bin/env python3
"""Assert that every `wrote=<path>` the camlib logged is a real file on the device.

Issue #175 review (id=6003891462): the orphan-recovery fix writes the claimed
object to disk with gp_file_save() *before* the camera object is deleted, and
the audit line reports `wrote=<path>`. The code and its unit tests are in place;
what was still missing is the on-device assertion that the named path actually
exists. Without it, "the frame was preserved" is only a claim the process made
about itself -- which is exactly the failure #175 was about (IMGP3794-3797 were
each reported as recovered and appear nowhere on the card).

The audit line is emitted by camlibs/ptp2/library.c (pentax_recover_orphan_
candidates) to stderr, which the pgphoto wrapper lands in the rotating
Clog files on the card:

  [pentax-recovery] capture=N path=orphan-recovery outcome=cleared recovered=1
      names=IMGP3794.DNG accepted=1 ... wrote=/app/sd/pentax-recovered/
      IMGP3794-orphan-3794.dng

A `wrote=` path that is absent, or present but zero-length, is a failure: the
delete has already happened by then, so the image is gone and the only evidence
that it ever existed is the log line.

Usage:
  # check the device directly (default)
  scripts/assert-orphan-wrote.py --host root@192.168.0.1

  # or check an already-pulled log copy (no device needed)
  scripts/assert-orphan-wrote.py --log-file out/logs/device-20261006/c2.log

Exit codes: 0 = every wrote= path is a real non-empty file (or nothing claimed
to be written); 1 = at least one path is missing/empty; 2 = usage/harness error.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys

DEFAULT_HOST = "root@192.168.0.1"
# The real logs are the rotating Clog_NNNNNN.log files on the card. /app/Clog.txt
# is truncated in place by the stock firmware and loses these lines (#172).
DEFAULT_LOG_GLOB = "/app/sd/system/log/Clog_*.log"

_WROTE_RE = re.compile(r"wrote=(\S+)")


def parse_wrote_paths(text: str) -> list[str]:
    """Return the recovery paths the camlib claimed to have written.

    Order is preserved and duplicates collapsed: the same path can legitimately
    appear in more than one rotated copy of the same log, and asserting on it
    twice adds no evidence.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for match in _WROTE_RE.finditer(text):
        path = match.group(1).strip()
        # The audit line ends the record with the path, so a trailing delimiter
        # means the line was truncated mid-write and the name is not trustworthy.
        if not path.startswith("/") or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def build_check_command(paths: list[str]) -> str:
    """Shell command that reports `path|ok|size` or `path|missing|0` per path.

    `-e` decides ok/missing and the size is reported alongside it, so a file
    that exists but is empty is diagnosed as such rather than lumped in with a
    genuinely absent one. A zero-length file after a gp_file_save() that
    returned GP_OK is the same loss as no file at all -- it is the signature of
    a save the filesystem refused -- and evaluate_report() fails it either way.
    """
    quoted = " ".join(shlex.quote(p) for p in paths)
    return (
        'for f in ' + quoted + '; do '
        'if [ -e "$f" ]; then printf "%s|%s|%s\\n" "$f" ok "$(stat -c %s "$f" 2>/dev/null || echo 0)"; '
        'else printf "%s|%s|%s\\n" "$f" missing 0; fi; '
        'done'
    )


def evaluate_report(report: str, expected: list[str]) -> list[str]:
    """Return a list of human-readable failures; empty means the assertion held.

    Fail-closed on a missing report line: if the device did not answer for a
    path we cannot claim the file is there.
    """
    if not expected:
        return []
    parsed: dict[str, tuple[str, str]] = {}
    for line in report.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            parsed[parts[0]] = (parts[1], parts[2])
    failures: list[str] = []
    for path in expected:
        entry = parsed.get(path)
        if entry is None:
            failures.append(f"{path}: no report line (device did not answer for it)")
        elif entry[0] != "ok":
            failures.append(f"{path}: reported missing -- the delete left no image behind")
        elif entry[1] in ("", "0"):
            failures.append(f"{path}: present but zero-length -- save did not produce bytes")
    return failures


def read_device_log(host: str, log_glob: str, ssh_options: list[str]) -> str:
    cmd = ssh_options + [host, f"cat {log_glob} 2>/dev/null"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          check=False)
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(f"reading device logs failed ({proc.returncode}): "
                           f"{proc.stderr.strip()[:200]}")
    return proc.stdout


def query_device(host: str, paths: list[str], ssh_options: list[str]) -> str:
    cmd = ssh_options + [host, build_check_command(paths)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                          check=False)
    return proc.stdout


def local_report(root: str, paths: list[str]) -> str:
    """Same `path|ok|size` report as the device check, against a pulled tree.

    The report keys on the *device* path so evaluate_report() stays identical
    whichever transport produced the evidence.
    """
    lines = []
    for path in paths:
        local = os.path.join(root, path.lstrip("/"))
        try:
            size = os.stat(local).st_size
        except OSError:
            lines.append(f"{path}|missing|0")
            continue
        lines.append(f"{path}|ok|{size}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--log-glob", default=DEFAULT_LOG_GLOB,
                    help="device-side glob for the Clog files to read")
    ap.add_argument("--log-file",
                    help="check an already-pulled local log copy instead of the device")
    ap.add_argument("--root",
                    help="with --log-file: local directory the device paths are mounted "
                         "under, e.g. --root out/logs/device-20261006/files, so "
                         "/app/sd/x becomes out/logs/.../files/app/sd/x. Without it a "
                         "local log only enumerates the claims.")
    ap.add_argument("--ssh-option", action="append", default=[],
                    help="extra ssh argument (repeatable)")
    args = ap.parse_args()

    ssh_options = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                   *args.ssh_option]

    if args.log_file:
        try:
            with open(args.log_file, "r", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            print(f"[assert-orphan-wrote] FATAL cannot read {args.log_file}: {exc}",
                  file=sys.stderr)
            return 2
        if args.root and not os.path.isdir(args.root):
            print(f"[assert-orphan-wrote] FATAL --root is not a directory: {args.root}",
                  file=sys.stderr)
            return 2
        check = (lambda paths: local_report(args.root, paths)) if args.root else None
    else:
        try:
            text = read_device_log(args.host, args.log_glob, ssh_options)
        except (RuntimeError, subprocess.SubprocessError) as exc:
            print(f"[assert-orphan-wrote] FATAL {exc}", file=sys.stderr)
            return 2
        check = lambda paths: query_device(args.host, paths, ssh_options)  # noqa: E731

    paths = parse_wrote_paths(text)
    if not paths:
        # Nothing claimed to be written. That is a pass for this assertion, but
        # it is not evidence the recovery path ran -- say so rather than imply it.
        print("[assert-orphan-wrote] PASS (vacuous) no wrote= lines found; this "
              "run did not exercise orphan recovery", flush=True)
        return 0

    print(f"[assert-orphan-wrote] found {len(paths)} wrote= path(s); asserting "
          "each is a real non-empty file", flush=True)
    for path in paths:
        print(f"  {path}", flush=True)

    if check is None:
        print("[assert-orphan-wrote] INCONCLUSIVE the claims were read from a local "
              "log copy and --root was not given, so nothing could be stat-ed. "
              "Re-run against the device, or pass --root pointing at a pulled "
              "file tree.", file=sys.stderr)
        return 2
    report = check(paths)
    failures = evaluate_report(report, paths)
    for failure in failures:
        print(f"[assert-orphan-wrote] FAIL {failure}", flush=True)
    if failures:
        return 1
    print("[assert-orphan-wrote] PASS every wrote= path is a real non-empty file",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

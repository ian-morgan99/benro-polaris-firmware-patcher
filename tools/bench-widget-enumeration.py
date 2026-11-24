#!/usr/bin/env python3
"""#389 -- reproducible widget-enumeration performance A/B for Pentax bodies.

Why this exists
---------------
Two independent measurement errors were made on the way to the #389 numbers, and
both are encoded here as hard checks so they cannot recur:

1. The settings-format trap (R7). libgphoto2 reads ``cachetime`` from
   ``$XDG_CONFIG_HOME/gphoto/settings`` and only falls back to the legacy
   ``~/.gphoto/settings`` when the XDG file does not exist. The line format is a
   flat ``section=key=value`` -- it needs TWO '=' characters, e.g.::

       ptp2=cachetime=30

   Writing INI syntax (``[ptp2]`` / ``cachetime=30``) makes ``verify_settings()``
   (gphoto2-settings.c:245) *unlink the file*. The first A/B therefore measured
   the default twice and reported a 49.66 s -> 27.12 s improvement that never
   happened. It was retracted.

2. Misreading a failed session as an efficient one (R5). When OpenSession is
   refused -- commonly ``PTP_RC_DeviceBusy`` 0x02fa, a legitimate post-capture
   state per docs/pentax-mode-aware-liveness.md -- the op count is tiny and the
   wall clock is huge. That looks like "fast" on a naive summary. It means the
   session never completed. A run is only reportable when the exit code is clean
   and no busy/timeout marker is present.

What it measures
----------------
For each ``cachetime`` value, in an isolated config dir: wall clock and PTP op
counts for a 1-widget read and an N-widget enumeration. The headline metric is
``0x1014`` (GetDevicePropDesc) fetches, because descriptor expiry is the
dominant cost -- 191 of 263 fetches at cachetime=2 in the validated run.

This tool measures; it does not change the driver. The #389 fix must be a
mode-keyed cache (Pentax enums are mode-dependent -- the Bulb shutter enum has
zero fractional values -- so a wall-clock TTL alone serves stale choice lists,
the #316 failure class), and it must be validated on a responsive body in the
registered worktree before anything ships.

Usage
-----
    tools/bench-widget-enumeration.py --dry-run
    tools/bench-widget-enumeration.py --cachetime 2,30 --widgets 10

Emits JSONL to stdout: one "meta", then one record per measurement. Read-only
with respect to the camera: it only issues list/get-config reads, never writes a
property and never resets USB.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Flat "section=key=value" form. verify_settings() requires two '=' per line and
# unlinks the file otherwise -- see the module docstring.
SETTINGS_LINE = "ptp2=cachetime=%d"

# Markers that mean "this session did not complete", so its timings are
# meaningless. 0x02fa is PTP_RC_DeviceBusy.
FAILURE_MARKERS = (
    "0x02fa",
    "DeviceBusy",
    "refusing session close",
    "Timeout",
    "PTP I/O problem",
    "Could not connect",
)

# Opcodes worth counting. 0x1014 is the one #389 is about.
OPCODES = {
    "GetDevicePropDesc": "0x1014",
    "GetPropValue": "0x1015",
    "GetAllConditions": "0x900f",
    "GetDeviceInfo": "0x1001",
    "GetObjectHandles": "0x1007",
}

# A run with few ops but a long wall clock is the signature of a session that
# never opened. Below this many descriptor fetches for an N-widget walk the
# result is suspect rather than fast.
SUSPECT_OPS_PER_WIDGET = 1


def render_settings(cachetime: int) -> str:
    """Return the settings file body for one cachetime value.

    Deliberately a single flat line. INI sections are wrong here and cause the
    file to be deleted by libgphoto2, which silently reverts to the default.
    """
    if not isinstance(cachetime, int) or cachetime <= 0:
        raise ValueError("cachetime must be a positive integer")
    return SETTINGS_LINE % cachetime + "\n"


def validate_settings_body(body: str) -> list[str]:
    """Return a list of format problems; empty means libgphoto2 will accept it."""
    problems = []
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        problems.append("settings body is empty")
    for line in lines:
        if line.startswith("["):
            problems.append(
                "INI section header %r is not accepted; use flat section=key=value" % line
            )
        if line.count("=") < 2:
            problems.append(
                "%r has fewer than two '='; verify_settings() unlinks the file" % line
            )
    return problems


def settings_path(xdg_config_home: str) -> str:
    return os.path.join(xdg_config_home, "gphoto", "settings")


def write_settings(xdg_config_home: str, cachetime: int) -> str:
    """Write the settings file and re-read it to prove it survived on disk."""
    body = render_settings(cachetime)
    problems = validate_settings_body(body)
    if problems:
        raise ValueError("refusing to write invalid settings: " + "; ".join(problems))
    path = settings_path(xdg_config_home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    # verify_settings() unlinks malformed files, so confirm it is still there.
    if not os.path.exists(path):
        raise RuntimeError("settings file was removed after write -- format rejected")
    with open(path, encoding="utf-8") as handle:
        if handle.read() != body:
            raise RuntimeError("settings file content does not match what was written")
    return path


def count_ops(text: str) -> dict[str, int]:
    """Count PTP opcode occurrences in gphoto2 debug output.

    Debug lines may carry the opcode as a name or as hex, and sometimes both on
    one line, so per-opcode we take the larger of the two counts rather than the
    sum -- summing would double-count those lines.
    """
    counts = {}
    for name, hexcode in OPCODES.items():
        by_name = len(re.findall(r"\b%s\b" % re.escape(name), text))
        # Match the literal "0x1014" form. Matching bare digits would also hit
        # propcodes, timestamps and session ids in debug output.
        by_hex = len(re.findall(re.escape(hexcode), text, re.IGNORECASE))
        counts[hexcode] = max(by_name, by_hex)
    return counts


def find_failure_markers(text: str) -> list[str]:
    return [marker for marker in FAILURE_MARKERS if marker.lower() in text.lower()]


def classify_run(exit_code: int, output: str, ops: dict[str, int], widgets: int,
                 wall_s: float) -> tuple[bool, list[str]]:
    """Decide whether a measurement is reportable.

    Returns (reportable, reasons). This is the R5 guard: a low op count with a
    high wall clock must be reported as a failed session, never as an
    improvement.
    """
    reasons = []
    markers = find_failure_markers(output)
    if markers:
        reasons.append("session failure marker(s): " + ", ".join(markers))
    if exit_code != 0:
        reasons.append("gphoto2 exit code %d" % exit_code)
    desc = ops.get("0x1014", 0)
    if not reasons and widgets > 0 and desc < SUSPECT_OPS_PER_WIDGET * widgets:
        reasons.append(
            "only %d descriptor fetches for %d widget(s) in %.2f s -- below the "
            "expected walk; treat as an incomplete session, not a fast run"
            % (desc, widgets, wall_s)
        )
    return (not reasons), reasons


def gphoto_env(xdg_config_home: str, debug: bool) -> dict[str, str]:
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = xdg_config_home
    if debug:
        # GP_DEBUG is the modern spelling; GP_DEBUG_LEVEL keeps older builds happy.
        env["GP_DEBUG"] = "1"
        env.setdefault("GP_DEBUG_LEVEL", "2")
    return env


def run_gphoto2(args: list[str], env: dict[str, str], timeout_s: int) -> tuple[int, float, str]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["gphoto2", "--quiet"] + args,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        raise SystemExit("gphoto2 is not installed; install it before measuring #389")
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        return 124, time.monotonic() - started, partial + "\nTimeout"
    wall = time.monotonic() - started
    return proc.returncode, wall, (proc.stdout or "") + "\n" + (proc.stderr or "")


def measure(xdg_config_home: str, cachetime: int, widgets: int, debug: bool,
            timeout_s: int) -> dict:
    path = write_settings(xdg_config_home, cachetime)
    env = gphoto_env(xdg_config_home, debug)

    exit_code, wall_single, out_single = run_gphoto2(["--list-config"], env, timeout_s)
    ops_single = count_ops(out_single)
    ok_single, why_single = classify_run(exit_code, out_single, ops_single, 1, wall_single)

    exit_code_n, wall_n, out_n = run_gphoto2(["--list-config"], env, timeout_s)
    ops_n = count_ops(out_n)
    ok_n, why_n = classify_run(exit_code_n, out_n, ops_n, widgets, wall_n)

    return {
        "kind": "measurement",
        "cachetime": cachetime,
        "settings_path": path,
        "settings_confirmed_on_disk": os.path.exists(path),
        "single_widget": {
            "wall_s": round(wall_single, 3),
            "ops": ops_single,
            "reportable": ok_single,
            "reasons": why_single,
        },
        "enumeration": {
            "widgets": widgets,
            "wall_s": round(wall_n, 3),
            "ops": ops_n,
            "reportable": ok_n,
            "reasons": why_n,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cachetime", default="2,30",
                        help="comma-separated cachetime values to A/B (default 2,30)")
    parser.add_argument("--widgets", type=int, default=10,
                        help="widget count for the enumeration leg (default 10)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="per-invocation timeout in seconds (default 180)")
    parser.add_argument("--no-debug", action="store_true",
                        help="omit GP_DEBUG (op counts will be empty; timing only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate settings handling and exit without touching a camera")
    args = parser.parse_args(argv)

    try:
        values = [int(v) for v in args.cachetime.split(",") if v.strip()]
    except ValueError:
        print("ERROR: --cachetime must be comma-separated integers", file=sys.stderr)
        return 2
    if not values:
        print("ERROR: --cachetime produced no values", file=sys.stderr)
        return 2

    if args.dry_run:
        for value in values:
            body = render_settings(value)
            problems = validate_settings_body(body)
            print(json.dumps({
                "kind": "dry-run",
                "cachetime": value,
                "settings_body": body.rstrip("\n"),
                "format_problems": problems,
            }))
        return 0

    if shutil.which("gphoto2") is None:
        print("ERROR: gphoto2 not found on PATH", file=sys.stderr)
        return 3

    print(json.dumps({
        "kind": "meta",
        "tool": "bench-widget-enumeration",
        "issue": "#389",
        "cachetime_values": values,
        "widgets": args.widgets,
        "debug": not args.no_debug,
        "note": "measurement only; no driver change. See module docstring for the "
                "two measurement errors this tool guards against.",
    }))

    unreportable = 0
    tmpdir = tempfile.mkdtemp(prefix="gpconf-")
    try:
        for value in values:
            record = measure(tmpdir, value, args.widgets, not args.no_debug, args.timeout)
            print(json.dumps(record), flush=True)
            if not (record["single_widget"]["reportable"] and record["enumeration"]["reportable"]):
                unreportable += 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if unreportable:
        print(json.dumps({
            "kind": "verdict",
            "ok": False,
            "reason": "%d cachetime value(s) produced no reportable measurement. A busy "
                      "or refusing body (0x02fa) is a legitimate state -- wait and re-run. "
                      "Do NOT interpret an unreportable run as faster." % unreportable,
        }))
        return 1
    print(json.dumps({"kind": "verdict", "ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

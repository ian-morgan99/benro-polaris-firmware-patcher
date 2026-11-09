#!/usr/bin/env python3
"""Optional host-side Pentax discovery/read-only probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


READ_ONLY_COMMANDS = (
    ("auto-detect", "--auto-detect"),
    ("summary", "--summary"),
    ("model", "--get-config", "/main/status/cameramodel"),
    ("manufacturer", "--get-config", "/main/status/manufacturer"),
    ("battery", "--get-config", "/main/status/batterylevel"),
)


def run(args: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    process = subprocess.run(["gphoto2", *args], capture_output=True, text=True, timeout=timeout, check=False)
    return process.returncode, process.stdout, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-model", help="fail unless the reported model contains this string")
    args = parser.parse_args()
    report: dict[str, object] = {"safe_commands": [entry[1:] for entry in READ_ONLY_COMMANDS]}
    failures: list[str] = []
    outputs: dict[str, str] = {}
    for name, *command in READ_ONLY_COMMANDS:
        try:
            code, stdout, stderr = run(command)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}: {exc}")
            continue
        outputs[name] = stdout.strip()
        if code != 0:
            failures.append(f"{name}: exit={code}: {stderr.strip() or stdout.strip()}")
    report["outputs"] = outputs
    model = outputs.get("model", "")
    if args.expected_model and args.expected_model.lower() not in model.lower():
        failures.append(f"model mismatch: expected {args.expected_model!r}, got {model!r}")
    report["failures"] = failures
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

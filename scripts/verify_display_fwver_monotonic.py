#!/usr/bin/env python3
"""Fail-closed validation for the app-visible Polaris firmware version.

The display version is what Benro Connect shows, so two installed builds must
never report the same value. Historically the value was typed by hand into the
release command and the baseline in RELEASE-VERSION-STATE.md was only advanced
manually, which let several candidates carry the same version.

This module can now derive the next version itself:

    --next      print the next permitted version and exit
    --record    advance the state file to the validated candidate

so a release script can stop relying on a human remembering the bump.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){4}$")
STATE_RE = re.compile(r"^last_display_fwver=([^\s`]+)$", re.MULTILINE)


def current_str(parts: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in parts)


def parse_display_fwver(raw: str) -> tuple[int, ...]:
    """Parse the required canonical five-component display version."""
    value = raw.strip()
    if not VERSION_RE.fullmatch(value):
        raise ValueError(
            f"display firmware version must be five numeric components: {raw!r}"
        )
    parts = tuple(int(part) for part in value.split("."))
    if any(str(part) != raw_part for part, raw_part in zip(parts, value.split("."))):
        raise ValueError(f"display firmware version is not canonical: {raw!r}")
    return parts


def read_last_display_fwver(state_path: Path) -> tuple[int, ...]:
    text = state_path.read_text(encoding="utf-8")
    match = STATE_RE.search(text)
    if not match:
        raise ValueError(f"state file has no last_display_fwver= entry: {state_path}")
    return parse_display_fwver(match.group(1))


def next_display_fwver(last: tuple[int, ...]) -> tuple[int, ...]:
    """Return the next permitted display version: the build counter plus one."""
    if len(last) != 5:
        raise ValueError(f"release baseline must have five components, got {last!r}")
    return (*last[:4], last[4] + 1)


def record_display_fwver(state_path: Path, value: str) -> tuple[int, ...]:
    """Write the accepted display version back into the release-state file."""
    current = parse_display_fwver(value)
    text = state_path.read_text(encoding="utf-8")
    if not STATE_RE.search(text):
        raise ValueError(f"state file has no last_display_fwver= entry: {state_path}")
    state_path.write_text(
        STATE_RE.sub("last_display_fwver=" + current_str(current), text),
        encoding="utf-8",
    )
    return current


def validate_monotonic(candidate: str, last: tuple[int, ...]) -> tuple[int, ...]:
    current = parse_display_fwver(candidate)
    if len(last) != 5:
        raise ValueError(f"release baseline must have five components, got {last!r}")
    if current[:4] != last[:4]:
        raise ValueError(
            "display firmware version family changed: "
            f"baseline={'.'.join(map(str, last))} candidate={candidate}"
        )
    if current <= last:
        raise ValueError(
            "display firmware version was not incremented: "
            f"baseline={'.'.join(map(str, last))} candidate={candidate}"
        )
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", help="five-component version to validate")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--next",
        action="store_true",
        help="print the next permitted version and exit (no validation)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="advance the state file to the validated candidate",
    )
    args = parser.parse_args()
    try:
        last = read_last_display_fwver(args.state)
        if args.next:
            print(current_str(next_display_fwver(last)))
            return 0
        if not args.candidate:
            parser.error("--candidate is required unless --next is given")
        current = validate_monotonic(args.candidate, last)
        if args.record:
            record_display_fwver(args.state, current_str(current))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        "display firmware version accepted: "
        f"{'.'.join(map(str, current))} > {'.'.join(map(str, last))}"
        + (" (state file updated)" if args.record else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

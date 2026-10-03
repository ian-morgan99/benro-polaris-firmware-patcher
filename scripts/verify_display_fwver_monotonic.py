#!/usr/bin/env python3
"""Fail-closed validation for the app-visible Polaris firmware version."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){4}$")
STATE_RE = re.compile(r"^last_display_fwver=([^\s`]+)$", re.MULTILINE)


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
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        last = read_last_display_fwver(args.state)
        current = validate_monotonic(args.candidate, last)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        "display firmware version accepted: "
        f"{'.'.join(map(str, current))} > {'.'.join(map(str, last))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

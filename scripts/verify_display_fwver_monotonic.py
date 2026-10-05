#!/usr/bin/env python3
"""Fail-closed validation for the app-visible Polaris firmware version.

The display version is what Benro Connect shows, so two installed builds must
never report the same value. Historically the value was typed by hand into the
release command and the baseline in RELEASE-VERSION-STATE.md was only advanced
manually, which let several candidates carry the same version.

This module can now derive the next version itself:

    --next      print the next permitted version and exit
    --record    claim the validated candidate in the state file

so a release script can stop relying on a human remembering the bump.

Issue #169: a monotonic baseline alone is not enough. The baseline is a single
mutable number, so if it is ever left behind -- as it was when o-v15q was
installed while the baseline still read `.53` -- `--next` re-offers a version
that is already running on hardware. The state file therefore also carries an
append-only registry of every version ever issued:

    consumed_display_fwver=6.0.0.54.53

A version in that registry is refused forever, independently of what
`last_display_fwver` happens to say. The baseline cross-check against the device
stays as a secondary defence, not the primary one.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){4}$")
STATE_RE = re.compile(r"^last_display_fwver=([^\s`]+)$", re.MULTILINE)
CONSUMED_RE = re.compile(
    r"^consumed_display_fwver=([^\s`]+)$", re.MULTILINE
)


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


def read_consumed_display_fwvers(state_path: Path) -> set[tuple[int, ...]]:
    """Return every display version ever issued, from the append-only registry.

    Malformed entries fail closed: a registry that cannot be trusted in full
    cannot be trusted at all, and silently skipping an unreadable line is
    exactly how a version gets handed out twice.
    """
    text = state_path.read_text(encoding="utf-8")
    consumed: set[tuple[int, ...]] = set()
    for raw in CONSUMED_RE.findall(text):
        consumed.add(parse_display_fwver(raw))
    return consumed


def next_display_fwver(
    last: tuple[int, ...], consumed: set[tuple[int, ...]] = frozenset()
) -> tuple[int, ...]:
    """Return the next display version that has never been issued.

    The candidate is taken one above the highest of the baseline and the
    registry, then advanced past any already-consumed value. Deriving from the
    registry as well as the baseline is what makes `--next` safe when the
    baseline has been left behind (#169).
    """
    if len(last) != 5:
        raise ValueError(f"release baseline must have five components, got {last!r}")
    known = [last, *consumed]
    for value in known:
        if len(value) != 5:
            raise ValueError(f"version must have five components, got {value!r}")
        if value[:4] != last[:4]:
            raise ValueError(
                "consumed registry spans more than one firmware family: "
                f"baseline={'.'.join(map(str, last))} entry={'.'.join(map(str, value))}"
            )
    candidate = max(known)
    while True:
        candidate = (*candidate[:4], candidate[4] + 1)
        if candidate not in consumed:
            return candidate


def claim_display_fwver(
    state_path: Path, value: str
) -> tuple[int, ...]:
    """Append a version to the registry so it can never be issued again."""
    current = parse_display_fwver(value)
    text = state_path.read_text(encoding="utf-8")
    if not CONSUMED_RE.search(text) and not STATE_RE.search(text):
        raise ValueError(
            f"state file has no last_display_fwver= entry: {state_path}"
        )
    if current in read_consumed_display_fwvers(state_path):
        raise ValueError(
            f"display firmware version {value} was already issued; the consumed "
            "registry is append-only"
        )
    lines = text.rstrip("\n").split("\n")
    insert_at = None
    for index in range(len(lines) - 1, -1, -1):
        if CONSUMED_RE.match(lines[index]):
            insert_at = index + 1
    if insert_at is None:
        raise ValueError(
            f"state file has no consumed_display_fwver= block to append to: "
            f"{state_path}"
        )
    lines.insert(insert_at, f"consumed_display_fwver={current_str(current)}")
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return current


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


def validate_monotonic(
    candidate: str,
    last: tuple[int, ...],
    consumed: set[tuple[int, ...]] = frozenset(),
) -> tuple[int, ...]:
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
    # The registry is checked separately from the baseline so that a version
    # issued while the baseline was stale is still refused (#169).
    if current in consumed:
        raise ValueError(
            f"display firmware version {candidate} was already issued; it is in "
            "the consumed registry and must never be reused"
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
        help="advance the baseline and append the candidate to the consumed registry",
    )
    args = parser.parse_args()
    try:
        last = read_last_display_fwver(args.state)
        consumed = read_consumed_display_fwvers(args.state)
        if args.next:
            print(current_str(next_display_fwver(last, consumed)))
            return 0
        if not args.candidate:
            parser.error("--candidate is required unless --next is given")
        current = validate_monotonic(args.candidate, last, consumed)
        if args.record:
            record_display_fwver(args.state, current_str(current))
            claim_display_fwver(args.state, current_str(current))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        "display firmware version accepted: "
        f"{'.'.join(map(str, current))} > {'.'.join(map(str, last))}"
        + (
            " (baseline advanced and version claimed in the consumed registry)"
            if args.record
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

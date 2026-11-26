#!/usr/bin/env python3
"""Fail-closed comparison of a candidate and installed Polaris identity."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_PROVENANCE = ("build_id", "patcher_commit", "git_commit", "display_fwver")
FWVER_RE = re.compile(r"(?:^|;)FwVer:([^;\r\n]+)")


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected key=value")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path}:{number}: empty key")
        values[key] = value.strip()
    return values


def read_fwver(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    match = FWVER_RE.search(raw)
    if not match:
        raise ValueError(f"{path}: no FwVer:<version>; field")
    return match.group(1)


def compare(candidate_provenance: Path, device_provenance: Path,
            candidate_fwver: Path, device_fwver: Path,
            candidate_kit_version: Path | None = None,
            device_kit_version: Path | None = None) -> list[str]:
    """Return mismatch/error strings; an empty list means identity matches."""
    errors: list[str] = []
    try:
        expected = read_key_values(candidate_provenance)
    except (OSError, ValueError) as exc:
        return [f"candidate provenance unreadable: {exc}"]
    try:
        actual = read_key_values(device_provenance)
    except (OSError, ValueError) as exc:
        return [f"device provenance unreadable: {exc}"]

    for key in REQUIRED_PROVENANCE:
        if not expected.get(key):
            errors.append(f"candidate missing {key}")
        if not actual.get(key):
            errors.append(f"device missing {key}")
        if expected.get(key) and actual.get(key) and expected[key] != actual[key]:
            errors.append(f"{key}: expected={expected[key]!r} actual={actual[key]!r}")

    try:
        expected_fwver = expected.get("display_fwver", "")
        candidate_fwver_value = read_fwver(candidate_fwver)
        actual_fwver = read_fwver(device_fwver)
    except (OSError, ValueError) as exc:
        errors.append(f"FwVer unreadable: {exc}")
    else:
        if not expected_fwver:
            errors.append("candidate missing display_fwver")
        if expected_fwver != candidate_fwver_value:
            errors.append(
                f"candidate FwVer: provenance={expected_fwver!r} package={candidate_fwver_value!r}"
            )
        if expected_fwver != actual_fwver:
            errors.append(f"display_fwver: expected={expected_fwver!r} actual={actual_fwver!r}")

    # The astro kit is a separate artifact from appfs. A flash deletes /app/astro
    # and its boot hook, so a device can report the correct FwVer while running a
    # kit built for an older candidate -- plate solving then silently uses the old
    # kit's code. Compare build_id whenever the candidate carries a kit; skip only
    # when the candidate genuinely has none (a camera-only release).
    if candidate_kit_version is not None:
        try:
            kit_expected = read_key_values(candidate_kit_version)
        except (OSError, ValueError) as exc:
            errors.append(f"candidate kit VERSION unreadable: {exc}")
        else:
            want_kit_id = kit_expected.get("build_id", "")
            if not want_kit_id:
                errors.append(f"{candidate_kit_version}: missing build_id")
            if device_kit_version is None:
                errors.append(
                    "device kit VERSION missing: the candidate carries an astro kit "
                    "but /app/sd/polaris-astro/VERSION is absent -- install it with "
                    "scripts/release/install-astro-kit.sh"
                )
            else:
                try:
                    kit_actual = read_key_values(device_kit_version)
                except (OSError, ValueError) as exc:
                    errors.append(f"device kit VERSION unreadable: {exc}")
                else:
                    have_kit_id = kit_actual.get("build_id", "")
                    if not have_kit_id:
                        errors.append(f"{device_kit_version}: missing build_id")
                    elif want_kit_id and have_kit_id != want_kit_id:
                        errors.append(
                            f"kit build_id: expected={want_kit_id!r} actual={have_kit_id!r} "
                            "(firmware was flashed but the astro kit was not re-installed)"
                        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-provenance", type=Path, required=True)
    parser.add_argument("--device-provenance", type=Path, required=True)
    parser.add_argument("--candidate-fwver", type=Path, required=True)
    parser.add_argument("--device-fwver", type=Path, required=True)
    parser.add_argument("--candidate-kit-version", type=Path, default=None,
                        help="kit VERSION inside the candidate, if it carries a kit")
    parser.add_argument("--device-kit-version", type=Path, default=None,
                        help="installed /app/sd/polaris-astro/VERSION, if present")
    args = parser.parse_args(argv)

    errors = compare(args.candidate_provenance, args.device_provenance,
                     args.candidate_fwver, args.device_fwver,
                     args.candidate_kit_version, args.device_kit_version)
    if errors:
        print("INSTALLED BUILD IDENTITY: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    candidate = read_key_values(args.candidate_provenance)
    print("INSTALLED BUILD IDENTITY: PASS")
    print(f"  build_id={candidate['build_id']}")
    print(f"  display_fwver={candidate['display_fwver']}")
    if args.candidate_kit_version is not None:
        kit = read_key_values(args.candidate_kit_version)
        print(f"  kit_build_id={kit.get('build_id', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

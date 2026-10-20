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

Uniqueness must hold in both directions, so a version is not enough on its own:

    version  -> commit set   one version describes exactly one build
    commit set -> version    one build is never re-issued under a new number

The second direction is what the consumed registry cannot express, and it is the
one that quietly breaks: rebuilding an unchanged source tree simply to try again
would otherwise mint a fresh version for identical commits, and Benro Connect
would show two different firmware versions for behaviour that cannot differ.
Every version claimed from now on is therefore bound to the exact commit set it
was built from:

    version_commit_binding=6.0.0.54.69|libgphoto2=<sha>|patcher=<sha>

Both directions are refused. Entries recorded before this rule carry no binding
and are treated as historical: they still block their version number, but they
cannot be used to infer a commit set, so an old build re-issued today is not
retroactively rejected on a guess.
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
BINDING_RE = re.compile(
    r"^version_commit_binding=([^|]+)\|libgphoto2=([0-9a-f]{4,40})"
    r"\|patcher=([0-9a-f]{4,40}|unknown)$",
    re.MULTILINE,
)

# A commit set is only comparable once both halves are named. `unknown` is
# allowed on read for records written before the patcher commit was captured,
# but is never accepted as a value to claim.
CommitSet = tuple[str, str]


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


def read_version_commit_bindings(
    state_path: Path,
) -> dict[tuple[int, ...], CommitSet]:
    """Return the recorded version -> commit-set bindings.

    Entries written before bindings existed are absent rather than guessed: an
    unbound historical version still blocks its number, but it must not be used
    to infer what commits it contained. Malformed bindings fail closed, because a
    half-read binding is exactly how one commit set gets a second version.
    """
    text = state_path.read_text(encoding="utf-8")
    bindings: dict[tuple[int, ...], CommitSet] = {}
    for line in text.splitlines():
        if not line.startswith("version_commit_binding="):
            continue
        match = BINDING_RE.fullmatch(line)
        if match is None:
            raise ValueError(
                "malformed version_commit_binding entry, refusing to guess: "
                f"{line}"
            )
        raw_version, libg, patcher = match.groups()
        version = parse_display_fwver(raw_version)
        if version in bindings and bindings[version] != (libg, patcher):
            raise ValueError(
                f"version {raw_version} is bound to more than one commit set; "
                "one version must describe exactly one build"
            )
        bindings[version] = (libg, patcher)
    return bindings


def validate_commit_set(
    candidate: str,
    commit_set: CommitSet,
    bindings: dict[tuple[int, ...], CommitSet],
) -> None:
    """Refuse a claim that would break either direction of uniqueness.

    A version already bound to the same commit set is accepted so that
    re-validating an existing candidate is idempotent; anything else that
    collides is a real conflict and must stop the release.
    """
    version = parse_display_fwver(candidate)
    if any(part == "unknown" for part in commit_set):
        raise ValueError(
            "refusing to bind a version to an unknown commit: both the "
            "libgphoto2 and patcher commits must be known"
        )
    existing = bindings.get(version)
    if existing is not None:
        if existing == commit_set:
            return
        raise ValueError(
            f"version {candidate} is already bound to "
            f"libgphoto2={existing[0]} patcher={existing[1]}; it cannot also "
            "describe a different commit set"
        )
    for bound_version, bound_set in bindings.items():
        if bound_set == commit_set:
            raise ValueError(
                "these commits are already issued as "
                f"{'.'.join(map(str, bound_version))}; a rebuild of an "
                "unchanged source tree must not consume a new version"
            )


def format_binding(value: str, commit_set: CommitSet) -> str:
    return (
        f"version_commit_binding={value}|libgphoto2={commit_set[0]}"
        f"|patcher={commit_set[1]}"
    )


def bind_display_fwver(
    state_path: Path, value: str, commit_set: CommitSet
) -> None:
    """Record which exact commits a claimed version describes.

    Append-only, like the version registry itself. Re-recording the identical
    binding is a no-op so that a retried release step stays safe.
    """
    version = parse_display_fwver(value)
    validate_commit_set(value, commit_set, read_version_commit_bindings(state_path))
    line = format_binding(current_str(version), commit_set)
    text = state_path.read_text(encoding="utf-8")
    if line in text.splitlines():
        return
    lines = text.rstrip("\n").split("\n")
    # Keep bindings together, and keep them after the version registry, so the
    # two blocks stay readable and each still parses with a single regex.
    insert_at = None
    for index in range(len(lines) - 1, -1, -1):
        if BINDING_RE.match(lines[index]):
            insert_at = index + 1
            break
    if insert_at is None:
        for index in range(len(lines) - 1, -1, -1):
            if CONSUMED_RE.match(lines[index]):
                insert_at = index + 1
                break
    if insert_at is None:
        raise ValueError(
            f"state file has no consumed_display_fwver= block to append to: "
            f"{state_path}"
        )
    lines.insert(insert_at, line)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        help="advance the baseline, claim the version, and bind it to its commits",
    )
    parser.add_argument(
        "--libgphoto2-commit",
        help="exact libgphoto2 commit the candidate was built from",
    )
    parser.add_argument(
        "--patcher-commit",
        help="exact patcher commit the candidate was built from",
    )
    args = parser.parse_args()
    try:
        last = read_last_display_fwver(args.state)
        consumed = read_consumed_display_fwvers(args.state)
        bindings = read_version_commit_bindings(args.state)
        if args.next:
            print(current_str(next_display_fwver(last, consumed)))
            return 0
        if not args.candidate:
            parser.error("--candidate is required unless --next is given")
        current = validate_monotonic(args.candidate, last, consumed)
        commit_set: CommitSet | None = None
        if args.libgphoto2_commit or args.patcher_commit:
            if not (args.libgphoto2_commit and args.patcher_commit):
                raise ValueError(
                    "a commit set needs both --libgphoto2-commit and "
                    "--patcher-commit; a partial set cannot prove uniqueness"
                )
            commit_set = (args.libgphoto2_commit, args.patcher_commit)
            validate_commit_set(current_str(current), commit_set, bindings)
        if args.record:
            if commit_set is None:
                raise ValueError(
                    "--record requires the commit set: one version must be bound "
                    "to exactly one set of commits, so a claim cannot be recorded "
                    "without --libgphoto2-commit and --patcher-commit"
                )
            record_display_fwver(args.state, current_str(current))
            claim_display_fwver(args.state, current_str(current))
            bind_display_fwver(args.state, current_str(current), commit_set)
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
        + (
            f" (bound to libgphoto2={commit_set[0]} patcher={commit_set[1]})"
            if commit_set is not None
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

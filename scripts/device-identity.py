#!/usr/bin/env python3
"""Fail-closed identity check for what is actually running on a Polaris head.

Why this exists
---------------
On 2026-11-26 a hot-swap replaced /app/lib/stage2/libpolaris_stage2.so with locally
built bytes while the device continued to report FwVer 6.0.0.54.117. Nothing detected
it, because docs/release-change-summary-v117-astro.json records purpose, changes and
known_limits but no component hashes -- so "v117" was a label with no bytes behind it.
Two consequences followed immediately:

  * A/B results were misattributed. Tests run against the replaced loader were read as
    results for the shipped build, and vice versa; one retracted A/B and one retracted
    capture result came from exactly this.
  * The device was left running an artifact that exists in no release record.

This script makes identity a command with an exit status rather than something inferred
from a version string. It is read-only: it never writes to the device.

Exit codes
----------
  0  every component matches a registered artifact, and matches the release expectation
  1  a component is UNREGISTERED (bytes not in docs/component-identity.json)
  2  a component is registered but does not match the expected release
  3  launcher drift: an env var was added to /app/bin/pgphoto outside the registry
  4  transport failure -- cannot judge identity (never report success on this)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "docs" / "component-identity.json"

# Env vars that change head behaviour and are not part of any package. A diagnostic flag
# left in the launcher silently changes what a build does, which is how a "v117" device
# ended up emitting trace lines. Anything here must be declared in the registry to pass.
LAUNCHER = "/app/bin/pgphoto"


def ssh(host: str, cmd: str, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, cmd],
            capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError as e:
        return 125, str(e)


def md5_local(path: Path) -> str | None:
    try:
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def var_names(text: str) -> list[str]:
    """Normalise 'export STAGE2_FOO' lines to bare names.

    Splitting on whitespace would turn one line into two tokens ('export' and the name),
    which made every declared variable look undeclared.
    """
    out = set()
    for line in text.splitlines():
        tok = line.strip().removeprefix("export").strip()
        if tok.startswith("STAGE2_"):
            out.add(tok)
    return sorted(out)


def lookup(reg: dict, component: str, md5: str | None):
    """Return (label, status, entry) for a hash, or (None, None, None) if unregistered."""
    if not md5:
        return None, None, None
    for art in reg["components"][component]["artifacts"]:
        if art["md5"] == md5:
            return art["label"], art["status"], art
    return None, None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh", default="root@192.168.0.1")
    ap.add_argument("--expect-release", default=None,
                    help="release id to compare against, e.g. 6.0.0.54.117")
    ap.add_argument("--local", metavar="DIR",
                    help="check local build artifacts in DIR instead of the device")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not REGISTRY.exists():
        print(f"FATAL: registry missing: {REGISTRY}", file=sys.stderr)
        return 4
    reg = json.loads(REGISTRY.read_text())
    components = reg["components"]

    release = None
    if args.expect_release:
        release = reg.get("releases", {}).get(args.expect_release)
        if not release:
            print(f"FATAL: release {args.expect_release} is not in the registry",
                  file=sys.stderr)
            return 4

    results, issues = [], []

    def raise_issue(code: int) -> None:
        if code not in issues:
            issues.append(code)

    if args.local:
        d = Path(args.local)
        for name, spec in components.items():
            cand = next((p for p in d.iterdir() if p.name == name or
                         p.stem.startswith(name.replace(".so", ""))), None)
            got = md5_local(cand) if cand else None
            label, status, _ = lookup(reg, name, got)
            results.append({"component": name, "source": str(cand), "md5": got,
                            "label": label, "status": status})
            if got and not label:
                raise_issue(1)
    else:
        # One ssh round trip for all hashes; the head is slow and flaky on battery.
        paths = " ".join(spec["path"] for spec in components.values())
        code, out = ssh(args.ssh, f"md5sum {paths} 2>/dev/null", timeout=60)
        if code != 0 and not out:
            print(f"FATAL: cannot reach {args.ssh} (rc={code}) -- identity UNKNOWN, "
                  "not assumed correct", file=sys.stderr)
            return 4
        got_by_path = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                got_by_path[parts[1]] = parts[0]

        for name, spec in components.items():
            got = got_by_path.get(spec["path"])
            label, status, _ = lookup(reg, name, got)
            expected = (release or {}).get("expected", {}).get(name)
            results.append({"component": name, "md5": got, "label": label,
                            "status": status, "expected": expected})
            if not got:
                raise_issue(4)
            elif not label:
                raise_issue(1)
            elif expected and got != expected:
                raise_issue(2)

        # Launcher drift: a diagnostic env var left in the launcher changes behaviour of
        # an otherwise-registered binary, so it is part of identity.
        code, out = ssh(args.ssh, f"grep -oE 'export STAGE2_[A-Z_]+' {LAUNCHER} "
                                  "2>/dev/null", timeout=30)
        found = var_names(out)
        declared = var_names("\n".join(reg.get("launcher_env_declared", [])))
        undeclared = [v for v in found if v not in declared]
        results.append({"component": "launcher-env", "found": found,
                        "declared": declared, "undeclared": undeclared})
        if undeclared:
            raise_issue(3)

    # Severity, not numeric order: a wrong or unregistered binary outranks an env-var
    # difference, and "could not tell" outranks everything because it must never be read
    # as healthy.
    priority = [4, 1, 2, 3]
    rc = 0 if not issues else next(c for c in priority if c in issues)

    if args.json:
        print(json.dumps({"results": results, "issues": issues, "exit": rc}, indent=2))
    else:
        print(f"component identity (registry: {REGISTRY.name})")
        for r in results:
            if r["component"] == "launcher-env":
                mark = "OK" if not r["undeclared"] else "DRIFT"
                print(f"  {mark:5} launcher env: undeclared={r['undeclared'] or '[]'}")
                continue
            label = r.get("label") or "UNREGISTERED"
            status = r.get("status") or "-"
            line = f"  {r['component']:26} {r.get('md5') or 'MISSING'}  {label} [{status}]"
            if r.get("expected"):
                line += "" if r["md5"] == r["expected"] else \
                    f"  EXPECTED {r['expected']}"
            print(line)

    verdicts = {0: "IDENTITY VERIFIED", 1: "UNREGISTERED ARTIFACT -- bytes match no "
                "recorded build; this is how a modified head masquerades as a release",
                2: "WRONG BUILD FOR THIS RELEASE -- registered, but not the expected one",
                3: "LAUNCHER DRIFT -- env var present that no release declares",
                4: "UNKNOWN -- could not read the device; do not treat as healthy"}
    print(f"\nVERDICT: {verdicts[rc]} (exit {rc})")
    return rc


if __name__ == "__main__":
    sys.exit(main())

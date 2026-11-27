#!/usr/bin/env python3
"""Look up every authoritative source that mentions a symbol, opcode or feature.

Why this exists: on 2026-11-27 an agent concluded that K-1 II autofocus was
"vendor polestar_app code, not ours to patch -- report upstream" and recorded
that in docs/evidence/k1ii-overnight-20261126/HANDOFF.md. It is wrong. The
Ghidra decompilation of pgphoto is in this workspace, and its
updateCameraAutoFocus() is a plain libgphoto2 widget call: _find_widget_by_name
then gp_camera_set_config(). The widget it names is one our own camlib owns.
The conclusion was reached by grepping our two repos and stopping when nothing
matched, instead of searching the vendor sources that were already on disk.

The same class of error recurs constantly in this project's own findings files:
inferring a mechanism from a log line without reading the code that printed it.
This script does not decide ownership -- it makes the evidence visible so a
"not ours" claim has to be made against it rather than in its absence.

Sources are searched by default under $POLARIS_RESEARCH_ROOT, which defaults to
the parent of this repo (~/Documents/VSCodeProjects). Missing roots are reported
as MISSING, never silently skipped: a silent skip is how the pgphoto
decompilation stayed invisible for weeks.

Usage:
  scripts/find-authoritative-source.py updateCameraAutoFocus
  scripts/find-authoritative-source.py --opcode 262
  scripts/find-authoritative-source.py --feature autofocus --context
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def research_root() -> Path:
    env = os.environ.get("POLARIS_RESEARCH_ROOT")
    return Path(env).expanduser() if env else REPO.parent


# (key, label, relative-to-research-root, must-exist)
# must-exist True means a missing path is a real problem worth shouting about:
# these are the sources that have repeatedly been assumed absent when present.
SOURCES: list[tuple[str, str, str, bool]] = [
    ("pgphoto", "pgphoto Ghidra decompilation (vendor ARM code)",
     "pr-publish/pgphoto-re/decompiled", True),
    ("pgphoto-md", "pgphoto ANALYSIS.md",
     "pr-publish/pgphoto-re/ANALYSIS.md", False),
    ("it2-device", "Image Transmitter 2 MtpDevice.cs (vendor protocol)",
     "LibGphoto2/ImageTransmitter2/IMAGETransmitter2/MtpDevice.cs", True),
    ("it2-ui", "Image Transmitter 2 MainWindow.xaml.cs (vendor UI gating)",
     "LibGphoto2/ImageTransmitter2/IMAGETransmitter2/MainWindow.xaml.cs", False),
    ("benro-connect", "Benro Connect decompiled APK",
     "PrivateResearch/openpolaris-research/Benro-Connect/benro-connect-decompiled",
     True),
    ("our-driver", "our libgphoto2 fork (camlib source)",
     "LibGphoto2/libgphoto2/camlibs/ptp2", True),
    ("our-webui", "our Astro Web UI / httpd opcodes",
     "BenroPolarisPatcher/container/astro", False),
    ("our-loader", "our Stage-2 loader",
     "BenroPolarisPatcher/container/stage2_loader.c", False),
]

# Vendor code is Ghidra output or decompiled C#: names are real, statement text
# is reconstructed. Say so on every hit so it is never quoted as upstream source.
CAVEAT = ("vendor hits are Ghidra/decompiler OUTPUT -- reference for behaviour, "
          "never the upstream file")


def _grep(term: str, target: Path, context: int) -> list[str]:
    if not target.exists():
        return []
    # -F is not cosmetic. With regex on, "code[262]" is a character class and
    # matches getPostCode2() in the Benro Connect smali, so an opcode lookup
    # reported five vendor hits that had nothing to do with opcode 262 -- the
    # exact kind of confident-but-wrong evidence this script exists to remove.
    cmd = ["grep", "-rn", "-i", "-I", "-F", "--exclude-dir=build",
           "--exclude-dir=.git", term, str(target)]
    if context:
        cmd.insert(1, f"-{context}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def _short(path: str, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root.parent))
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("term", nargs="?", help="symbol or string to search")
    ap.add_argument("--opcode", help="IPC opcode, e.g. 262")
    ap.add_argument("--feature", help="feature name, e.g. autofocus")
    ap.add_argument("--context", action="store_true",
                    help="show surrounding lines at each hit")
    ap.add_argument("--root", default=None,
                    help="override the research root directory")
    args = ap.parse_args(argv)

    terms = [t for t in (args.term, args.feature) if t]
    if args.opcode:
        terms += [f"code[{args.opcode}]", f"code:{args.opcode}",
                  f"cmd={args.opcode}", f"{{ {args.opcode},"]
    if not terms:
        ap.error("give a term, --feature, or --opcode")

    root = Path(args.root).expanduser() if args.root else research_root()
    print(f"research root: {root}")
    print(f"terms: {', '.join(terms)}\n")

    present = missing = 0
    vendor_hits = 0
    for key, label, rel, must in SOURCES:
        target = root / rel
        if not target.exists():
            # A must-exist source that is gone is the failure this script exists
            # to prevent, so it is reported loudly rather than as a shrug.
            flag = "MISSING (expected present)" if must else "absent"
            print(f"[{key:13}] {flag} -- {target}")
            missing += 1
            continue
        hits: list[str] = []
        for t in terms:
            hits.extend(_grep(t, target, 2 if args.context else 0))
        uniq = sorted(set(hits))
        if not uniq:
            print(f"[{key:13}] no match ({label})")
            continue
        present += 1
        if key in ("pgphoto", "it2-device", "it2-ui", "benro-connect"):
            vendor_hits += len(uniq)
        print(f"[{key:13}] {len(uniq)} hit(s) -- {label}")
        for ln in uniq[:12]:
            path, _, rest = ln.partition(":")
            print(f"    {_short(path, root)}:{rest}")
        if len(uniq) > 12:
            print(f"    ... {len(uniq) - 12} more")
        print()

    print("=" * 60)
    if vendor_hits:
        print(f"VENDOR SOURCE HITS: {vendor_hits}")
        print(f"  NOTE: {CAVEAT}")
    if present == 0:
        print("NO SOURCE MATCHED. Before concluding a defect is not ours:")
        print("  1. confirm the terms above are the right ones (a vendor name")
        print("     may differ from ours -- e.g. pgphoto calls our 'autofocus'")
        print("     widget via updateCameraAutoFocus)")
        print("  2. confirm the roots above are not MISSING")
        print("  3. only then route it upstream, citing this output")
    return 0


if __name__ == "__main__":
    sys.exit(main())

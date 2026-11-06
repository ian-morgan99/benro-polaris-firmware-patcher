#!/usr/bin/env python3
"""Generate the immutable, candidate-specific install manifest for a staged FwPkt.

The manifest is the single source of truth for post-reboot installed-binary
verification (issue #199 review finding 1): a version string alone is not
sufficient; every mandatory installed executable/library must be read back
after reboot and its full SHA-256 compared against this manifest.

Layout: <candidate-dir>/FwPkt/  (the unpacked FwPkt tree)
        <candidate-dir>/FwPkt.zip
        <candidate-dir>/install-manifest.json   <- written here

Mandatory installed files are the ones the patcher places into appfs and that
the running firmware depends on:

  /app/FwVer
  /app/bin/polestar_app
  /app/lib/stage2/pgphoto.stage2ondisk
  /app/lib/stage2/libpolaris_stage2.so
  /app/lib/stage2/libgphoto2.so.6
  /app/lib/stage2/libgphoto2_port.so.12
  /app/lib/stage2/libgphoto2/2.5.34/ptp2.so
  /app/lib/stage2/libgphoto2/2.5.34/pentax.so
  /app/lib/stage2/libgphoto2_port/0.12.2/usb1.so
  /app/lib/stage2/libgphoto2_port/0.12.2/usbscsi.so (K-5 II profile only)
  /app/openpolaris-libgphoto2-provenance.txt

The stage2ondisk predicate (issue #199 review finding 4): the manifest records
whether appfs contains a lib/stage2 tree at all. If it does, every file listed
above is MANDATORY and a missing file must fail verification; if appfs has no
lib/stage2 tree, the stage2 entries are recorded as non-mandatory (predicate
`stage2_mandatory=false`) so a SKIP is machine-checkable rather than silent.

Usage:
  python3 scripts/generate-fwpkt-manifest.py out/staged/<candidate> \
      [--ubireader /work/bin/ubireader_extract_files]

Exit codes: 0 = manifest written, 1 = input error, 2 = appfs extraction failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Device path -> appfs-relative path (appfs root == /app on the device).
MANDATORY_FILES = [
    ("FwVer", "FwVer"),
    ("bin/polestar_app", "bin/polestar_app"),
    ("lib/stage2/pgphoto.stage2ondisk", "lib/stage2/pgphoto.stage2ondisk"),
    ("lib/stage2/libpolaris_stage2.so", "lib/stage2/libpolaris_stage2.so"),
    ("lib/stage2/libgphoto2.so.6", "lib/stage2/libgphoto2.so.6"),
    ("lib/stage2/libgphoto2_port.so.12", "lib/stage2/libgphoto2_port.so.12"),
    ("lib/stage2/libgphoto2/2.5.34/ptp2.so", "lib/stage2/libgphoto2/2.5.34/ptp2.so"),
    ("lib/stage2/libgphoto2/2.5.34/pentax.so", "lib/stage2/libgphoto2/2.5.34/pentax.so"),
    ("lib/stage2/libgphoto2_port/0.12.2/usb1.so", "lib/stage2/libgphoto2_port/0.12.2/usb1.so"),
    ("openpolaris-libgphoto2-provenance.txt", "openpolaris-libgphoto2-provenance.txt"),
]
LEGACY_USB_SCSI_FILE = (
    "lib/stage2/libgphoto2_port/0.12.2/usbscsi.so",
    "lib/stage2/libgphoto2_port/0.12.2/usbscsi.so",
)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Returns (usable_binary_or_None, notes). The notes explain every candidate that
# was considered and rejected, because "no functional ubireader" on its own is a
# misleading diagnosis: on 2026-11-06 a wrapper WAS present at
# ~/.local/bin/ubireader_extract_files but died at import time (its module had
# been installed for a different interpreter). The probe below correctly rejects
# it -- --help must EXIT 0, not merely run -- but the old error said nothing about
# where it had looked or why the thing it found was unusable, so the operator had
# no way to tell "not installed" from "installed and broken".
def resolve_ubireader(explicit: str | None) -> tuple[str | None, list[str]]:
    if explicit:
        if not os.path.exists(explicit):
            return None, [f"--ubireader path does not exist: {explicit}"]
        return explicit, []

    notes: list[str] = []
    candidates = [
        shutil.which("ubireader_extract_files"),
        "/work/bin/ubireader_extract_files",
    ]
    seen = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        # A wrapper on PATH can be broken (module installed for another
        # interpreter); probe it the same way the pre-release gate does -- which
        # means requiring --help to EXIT 0, not merely to run. The probe used to
        # swallow the exit code, so a wrapper that crashed at import time was
        # still returned and extraction then failed with "no functional
        # ubireader" even though a working one sat at /work/bin.
        try:
            proc = subprocess.run(
                [cand, "--help"], capture_output=True, timeout=30, text=True,
            )
        except Exception as exc:
            notes.append(f"{cand}: could not be executed ({exc})")
            continue
        if proc.returncode == 0:
            return cand, notes
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(detail[-2:]) if detail else "no output"
        notes.append(
            f"{cand}: present but NOT functional (--help exited "
            f"{proc.returncode}: {tail[:200]})"
        )
    if not seen:
        notes.append(
            "nothing found on PATH or at /work/bin/ubireader_extract_files"
        )
    return None, notes


def extract_appfs(appfs_path: str, ubireader: str | None) -> tuple[str | None, str]:
    """Extract appfs.ubifs; return (extracted root dir or None, explanation).

    The explanation is non-empty only on failure and carries the tool's own error
    text. A silent None here previously became "no functional ubireader" even when
    ubireader ran and failed for an entirely different reason -- most commonly an
    output directory the Docker daemon could not see, which is a TMPDIR problem,
    not a ubireader problem.
    """
    if not ubireader:
        return None, "no functional ubireader_extract_files was found"
    tmp = tempfile.mkdtemp(prefix="fwpkt-manifest-")
    try:
        proc = subprocess.run(
            [ubireader, "-o", tmp, appfs_path],
            check=True, capture_output=True, timeout=600, text=True,
        )
        # ubireader nests under <tmp>/<inode>/ubifs/
        for root, _dirs, _files in os.walk(tmp):
            if os.path.basename(root) == "ubifs" and os.path.isdir(os.path.join(root, "lib")):
                return root, ""
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(detail[-2:]) if detail else "no output"
        shutil.rmtree(tmp, ignore_errors=True)
        return None, (
            f"{ubireader} ran but produced no ubifs/ directory containing lib/ "
            f"under {tmp} (TMPDIR={os.environ.get('TMPDIR', 'unset')}). {tail[:200]}"
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        tail = " | ".join(detail[-3:]) if detail else "no output"
        return None, f"{ubireader} exited {exc.returncode}: {tail[:300]}"
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, f"could not run {ubireader}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidate_dir", help="directory containing FwPkt/ and FwPkt.zip")
    ap.add_argument("--ubireader", default=None, help="path to a functional ubireader_extract_files")
    args = ap.parse_args()

    cand = os.path.abspath(args.candidate_dir)
    fwpkt = os.path.join(cand, "FwPkt")
    zip_path = os.path.join(cand, "FwPkt.zip")
    appfs = os.path.join(fwpkt, "camera", "appfs.ubifs")
    if not os.path.isdir(fwpkt):
        print(f"ERROR: {fwpkt} not found", file=sys.stderr)
        return 1
    if not os.path.isfile(zip_path):
        print(f"ERROR: {zip_path} not found", file=sys.stderr)
        return 1

    ubireader, ubi_notes = resolve_ubireader(args.ubireader)
    if os.path.isfile(appfs):
        appfs_root, extract_note = extract_appfs(appfs, ubireader)
    else:
        appfs_root, extract_note = None, f"{appfs} does not exist in the candidate"
    if appfs_root is None:
        print("ERROR: could not extract appfs.ubifs", file=sys.stderr)
        for note in ([extract_note] if extract_note else []) + ubi_notes:
            if note:
                print(f"       {note}", file=sys.stderr)
        print(
            "       A working ubireader ships inside the patcher image; use the\n"
            "       committed bridge, which runs it there against host paths:\n"
            "         export UBIREADER_EXTRACT_FILES=<repo>/tools/ubireader-docker\n"
            "       If the failure mentions the output directory, TMPDIR points at a\n"
            "       path the Docker daemon cannot see (a sandbox-private /tmp). Set\n"
            "       TMPDIR under $HOME and retry. Run scripts/build-doctor.sh to check\n"
            "       every build prerequisite at once.",
            file=sys.stderr,
        )
        return 2

    # Machine-checkable stage2 predicate: does this candidate ship a lib/stage2 tree?
    stage2_mandatory = os.path.isdir(os.path.join(appfs_root, "lib", "stage2"))

    manifest_files = list(MANDATORY_FILES)
    legacy_usbscsi = os.path.join(appfs_root, LEGACY_USB_SCSI_FILE[1])
    if os.path.isfile(legacy_usbscsi):
        manifest_files.append(LEGACY_USB_SCSI_FILE)

    files = []
    missing = []
    for device_rel, appfs_rel in manifest_files:
        src = os.path.join(appfs_root, appfs_rel)
        if not os.path.isfile(src):
            missing.append(device_rel)
            continue
        files.append({
            "path": f"/app/{device_rel}",
            "sha256": sha256_file(src),
            "size": os.path.getsize(src),
        })

    if stage2_mandatory:
        absent_stage2 = [m for m in missing if "/lib/stage2/" in m]
        if absent_stage2:
            print(f"ERROR: lib/stage2 present but mandatory files missing: {absent_stage2}", file=sys.stderr)
            return 1

    fwver_path = os.path.join(appfs_root, "FwVer")
    fwver_content = ""
    if os.path.isfile(fwver_path):
        with open(fwver_path, "r", encoding="utf-8", errors="replace") as f:
            fwver_content = f.read().strip()

    manifest = {
        "schema": 1,
        "candidate": os.path.basename(cand),
        "zip": {"sha256": sha256_file(zip_path), "size": os.path.getsize(zip_path)},
        "fwver_content": fwver_content,
        "stage2_mandatory": stage2_mandatory,
        "files": files,
    }
    out = os.path.join(cand, "install-manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"wrote {out} ({len(files)} mandatory files, stage2_mandatory={stage2_mandatory})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

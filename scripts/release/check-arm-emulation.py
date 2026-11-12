#!/usr/bin/env python3
"""Execute the candidate's Stage-2 binary under the harness ARM emulator.

This is the pre-deploy execution check requested in patcher issue #340. It runs
the candidate's own pgphoto.stage2ondisk under Unicorn via the harness dynamic
loader and asserts only what an emulator can honestly prove:

  * the bytes we executed are the bytes the install manifest promises to install;
  * every dynamic relocation resolves (an ABI or camlib mismatch surfaces here);
  * the entry point executes a bounded instruction budget without a memory fault,
    an unsupported instruction, or an unexpected syscall.

It deliberately does NOT assert anything about:

  * shutter closure -- gp_camera_exit/gp_port_close is libgphoto2 teardown, not
    the Bulb stop; stopCaptureImageForMessage is that path and is not reached;
  * PTP or physical camera behaviour (the harness is not a Pentax/PTP emulator);
  * the on-boot upgrade watcher, appfs/rootfs image contents, or Wi-Fi.

Those exclusions are printed on every run and written into the record, because a
green execution check has historically been over-read as device qualification.
The harness states the rule this script enforces: "No firmware candidate should
be treated as qualified merely because emulator tests pass."

Exit codes (mirrors the gate's ok/bad/skp contract):
  0  all load-class assertions held
  2  invalid arguments / unreadable manifest
  3  an assertion was contradicted by the artifact (fail closed)
  4  reserved: every evaluated assertion held but some could not be evaluated
  5  prerequisite unavailable (unicorn or harness source missing)

Exit 5 is reported as a SKIP by the gate, never as a pass. Reporting OK for a
check that never ran is the failure mode R4 was written to prevent.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

MANIFEST_PATH = "/app/lib/stage2/pgphoto.stage2ondisk"
DEFAULT_INSTRUCTION_BUDGET = 100000

# What this check cannot see. Printed and recorded so a green result is never
# mistaken for device qualification.
EXCLUSIONS = [
    "shutter closure (gp_camera_exit/gp_port_close is libgphoto2 teardown, not "
    "the Bulb stop; stopCaptureImageForMessage is that path)",
    "PTP protocol and physical camera behaviour (not a Pentax/PTP emulator)",
    "on-boot firmware upgrade watcher (SP_UpgradeCheckFw) and reboot behaviour",
    "appfs/rootfs image contents and UBIFS layout",
    "Wi-Fi/AP behaviour, auto-join, and the 60s wifi-auto-off timer",
    "astro kit install, boot hook, and plate solver",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_rev(cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=20,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def find_candidate_binary(build_dir: Path) -> Path:
    """Locate the candidate's Stage-2 binary.

    The tree layout has moved before (stage2-ondisk/ vs stage2-ondisk/ondisk/),
    so search rather than hardcoding one path -- but accept exactly one match and
    fail closed on ambiguity, because testing the wrong binary is worse than not
    testing at all.
    """
    hits = sorted(p for p in build_dir.rglob("pgphoto.stage2ondisk") if p.is_file())
    if not hits:
        raise FileNotFoundError(
            "no pgphoto.stage2ondisk under %s" % build_dir)
    if len(hits) > 1:
        # Prefer the ondisk/ copy, which is what the installer stages, but say so.
        preferred = [p for p in hits if p.parent.name == "ondisk"]
        if len(preferred) != 1:
            raise RuntimeError(
                "ambiguous candidate Stage-2 binary (%d copies found): %s"
                % (len(hits), ", ".join(str(p) for p in hits)))
        return preferred[0]
    return hits[0]


def manifest_expectation(manifest_path: Path) -> dict:
    data = json.loads(manifest_path.read_text())
    for entry in data.get("files", []):
        if entry.get("path") == MANIFEST_PATH:
            return {"sha256": entry.get("sha256"), "size": entry.get("size")}
    raise KeyError("%s not listed in %s" % (MANIFEST_PATH, manifest_path))


def elf_segment_coverage(path: Path) -> list:
    """Return PT_LOAD segments whose declared data exceeds the file size.

    The loader zero-fills anything past the end of the file instead of erroring,
    and 0x00000000 is a valid ARM instruction (andeq r0,r0,r0). A truncated
    binary therefore executes its whole instruction budget harmlessly and reports
    result=pass. Verified against v107: truncating pgphoto.stage2ondisk to 8 KiB
    produced "pass" with 100000 instructions executed and 0 relocations resolved.

    So the loader's own verdict is not sufficient evidence that the artifact is
    intact, and this check must validate structure independently rather than
    trusting it.
    """
    data = path.read_bytes()
    size = len(data)
    if size < 52:
        return [{"error": "file smaller than an ELF32 header (%d bytes)" % size}]
    if data[:4] != b"\x7fELF":
        return [{"error": "not an ELF file"}]
    if data[4] != 1:
        return [{"error": "not ELFCLASS32 (this device is ARM32)"}]

    import struct
    e_shoff, = struct.unpack_from("<I", data, 0x20)
    e_phoff, = struct.unpack_from("<I", data, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x2A)
    if e_phnum == 0 or e_phoff + e_phnum * e_phentsize > size:
        return [{"error": "program header table runs past end of file"}]

    bad = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_offset, p_vaddr, _p_p, _p_f, p_filesz, _p_m = \
            struct.unpack_from("<IIIIIII", data, off)[:7]
        if p_type != 1:  # PT_LOAD
            continue
        if p_offset + p_filesz > size:
            bad.append({
                "segment": i, "vaddr": hex(p_vaddr),
                "declared_filesz": hex(p_filesz), "offset": hex(p_offset),
                "file_size": size,
                "missing_bytes": p_offset + p_filesz - size,
            })
    if e_shoff and e_shoff < size:
        pass  # section headers are optional for execution; not a failure
    return bad


def import_loader(harness_src: Path):
    sys.path.insert(0, str(harness_src))
    from polaris_harness.arm_emulator.dynamic_loader import DynamicLoader  # noqa
    return DynamicLoader


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", required=True, help="candidate build directory")
    ap.add_argument("--manifest", help="install-manifest.json (default: <build>/)")
    ap.add_argument("--harness-src", default=os.environ.get("POLARIS_HARNESS_SRC"),
                    help="path to harness src/ (env POLARIS_HARNESS_SRC)")
    ap.add_argument("--instruction-budget", type=int,
                    default=DEFAULT_INSTRUCTION_BUDGET)
    ap.add_argument("--output", help="write the machine-readable record here")
    args = ap.parse_args()

    build_dir = Path(args.build).resolve()
    if not build_dir.is_dir():
        print("ERROR: build directory not found: %s" % build_dir, file=sys.stderr)
        return 2

    manifest_path = Path(args.manifest) if args.manifest \
        else build_dir / "install-manifest.json"
    if not manifest_path.is_file():
        print("ERROR: manifest not found: %s" % manifest_path, file=sys.stderr)
        return 2

    # Prerequisites. Absent is a SKIP (exit 5), never a silent pass.
    try:
        import unicorn  # noqa: F401
    except Exception as exc:
        print("PREREQ: unicorn unavailable (%s)" % exc)
        return 5

    if not args.harness_src:
        print("PREREQ: no harness src given (--harness-src or POLARIS_HARNESS_SRC)")
        return 5
    harness_src = Path(args.harness_src).resolve()
    if not (harness_src / "polaris_harness" / "arm_emulator" / "dynamic_loader.py").is_file():
        print("PREREQ: harness dynamic loader not found under %s" % harness_src)
        return 5

    try:
        binary = find_candidate_binary(build_dir)
    except Exception as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    try:
        want = manifest_expectation(manifest_path)
    except Exception as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    got_sha = sha256(binary)
    record = {
        "check": "arm-emulation-stage2",
        "binary_path": str(binary),
        "binary_sha256": got_sha,
        "binary_size": binary.stat().st_size,
        "manifest_expected_sha256": want.get("sha256"),
        "manifest_expected_size": want.get("size"),
        "instruction_budget": args.instruction_budget,
        "patcher_commit": git_rev(Path(__file__).resolve().parents[2]),
        "harness_revision": git_rev(harness_src.parent),
        "exclusions": EXCLUSIONS,
    }

    # Identity first: executing bytes that are not the bytes we will install would
    # make every downstream assertion meaningless.
    if want.get("sha256") and got_sha != want["sha256"]:
        record["result"] = "fail"
        record["reason"] = ("candidate Stage-2 binary does not match the install "
                            "manifest (got %s, expected %s)"
                            % (got_sha, want["sha256"]))
        _emit(record, args.output)
        print("FAIL: %s" % record["reason"], file=sys.stderr)
        return 3

    # Structure before execution. The loader zero-fills past EOF and 0x00000000 is
    # a valid ARM instruction, so a truncated binary can "pass" while executing
    # nothing real. Catch that here rather than trusting the loader's verdict.
    bad_segments = elf_segment_coverage(binary)
    record["elf_segment_defects"] = bad_segments
    if bad_segments:
        record["result"] = "fail"
        record["reason"] = ("ELF PT_LOAD segment(s) declare more data than the "
                            "file contains; the loader would zero-fill them and "
                            "report a spurious pass: %s"
                            % json.dumps(bad_segments))
        _emit(record, args.output)
        for b in bad_segments:
            if "error" in b:
                print("FAIL: ELF defect: %s" % b["error"], file=sys.stderr)
            else:
                print("FAIL: ELF segment %d at vaddr %s declares filesz %s but the "
                      "file is only %d bytes (%d bytes missing)"
                      % (b["segment"], b["vaddr"], b["declared_filesz"],
                         b["file_size"], b["missing_bytes"]), file=sys.stderr)
        return 3

    DynamicLoader = import_loader(harness_src)
    try:
        loader = DynamicLoader(binary, max_instructions=args.instruction_budget)
        rec = loader.run()
    except Exception as exc:
        record["result"] = "error"
        record["reason"] = "loader raised %s: %s" % (type(exc).__name__, exc)
        _emit(record, args.output)
        print("FAIL: %s" % record["reason"], file=sys.stderr)
        return 3

    record.update({
        "entry_address": hex(rec.entry_address),
        "result": rec.result,
        "instructions_executed": rec.instructions_executed,
        "relocations_resolved": rec.relocations_resolved,
        "relocations_unresolved": rec.relocations_unresolved,
        "stub_calls": len(rec.stub_calls),
        "unresolved_symbol": rec.unresolved_symbol,
        "missing_library": rec.missing_library,
        "unsupported_relocation_offset": rec.unsupported_relocation_offset,
        "error_message": rec.error_message,
        "duration_ms": rec.duration_ms,
    })

    failures = []
    if rec.result != "pass":
        failures.append("loader result is %r, not 'pass'" % rec.result)
    if rec.relocations_unresolved:
        failures.append("%d dynamic relocation(s) unresolved%s"
                        % (rec.relocations_unresolved,
                           " (%s)" % rec.unresolved_symbol if rec.unresolved_symbol else ""))
    if rec.missing_library:
        failures.append("missing library: %s" % rec.missing_library)
    if rec.instructions_executed <= 0:
        failures.append("no instructions executed")
    # A real pgphoto.stage2ondisk resolves hundreds of relocations. Zero means the
    # dynamic section was never read -- which is what a truncated or stripped
    # artifact looks like. Asserting only "unresolved == 0" would accept that,
    # because zero unresolved out of zero total is vacuously true.
    if rec.relocations_resolved <= 0:
        failures.append("no dynamic relocations resolved at all; the binary is "
                        "stripped, truncated, or was not loaded as a dynamic ELF "
                        "(a real pgphoto.stage2ondisk resolves hundreds)")

    record["assertions_failed"] = failures
    _emit(record, args.output)

    print("binary sha256      : %s (matches install-manifest.json)" % got_sha[:16])
    print("entry address      : %s" % hex(rec.entry_address))
    print("loader result      : %s" % rec.result)
    print("instructions       : %d of %d budget"
          % (rec.instructions_executed, args.instruction_budget))
    print("relocations        : %d resolved / %d unresolved"
          % (rec.relocations_resolved, rec.relocations_unresolved))
    print("stub calls         : %d" % len(rec.stub_calls))

    if failures:
        for f in failures:
            print("FAIL: %s" % f, file=sys.stderr)
        return 3

    print("NOTE: this proves load, relocation and bounded execution only. It does "
          "NOT qualify the candidate.")
    print("      Not covered by this check:")
    for e in EXCLUSIONS:
        print("        - %s" % e)
    print("      Supervised physical K-1 II / K-3 III testing remains required.")
    return 0


def _emit(record: dict, output) -> None:
    if output:
        Path(output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail-closed identity check for a Polaris FwPkt candidate.

This is deliberately separate from the device installer. It proves that the
directory being handed to the installer is one coherent candidate: provenance,
FwVer, ZIP bytes, and install manifest agree. A smoke directory may be checked
without an install manifest, but ``--require-deployable`` is mandatory before
staging or publishing a release candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){4}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PROVENANCE = (
    "source_kind",
    "actual_version",
    "git_commit",
    "dirty_diff_hash",
    "patcher_commit",
    "patcher_dirty_diff_hash",
    "selected_camlibs",
    "build_id",
    "display_fwver",
    "candidate_id",
    "release_change_manifest",
    "release_change_manifest_sha256",
)

REQUIRED_PAYLOAD = (
    "camera/config",
    "camera/uImage",
    "camera/rootfs.ubifs",
    "camera/appfs.ubifs",
    "gimbal/polaris403_2.0.0.22.bin",
    "gimbal/polaris413_2.0.0.22.bin",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_provenance(path: Path, errors: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if key in values:
            errors.append(f"duplicate provenance key: {key} (line {number})")
        values[key] = value
    for key in REQUIRED_PROVENANCE:
        if key not in values:
            errors.append(f"provenance missing required key: {key}")
    return values


def validate_release_change_manifest(
    candidate_dir: Path,
    provenance: dict[str, str],
    zip_path: Path,
    errors: list[str],
) -> None:
    """Prove that the human change record belongs to this exact candidate."""
    declared_name = provenance.get("release_change_manifest", "")
    if declared_name != "release-change-manifest.json":
        errors.append(
            "release_change_manifest must be exactly release-change-manifest.json"
        )
        return
    manifest_path = candidate_dir / declared_name
    if not manifest_path.is_file():
        errors.append(f"release change manifest missing: {manifest_path}")
        return
    actual_hash = sha256_file(manifest_path)
    if actual_hash != provenance.get("release_change_manifest_sha256"):
        errors.append(
            "release change manifest SHA-256 mismatch: "
            f"provenance={provenance.get('release_change_manifest_sha256')!r} "
            f"actual={actual_hash}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"release-change-manifest.json is unreadable: {exc}")
        return
    if not isinstance(manifest, dict):
        errors.append("release-change-manifest.json root is not an object")
        return
    if manifest.get("schema") != 1:
        errors.append("release-change-manifest.json schema is not 1")
    expected = {
        "candidate_id": candidate_dir.name,
        "display_fwver": provenance.get("display_fwver", ""),
        "build_id": provenance.get("build_id", ""),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(
                f"release change manifest {key} mismatch: "
                f"expected={value!r} actual={manifest.get(key)!r}"
            )
    source = manifest.get("source")
    patcher = manifest.get("patcher")
    for label, record, expected_sha in (
        ("source", source, provenance.get("git_commit")),
        ("patcher", patcher, provenance.get("patcher_commit")),
    ):
        if not isinstance(record, dict):
            errors.append(f"release change manifest has no {label} object")
            continue
        if record.get("head_commit") != expected_sha:
            errors.append(
                f"release change manifest {label}.head_commit does not match provenance"
            )
        commits = record.get("commits_since_baseline")
        if not isinstance(commits, list):
            errors.append(f"release change manifest {label}.commits_since_baseline is not a list")
        else:
            for number, commit in enumerate(commits, 1):
                if not isinstance(commit, dict) or not COMMIT_RE.fullmatch(str(commit.get("sha", ""))):
                    errors.append(f"release change manifest {label} commit {number} has no full SHA")
    if not isinstance(manifest.get("purpose"), str) or not manifest["purpose"].strip():
        errors.append("release change manifest purpose is empty")
    if not isinstance(manifest.get("declared_changes"), list) or not manifest["declared_changes"]:
        errors.append("release change manifest has no declared changes")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        errors.append("release change manifest has no artifact object")
    else:
        actual_zip_sha = sha256_file(zip_path)
        if artifact.get("fwpkt_zip_sha256") != actual_zip_sha:
            errors.append("release change manifest ZIP SHA-256 does not match candidate ZIP")
        if artifact.get("fwpkt_zip_md5") != hashlib.md5(zip_path.read_bytes()).hexdigest():
            errors.append("release change manifest ZIP MD5 does not match candidate ZIP")


def validate_candidate(candidate_dir: Path, require_deployable: bool = False) -> list[str]:
    errors: list[str] = []
    candidate_dir = candidate_dir.resolve()
    fwpkt = candidate_dir / "FwPkt"
    zip_path = candidate_dir / "FwPkt.zip"
    provenance_path = candidate_dir / "build-source-provenance.txt"
    manifest_path = candidate_dir / "install-manifest.json"

    if not fwpkt.is_dir():
        errors.append(f"missing candidate tree: {fwpkt}")
    if not zip_path.is_file():
        errors.append(f"missing candidate ZIP: {zip_path}")
    if not provenance_path.is_file():
        errors.append(f"missing candidate provenance: {provenance_path}")
    if errors:
        return errors

    provenance = read_provenance(provenance_path, errors)
    if provenance.get("candidate_id") != candidate_dir.name:
        errors.append(
            f"candidate_id does not match candidate directory: "
            f"{provenance.get('candidate_id')!r} != {candidate_dir.name!r}"
        )
    display_fwver = provenance.get("display_fwver", "")
    if not VERSION_RE.fullmatch(display_fwver):
        errors.append(f"display_fwver is not a five-component version: {display_fwver!r}")

    for key in ("git_commit", "patcher_commit"):
        value = provenance.get(key, "")
        if not COMMIT_RE.fullmatch(value):
            errors.append(f"{key} must be a full 40-character commit SHA: {value!r}")

    if not provenance.get("build_id"):
        errors.append("build_id is empty")
    if not provenance.get("selected_camlibs"):
        errors.append("selected_camlibs is empty")
    for key in ("dirty_diff_hash", "patcher_dirty_diff_hash"):
        if key in provenance and provenance[key] and not SHA256_RE.fullmatch(provenance[key]):
            errors.append(f"{key} is not empty or a SHA-256 hash")

    validate_release_change_manifest(candidate_dir, provenance, zip_path, errors)

    fwver_path = fwpkt / "FwVer"
    firmware_info_path = fwpkt / "firmwareInfo"
    if not fwver_path.is_file():
        errors.append(f"missing candidate FwVer: {fwver_path}")
    if not firmware_info_path.is_file():
        errors.append(f"missing candidate firmwareInfo: {firmware_info_path}")
    if fwver_path.is_file() and display_fwver:
        fwver = fwver_path.read_text(encoding="utf-8", errors="replace").strip()
        if not fwver.startswith(f"FwVer:{display_fwver};"):
            errors.append(
                f"FwPkt/FwVer does not match display_fwver={display_fwver}: {fwver!r}"
            )

    for relative in REQUIRED_PAYLOAD:
        if require_deployable and not (fwpkt / relative).is_file():
            errors.append(f"deployable candidate missing payload: FwPkt/{relative}")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            for required in ("FwPkt/FwVer", "FwPkt/firmwareInfo"):
                if required not in names:
                    errors.append(f"candidate ZIP missing {required}")
            if "FwPkt/FwVer" in names and display_fwver:
                zipped_fwver = archive.read("FwPkt/FwVer").decode("utf-8", "replace").strip()
                if not zipped_fwver.startswith(f"FwVer:{display_fwver};"):
                    errors.append("ZIP FwPkt/FwVer disagrees with provenance display_fwver")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"candidate ZIP is unreadable: {exc}")

    if not manifest_path.is_file():
        if require_deployable:
            errors.append("install-manifest.json missing: candidate is not deployable")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest root is not an object")
            zip_record = manifest.get("zip")
            if not isinstance(zip_record, dict):
                raise ValueError("manifest has no zip object")
            actual_sha = sha256_file(zip_path)
            if zip_record.get("sha256") != actual_sha:
                errors.append(
                    "install manifest ZIP SHA-256 mismatch: "
                    f"manifest={zip_record.get('sha256')!r} actual={actual_sha}"
                )
            if zip_record.get("size") != zip_path.stat().st_size:
                errors.append("install manifest ZIP size mismatch")
            if manifest.get("candidate") not in (None, candidate_dir.name):
                errors.append(
                    f"install manifest candidate mismatch: {manifest.get('candidate')!r}"
                )
            if not isinstance(manifest.get("files"), list) or not manifest["files"]:
                errors.append("install manifest has no mandatory file records")
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            errors.append(f"install-manifest.json is invalid: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument(
        "--require-deployable",
        action="store_true",
        help="require the complete manifest and payload needed before staging",
    )
    args = parser.parse_args()
    errors = validate_candidate(args.candidate_dir, args.require_deployable)
    if errors:
        print(f"CANDIDATE IDENTITY: FAIL ({args.candidate_dir})", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    state = "deployable" if args.require_deployable else "coherent-smoke"
    print(f"CANDIDATE IDENTITY: PASS ({state}) {args.candidate_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


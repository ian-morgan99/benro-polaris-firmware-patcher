#!/usr/bin/env python3
"""Write the immutable provenance record for one Astro candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode()
        h.update(len(rel).to_bytes(8, "big"))
        h.update(rel)
        h.update(sha256(path).encode())
    return h.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def stock_hash(path: Path) -> str:
    return sha256(path) if path.is_file() else tree_hash(path)


def dependency_files(bundle: Path) -> list[dict[str, object]]:
    roots = [
        bundle / "licenses",
        bundle / "COPY-TO-SD-CARD-ROOT" / "astrometry",
        bundle / "COPY-TO-SD-CARD-ROOT" / "polaris-astro" / "catalogue-tiles",
    ]
    files: list[dict[str, object]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            files.append({
                "path": path.relative_to(bundle).as_posix(),
                "sha256": sha256(path),
                "size": path.stat().st_size,
            })
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate-dir", required=True, type=Path)
    ap.add_argument("--patcher", required=True, type=Path)
    ap.add_argument("--camera-baseline", required=True)
    ap.add_argument("--astro-commit", required=True)
    ap.add_argument("--libgphoto2", required=True, type=Path)
    ap.add_argument("--stock", required=True, type=Path)
    ap.add_argument("--display-fwver", required=True)
    ap.add_argument("--build-id", required=True)
    ap.add_argument("--catalogue-package", required=True, type=Path)
    ap.add_argument("--focal-min", required=True)
    ap.add_argument("--focal-max", required=True)
    ap.add_argument("--sensor-mm", required=True)
    args = ap.parse_args()

    candidate = args.candidate_dir.resolve()
    bundle = candidate / "astro-bundle"
    zip_path = candidate / "FwPkt.zip"
    install_manifest = candidate / "install-manifest.json"
    astro_manifest = bundle / "ASTRO-MANIFEST.sha256"
    for path in (zip_path, install_manifest, bundle, astro_manifest):
        if not path.exists():
            raise SystemExit(f"ERROR: required candidate artifact missing: {path}")

    packet = {"sha256": sha256(zip_path), "md5": md5(zip_path),
              "size": zip_path.stat().st_size}
    appfs = candidate / "FwPkt" / "camera" / "appfs.ubifs"
    if appfs.is_file():
        packet["appfs_sha256"] = sha256(appfs)
    output = {
        "schema": 1,
        "candidate_variant": "astro",
        "candidate_id": candidate.name,
        "display_fwver": args.display_fwver,
        "build_id": args.build_id,
        "status": "candidate-build-only",
        "deployment": "not-performed",
        "hardware_qualification": "not-performed",
        "source": {
            "patcher_commit": git(args.patcher, "rev-parse", "HEAD"),
            "shared_camera_baseline": args.camera_baseline,
            "astro_commit": args.astro_commit,
            "libgphoto2_commit": git(args.libgphoto2, "rev-parse", "HEAD"),
            "libgphoto2_branch": git(args.libgphoto2, "branch", "--show-current"),
            "stock_input": str(args.stock.resolve()),
            "stock_sha256": stock_hash(args.stock.resolve()),
        },
        "astro": {
            "bundle_tree_sha256": tree_hash(bundle),
            "manifest_sha256": sha256(astro_manifest),
            "tar_sha256": sha256(candidate / "astro-bundle.tar.gz")
            if (candidate / "astro-bundle.tar.gz").is_file() else None,
            "catalogue_package": str(args.catalogue_package.resolve()),
            "catalogue_package_tree_sha256": tree_hash(args.catalogue_package.resolve()),
            "index_selection": {
                "focal_min_mm": args.focal_min,
                "focal_max_mm": args.focal_max,
                "sensor_width_mm": args.sensor_mm,
            },
            "dependency_files": dependency_files(bundle),
        },
        "firmware": {
            "packet": packet,
            "install_manifest_sha256": sha256(install_manifest),
            "install_manifest": "install-manifest.json",
            "shared_gate_transcript": "shared-camera-gate.txt",
            "astro_test_transcript": "astro-test-transcript.txt",
        },
        "features": [
            "native-C Astro solver side by side with Astrometry.net reference",
            "native-C Gaia catalogue bundle and selected FITS indexes",
            "capture/calibration/GOTO/frame-watch orchestration remains opt-in",
            "no live motor-rate command enabled",
        ],
        "known_limits": [
            "issue #251 remains release-blocking for the standard camera owner",
            "no physical Polaris or camera qualification was performed",
            "Astro bundle is additive SD-card content; it is not linked into Stage 2",
        ],
    }
    out = candidate / "astro-candidate-manifest.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"FwPkt SHA-256: {packet['sha256']}")
    print(f"Astro tree SHA-256: {output['astro']['bundle_tree_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

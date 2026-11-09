#!/usr/bin/env python3
"""Independent, read-only Astro regression runner.

The module intentionally uses only the Python standard library and an explicit
HTTP allow-list. It is safe to run against a live WebUI without enabling a
capture, mount move, tracking change, or EXIF write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
SAFE_GETS = {"/api/link", "/api/state", "/api/site"}
SAFE_HISTORIC = {"/api/test/upload", "/api/test/solve", "/api/test/state"}
FORBIDDEN = ("capture", "goto", "move", "motor", "track", "rate", "calibrat")


class Result:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append({"status": status, "name": name, "detail": detail})
        suffix = f": {detail}" if detail else ""
        print(f"{status:7} {name}{suffix}")

    @property
    def failed(self) -> bool:
        return any(row["status"] == "FAIL" for row in self.rows)

    @property
    def blocked(self) -> bool:
        return any(row["status"] == "BLOCKED" for row in self.rows)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def offline(result: Result) -> None:
    manifest = load_json(MANIFEST)
    safety = manifest["safety"]
    if safety["default_is_offline"] and not safety["allows_motor_commands"] and not safety["allows_camera_capture"]:
        result.add("PASS", "safety contract", "offline by default; motor and capture commands disabled")
    else:
        result.add("FAIL", "safety contract", "unsafe defaults in manifest")

    expected = {"k1ii": ("0183", "PENTAX K-1 Mark II"), "k3iii": ("0189", "PENTAX K-3 Mark III")}
    camera_cfg = manifest["camera_usb"]
    for camera, (pid, name) in expected.items():
        path = ROOT / manifest["fixtures"][f"{camera}_usb"]
        data = load_json(path)
        if (data.get("vendor_id"), data.get("product_id"), data.get("name")) == (camera_cfg["vendor_id"], pid, name):
            result.add("PASS", f"{camera} USB identity", f"{camera_cfg['vendor_id']}:{pid} {name}")
        else:
            result.add("FAIL", f"{camera} USB identity", json.dumps(data, sort_keys=True))

    for key, expected_class in (("k1ii_link", "camera_ready"), ("k3iii_link", "camera_ready"), ("k3iii_quarantined", "camera_quarantined")):
        data = load_json(ROOT / manifest["fixtures"][key])
        link = data["link"]
        if key == "k3iii_quarantined":
            valid = data.get("classification") == expected_class and link.get("camera_state") == -110 and link.get("model") == "none"
        else:
            valid = data.get("classification") == expected_class and link.get("camera_state") == 1 and link.get("model") != "none"
        result.add("PASS" if valid else "FAIL", f"{key} classification", data.get("classification", "missing"))

    paths = set(manifest["webui"]["read_only_paths"] + manifest["webui"]["historic_paths"])
    if paths == SAFE_GETS | SAFE_HISTORIC and not any(any(fragment in path.lower() for fragment in FORBIDDEN) for path in paths):
        result.add("PASS", "HTTP endpoint allow-list", "read-only link/state/site plus historic solver endpoints")
    else:
        result.add("FAIL", "HTTP endpoint allow-list", "unexpected or unsafe endpoint")

    images = load_json(ROOT / manifest["fixtures"]["images"])
    good = True
    for image in images["images"]:
        if len(image.get("sha256", "")) != 64 or image.get("width", 0) <= 0 or image.get("height", 0) <= 0:
            good = False
        if image.get("focal_mm", 0) <= 0 or image.get("sensor_width_mm", 0) <= 0:
            good = False
        if image["reference"].get("solved") and not image["reference"].get("ra_deg"):
            good = False
    result.add("PASS" if good else "FAIL", "image corpus metadata", f"{len(images['images'])} hashed external fixtures")


def request(base: str, path: str, method: str = "GET", body: bytes | None = None, content_type: str | None = None, timeout: float = 10.0):
    if path not in SAFE_GETS | SAFE_HISTORIC:
        raise ValueError(f"blocked non-read-only endpoint: {path}")
    url = base.rstrip("/") + path
    headers = {"User-Agent": "polaris-astro-regression/1"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read(), response.headers.get_content_type()


def json_request(base: str, path: str, timeout: float = 10.0):
    status, body, _ = request(base, path, timeout=timeout)
    return status, json.loads(body.decode("utf-8"))


def link_classification(data: object) -> str:
    text = json.dumps(data, sort_keys=True).lower()
    if "-110" in text or '"model":"none"' in text or "quarantined" in text:
        return "camera_quarantined_or_missing"
    if "pentax k-1 mark ii" in text or "pentax k-3 mark iii" in text:
        return "camera_identity_present"
    return "link_alive_camera_unknown"


def live_probe(result: Result, base: str) -> None:
    snapshots = {}
    for path in ("/api/link", "/api/state", "/api/site"):
        try:
            status, data = json_request(base, path)
            snapshots[path] = data
            result.add("PASS", f"GET {path}", f"HTTP {status}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result.add("BLOCKED", f"GET {path}", str(exc))
    if "/api/link" in snapshots:
        classification = link_classification(snapshots["/api/link"])
        result.add("PASS" if classification == "camera_identity_present" else "FAIL", "camera identity publication", classification)
    else:
        result.add("BLOCKED", "camera identity publication", "link snapshot unavailable")


def multipart(name: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----polaris-astro-regression-boundary"
    head = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def form(fields: dict[str, str]) -> tuple[bytes, str]:
    encoded = urllib.parse.urlencode(fields).encode()
    return encoded, "application/x-www-form-urlencoded"


def historic_probe(result: Result, base: str, image: Path, solver: str, focal: str, sensor: str, ra: str | None, dec: str | None, radius: str | None) -> None:
    if not image.is_file():
        result.add("BLOCKED", "historic image", f"not found: {image}")
        return
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    name = f"regression-{digest[:12]}-{image.name}"
    try:
        payload, content_type = multipart("file", name, image.read_bytes())
        status, raw, _ = request(base, "/api/test/upload?name=" + urllib.parse.quote(name), method="POST", body=payload, content_type=content_type, timeout=30)
        upload = json.loads(raw.decode())
        path = upload.get("path") or upload.get("file") or upload.get("name")
        if not path:
            result.add("FAIL", "historic upload", f"HTTP {status}: no returned path")
            return
        fields = {"path": path, "solver": solver, "focal": focal, "sensor": sensor}
        if ra is not None and dec is not None:
            fields.update({"ra": ra, "dec": dec})
            if radius is not None:
                fields["radius"] = radius
        body, content_type = form(fields)
        started = time.monotonic()
        status, raw, _ = request(base, "/api/test/solve", method="POST", body=body, content_type=content_type, timeout=90)
        solve = json.loads(raw.decode())
        elapsed = time.monotonic() - started
        safe = solve.get("motor_control") is False and solve.get("exif_writeback") is False
        result.add("PASS" if safe else "FAIL", "historic solver safety contract", f"HTTP {status}; elapsed={elapsed:.3f}s; solver={solver}")
        if not safe:
            result.add("FAIL", "historic solver result", "response did not prove motor_control=false and exif_writeback=false")
        else:
            result.add("PASS" if solve.get("solved") is True else "FAIL", "historic solver result", json.dumps(solve, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.add("BLOCKED", "historic solver", str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="run deterministic checks only")
    parser.add_argument("--live", action="store_true", help="probe the read-only WebUI")
    parser.add_argument("--webui-url", default="http://192.168.0.1:8090")
    parser.add_argument("--historic-image", type=Path)
    parser.add_argument("--solver", choices=("reference", "native"), default="reference")
    parser.add_argument("--focal", default="auto")
    parser.add_argument("--sensor", default="auto")
    parser.add_argument("--ra")
    parser.add_argument("--dec")
    parser.add_argument("--radius")
    args = parser.parse_args(argv)
    result = Result()
    offline(result)
    if args.live or args.historic_image:
        live_probe(result, args.webui_url)
    if args.historic_image:
        historic_probe(result, args.webui_url, args.historic_image, args.solver, args.focal, args.sensor, args.ra, args.dec, args.radius)
    if not args.offline and not args.live and args.historic_image is None:
        print("PASS    no live actions requested; offline checks are the default")
    summary = {"failed": result.failed, "blocked": result.blocked, "rows": result.rows}
    print(json.dumps(summary, sort_keys=True))
    if result.failed:
        return 1
    if result.blocked:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

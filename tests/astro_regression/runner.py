#!/usr/bin/env python3
"""Safety wrapper for the independent Astro regression runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
IMPL_PATH = HERE / "runner_impl.py"
SPEC = importlib.util.spec_from_file_location("astro_regression_impl", IMPL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {IMPL_PATH}")
IMPL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPL)
SAFE_GETS = IMPL.SAFE_GETS
SAFE_HISTORIC = IMPL.SAFE_HISTORIC


def request(base: str, path: str, method: str = "GET", body: bytes | None = None, content_type: str | None = None, timeout: float = 10.0):
    endpoint = urllib.parse.urlsplit(path).path
    if endpoint not in SAFE_GETS | SAFE_HISTORIC:
        raise ValueError(f"blocked non-read-only endpoint: {path}")
    headers = {"User-Agent": "polaris-astro-regression/1"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(base.rstrip("/") + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read(), response.headers.get_content_type()


def historic_probe(result, base: str, image: Path, solver: str, focal: str, sensor: str, ra: str | None, dec: str | None, radius: str | None) -> None:
    if not image.is_file():
        result.add("BLOCKED", "historic image", f"not found: {image}")
        return
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    name = f"regression-{digest[:12]}-{image.name}"
    try:
        status, raw, _ = request(base, "/api/test/upload?name=" + urllib.parse.quote(name), "POST", image.read_bytes(), "application/octet-stream", 30)
        upload = json.loads(raw.decode("utf-8"))
        path = upload.get("path") or upload.get("file") or upload.get("name")
        if not path:
            result.add("FAIL", "historic upload", f"HTTP {status}: no returned path")
            return
        fields = {"path": path, "solver": solver, "focal": focal, "sensor": sensor}
        if ra is not None and dec is not None:
            fields.update({"ra": ra, "dec": dec})
            if radius is not None:
                fields["radius"] = radius
        body = urllib.parse.urlencode(fields).encode("utf-8")
        started = time.monotonic()
        status, raw, _ = request(base, "/api/test/solve", "POST", body, "application/x-www-form-urlencoded", 30)
        start = json.loads(raw.decode("utf-8"))
        safe = start.get("motor_control") is False and start.get("exif_writeback") is False
        result.add("PASS" if safe else "FAIL", "historic solver safety contract", f"HTTP {status}; solver={solver}")
        if not safe:
            return
        final = None
        for _ in range(180):
            state_status, state_raw, _ = request(base, "/api/test/state", timeout=10)
            state = json.loads(state_raw.decode("utf-8"))
            if state.get("status") in {"done", "failed", "error"}:
                final = state
                break
            time.sleep(0.5)
        elapsed = time.monotonic() - started
        if final is None:
            result.add("FAIL", "historic solver result", f"no terminal state after {elapsed:.3f}s")
            return
        payload = final.get("result", final)
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = dict(payload)
        payload["motor_control"] = False
        payload["exif_writeback"] = False
        solved = final.get("status") == "done" and payload.get("solved") is True
        result.add("PASS" if solved else "FAIL", "historic solver result", f"elapsed={elapsed:.3f}s; {json.dumps(payload, sort_keys=True)}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.add("BLOCKED", "historic solver", str(exc))


IMPL.request = request
IMPL.historic_probe = historic_probe

if __name__ == "__main__":
    sys.exit(IMPL.main())

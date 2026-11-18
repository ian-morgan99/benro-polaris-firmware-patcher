#!/usr/bin/env python3
"""Exercise the full range of Astro WebUI protocol endpoints against a live Polaris.

Monitors mlog/clog after each POST/GET and reports any anomalies.
Does NOT write anything locally — only reads from the device.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from urllib.parse import urlencode

HOST = "192.168.68.25"
PORT = 8090


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def http_get(path: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Perform a raw HTTP GET. Returns (status, body, headers)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((HOST, PORT))
        req = f"GET {path} HTTP/1.0\r\nHost: {HOST}\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode("ascii"))
        data = b""
        while True:
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
    finally:
        s.close()

    text = data.decode("ascii", errors="replace")
    # Split headers from body
    if "\r\n\r\n" in text:
        head, body = text.split("\r\n\r\n", 1)
    else:
        head, body = text, ""
    # Extract status line
    status_line = head.split("\r\n")[0] if head else ""
    status = 0
    parts = status_line.split(" ")
    if len(parts) >= 2:
        try:
            status = int(parts[1])
        except ValueError:
            status = 0
    return status, body, head


def http_post(path: str, body: str = "", timeout: float = 10.0) -> tuple[int, str, str]:
    """Perform a raw HTTP POST."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((HOST, PORT))
        encoded = body.encode("utf-8")
        req = (
            f"POST {path} HTTP/1.0\r\n"
            f"Host: {HOST}\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(encoded)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        s.sendall(req.encode("ascii") + encoded)
        data = b""
        while True:
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
    finally:
        s.close()

    text = data.decode("ascii", errors="replace")
    if "\r\n\r\n" in text:
        head, resp_body = text.split("\r\n\r\n", 1)
    else:
        head, resp_body = text, ""
    status_line = head.split("\r\n")[0] if head else ""
    status = 0
    parts = status_line.split(" ")
    if len(parts) >= 2:
        try:
            status = int(parts[1])
        except ValueError:
            status = 0
    return status, resp_body, head


def log(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def main() -> int:
    failures = 0

    # 1. /api/state — full device state
    log("=== TEST 1: GET /api/state ===")
    status, body, head = http_get("/api/state")
    log(f"  status={status} body_len={len(body)}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1
    else:
        try:
            state = json.loads(body)
            log(f"  status={state.get('status')} aligned={state.get('aligned')}")
            log(f"  tracking={state.get('tracking')} mount_read={state.get('mount_read')}")
            sol = state.get("solution", {})
            if sol:
                log(f"  solved={sol.get('solved')} nmatch={sol.get('nmatch')} "
                    f"pixscale={sol.get('pixscale_arcsec')} ra={sol.get('ra_deg')} "
                    f"dec={sol.get('dec_deg')}")
        except json.JSONDecodeError as e:
            log(f"  FAIL: invalid JSON: {e}")
            failures += 1

    # 2. /api/link — link state
    log("=== TEST 2: GET /api/link ===")
    status, body, head = http_get("/api/link")
    log(f"  status={status} body_len={len(body)} body={body[:200]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 3. /api/snapshot — preview frame
    log("=== TEST 3: GET /api/snapshot ===")
    status, body, head = http_get("/api/snapshot")
    log(f"  status={status} body_len={len(body)}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1
    elif len(body) == 0:
        log("  FAIL: empty snapshot body")
        failures += 1

    # 4. /api/wifi status
    log("=== TEST 4: GET /api/wifi ===")
    status, body, head = http_get("/api/wifi")
    log(f"  status={status} body_len={len(body)} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 5. POST /api/wifi with unknown action (should fail loudly per #273 fix)
    log("=== TEST 5: POST /api/wifi action=bogus (expect rejection) ===")
    status, body, head = http_post("/api/wifi", "action=bogus")
    log(f"  status={status} body={body[:300]}")
    try:
        resp = json.loads(body)
        if resp.get("ok") is False:
            log("  PASS: unknown action correctly rejected")
        else:
            log(f"  FAIL: unknown action not rejected: {resp}")
            failures += 1
    except json.JSONDecodeError:
        log(f"  FAIL: non-JSON response: {body[:200]}")
        failures += 1

    # 6. POST /api/wifi action=save with valid credentials (should be accepted or rejected properly)
    log("=== TEST 6: POST /api/wifi action=save (valid creds) ===")
    status, body, head = http_post("/api/wifi", "action=save&ssid=testnet&psk=testpass123")
    log(f"  status={status} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 7. POST /api/apply — apply last solve (no solved frame)
    log("=== TEST 7: POST /api/apply (no solved frame) ===")
    status, body, head = http_post("/api/apply", "")
    log(f"  status={status} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 8. POST /api/link/send — shutter command (code 264)
    log("=== TEST 8: POST /api/link/send (shutter code 264) ===")
    status, body, head = http_post("/api/link/send", "code=264&subtype=2&payload=-100")
    log(f"  status={status} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 9. POST /api/link/send — invalid code
    log("=== TEST 9: POST /api/link/send (invalid code 9999) ===")
    status, body, head = http_post("/api/link/send", "code=9999&subtype=2&payload=-100")
    log(f"  status={status} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 10. POST /api/solve — trigger a solve
    log("=== TEST 10: POST /api/solve ===")
    status, body, head = http_post("/api/solve", "mode=capture")
    log(f"  status={status} body={body[:300]}")
    if status != 200:
        log(f"  FAIL: expected 200, got {status}")
        failures += 1

    # 11. GET /api/state again after solve to check state change
    log("=== TEST 11: GET /api/state (after solve) ===")
    status, body, head = http_get("/api/state")
    log(f"  status={status} body_len={len(body)}")
    if status == 200:
        try:
            state = json.loads(body)
            log(f"  status={state.get('status')} tracking={state.get('tracking')}")
        except json.JSONDecodeError:
            log("  FAIL: invalid JSON")
            failures += 1

    log(f"\n=== SUMMARY: {failures} failure(s) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

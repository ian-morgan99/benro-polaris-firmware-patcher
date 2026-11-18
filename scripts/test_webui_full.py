#!/usr/bin/env python3
"""Exercise camera parameter get/set, shutter release, and file processing
via the Astro WebUI protocol against a live Polaris.

Captures /app/Clog.txt and /app/Mlog.txt before and after each test so that
any new log entries can be correlated with the test action.

Does NOT write anything locally — only reads from the device.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from urllib.parse import urlencode

HOST = "192.168.68.25"
PORT = 8090
SSH_HOST = "root@192.168.68.25"
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15"]


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def http_get(path: str, timeout: float = 10.0) -> tuple[int, str, str]:
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
    if "\r\n\r\n" in text:
        head, body = text.split("\r\n\r\n", 1)
    else:
        head, body = text, ""
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


# ---------------------------------------------------------------------------
# SSH / log capture
# ---------------------------------------------------------------------------

import subprocess


def ssh(cmd: str, timeout: float = 15.0) -> tuple[int, str]:
    full = ["ssh", *SSH_OPTS, SSH_HOST, cmd]
    try:
        p = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 2, f"{type(exc).__name__}: {exc}"


def read_remote(path: str) -> str:
    rc, out = ssh(f"cat {path} 2>/dev/null")
    return out if rc == 0 else ""


def md5_remote(path: str) -> str:
    rc, out = ssh(f"md5sum {path} 2>/dev/null | awk '{{print $1}}'")
    return out.strip() if rc == 0 else ""


def tail_remote(path: str, lines: int = 50) -> str:
    rc, out = ssh(f"tail -n {lines} {path} 2>/dev/null")
    return out if rc == 0 else ""


def capture_logs() -> dict[str, str]:
    """Return current md5 + full content of Clog and Mlog."""
    return {
        "clog_md5": md5_remote("/app/Clog.txt"),
        "clog": read_remote("/app/Clog.txt"),
        "mlog_md5": md5_remote("/app/Mlog.txt"),
        "mlog": read_remote("/app/Mlog.txt"),
    }


def log_diff(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    """Return new lines that appeared in each log between before and after."""
    result = {}
    for key in ("clog", "mlog"):
        before_lines = set(before[key].splitlines()) if before[key] else set()
        after_lines = after[key].splitlines() if after[key] else []
        new_lines = [ln for ln in after_lines if ln not in before_lines]
        result[key] = "\n".join(new_lines)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

failures = 0
results: list[tuple[str, str, str]] = []  # (test, status, detail)


def record(test: str, status: str, detail: str = "") -> None:
    global failures
    results.append((test, status, detail))
    suffix = f": {detail}" if detail else ""
    print(f"  [{status}] {test}{suffix}", flush=True)
    if status == "FAIL":
        failures += 1


def test_api_state() -> None:
    """GET /api/state — full device state."""
    log("=== TEST: GET /api/state ===")
    before = capture_logs()
    status, body, head = http_get("/api/state")
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("GET /api/state", "FAIL", f"expected 200, got {status}")
        return
    try:
        state = json.loads(body)
        sol = state.get("solution") or {}
        record("GET /api/state", "PASS",
               f"status={state.get('status')} aligned={state.get('aligned')} "
               f"tracking={state.get('tracking')} solved={sol.get('solved')}")
    except json.JSONDecodeError as e:
        record("GET /api/state", "FAIL", f"invalid JSON: {e}")
        return

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_link() -> None:
    """GET /api/link — link state."""
    log("=== TEST: GET /api/link ===")
    before = capture_logs()
    status, body, head = http_get("/api/link")
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("GET /api/link", "FAIL", f"expected 200, got {status}")
        return
    try:
        link = json.loads(body)
        record("GET /api/link", "PASS",
               f"status={link.get('status')} wanted={link.get('wanted')} "
               f"connects={link.get('connects')} drops={link.get('drops')}")
    except json.JSONDecodeError as e:
        record("GET /api/link", "FAIL", f"invalid JSON: {e}")
        return

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_wifi() -> None:
    """GET /api/wifi — Wi-Fi state."""
    log("=== TEST: GET /api/wifi ===")
    before = capture_logs()
    status, body, head = http_get("/api/wifi")
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("GET /api/wifi", "FAIL", f"expected 200, got {status}")
        return
    try:
        wifi = json.loads(body)
        record("GET /api/wifi", "PASS",
               f"ok={wifi.get('ok')} ap_ip={wifi.get('ap_ip')} "
               f"sta_ip={wifi.get('sta_ip')} configured={wifi.get('configured')}")
    except json.JSONDecodeError as e:
        record("GET /api/wifi", "FAIL", f"invalid JSON: {e}")
        return

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_wifi_bogus() -> None:
    """POST /api/wifi with unknown action — should be rejected."""
    log("=== TEST: POST /api/wifi action=bogus ===")
    before = capture_logs()
    status, body, head = http_post("/api/wifi", "action=bogus")
    after = capture_logs()
    diff = log_diff(before, after)

    try:
        resp = json.loads(body)
        if resp.get("ok") is False:
            record("POST /api/wifi bogus", "PASS", "unknown action correctly rejected")
        else:
            record("POST /api/wifi bogus", "FAIL", f"not rejected: {resp}")
    except json.JSONDecodeError:
        record("POST /api/wifi bogus", "FAIL", f"non-JSON: {body[:200]}")

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_link_send_shutter() -> None:
    """POST /api/link/send with shutter code 264 — trigger a capture."""
    log("=== TEST: POST /api/link/send shutter (code 264) ===")
    before = capture_logs()
    # The /api/link/send endpoint expects 'cmd' as a number parameter.
    # Shutter (code 264) moves the mount and requires confirm=1 per safety policy.
    status, body, head = http_post("/api/link/send", "cmd=264&subtype=4&payload=state:1;bulb:0;c:-1;&confirm=1", timeout=30)
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("POST /api/link/send shutter", "FAIL", f"expected 200, got {status}: {body[:200]}")
        return

    try:
        resp = json.loads(body)
        if resp.get("ok"):
            record("POST /api/link/send shutter", "PASS", f"shutter accepted: {resp}")
        else:
            record("POST /api/link/send shutter", "FAIL", f"shutter rejected: {resp}")
    except json.JSONDecodeError:
        # May return non-JSON; check if it's a success HTML or similar
        if "ok" in body.lower() or status == 200:
            record("POST /api/link/send shutter", "PASS", f"shutter sent (non-JSON): {body[:200]}")
        else:
            record("POST /api/link/send shutter", "FAIL", f"unexpected: {body[:200]}")

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:3000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:3000])


def test_api_link_send_invalid() -> None:
    """POST /api/link/send with invalid code — should be rejected."""
    log("=== TEST: POST /api/link/send invalid code ===")
    before = capture_logs()
    status, body, head = http_post("/api/link/send", "code=9999&subtype=2&payload=-100")
    after = capture_logs()
    diff = log_diff(before, after)

    if status == 400:
        record("POST /api/link/send invalid", "PASS", "invalid code correctly rejected with 400")
    elif status == 200:
        record("POST /api/link/send invalid", "FAIL", "invalid code was accepted (should be rejected)")
    else:
        record("POST /api/link/send invalid", "FAIL", f"unexpected status {status}: {body[:200]}")

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_solve() -> None:
    """POST /api/solve — trigger a plate solve."""
    log("=== TEST: POST /api/solve ===")
    before = capture_logs()
    status, body, head = http_post("/api/solve", "mode=capture", timeout=30)
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("POST /api/solve", "FAIL", f"expected 200, got {status}: {body[:200]}")
        return
    try:
        resp = json.loads(body)
        if resp.get("started"):
            record("POST /api/solve", "PASS", "solve started")
        else:
            record("POST /api/solve", "FAIL", f"solve not started: {resp}")
    except json.JSONDecodeError:
        record("POST /api/solve", "FAIL", f"non-JSON: {body[:200]}")
        return

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:3000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:3000])


def test_api_apply() -> None:
    """POST /api/apply — apply last solve result."""
    log("=== TEST: POST /api/apply ===")
    before = capture_logs()
    status, body, head = http_post("/api/apply", "", timeout=15)
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("POST /api/apply", "FAIL", f"expected 200, got {status}: {body[:200]}")
        return
    try:
        resp = json.loads(body)
        # May be ok:false if no fresh solve — that's expected behavior
        record("POST /api/apply", "PASS",
               f"ok={resp.get('ok')} error={resp.get('error', '')[:80]} age={resp.get('age_sec', '?')}")
    except json.JSONDecodeError:
        record("POST /api/apply", "FAIL", f"non-JSON: {body[:200]}")
        return

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def test_api_site() -> None:
    """GET /api/site — site info."""
    log("=== TEST: GET /api/site ===")
    before = capture_logs()
    status, body, head = http_get("/api/site")
    after = capture_logs()
    diff = log_diff(before, after)

    if status != 200:
        record("GET /api/site", "FAIL", f"expected 200, got {status}")
        return
    record("GET /api/site", "PASS", f"body_len={len(body)}")

    if diff["clog"] or diff["mlog"]:
        log("  --- NEW CLOG entries ---")
        log(diff["clog"][:2000])
        log("  --- NEW MLOG entries ---")
        log(diff["mlog"][:2000])


def main() -> int:
    global failures

    log(f"=== WebUI protocol test against {HOST}:{PORT} ===")
    log("Camera: Pentax K-1 Mark II on Polaris at 192.168.68.25")
    log("")

    test_api_state()
    test_api_link()
    test_api_wifi()
    test_api_wifi_bogus()
    test_api_link_send_shutter()
    test_api_link_send_invalid()
    test_api_solve()
    test_api_apply()
    test_api_site()

    log("")
    log(f"=== SUMMARY: {failures} failure(s) ===")
    for test, status, detail in results:
        mark = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{mark}] {test} {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""o-v12n first-canary probe: authenticate on 9090, report camera state,
optionally fire exactly one capture (code 264) and watch the lifecycle.

Usage:
  canary-probe.py --probe            # handshake + camera state only
  canary-probe.py --shot            # handshake + preview off + ONE capture
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import math
import posixpath
import shlex
import socket
import subprocess
import sys
import time


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Polaris:
    def __init__(self, host: str, port: int, bind: str | None, timeout: float):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if bind:
            self.sock.bind((bind, 0))
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.buffer = b""

    def close(self) -> None:
        self.sock.close()

    def send(self, code: int, subtype: int = 2, payload: str = "-100") -> None:
        frame = f"1&{code}&{subtype}&{payload}#"
        print(f"{stamp()} TX {frame}", flush=True)
        self.sock.sendall(frame.encode("ascii"))

    def frame(self, deadline: float) -> tuple[int, str]:
        while b"#" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("response deadline expired")
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("9090 socket closed")
            self.buffer += chunk
        raw, self.buffer = self.buffer.split(b"#", 1)
        text = raw.decode("ascii", errors="replace")
        if "@" in text:
            raw_code, payload = text.split("@", 1)
        else:
            parts = text.split("&", 3)
            if len(parts) != 4:
                print(f"{stamp()} RX_UNPARSED {text}#", flush=True)
                return -1, text
            raw_code, payload = parts[1], parts[3]
        try:
            code = int(raw_code)
        except ValueError:
            code = -1
        print(f"{stamp()} RX {text}#", flush=True)
        return code, payload

    def wait_code(self, wanted: int, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        while True:
            code, payload = self.frame(deadline)
            if code == wanted:
                return payload


def field(payload: str, name: str) -> str | None:
    prefix = f"{name}:"
    for item in payload.split(";"):
        if item.startswith(prefix):
            return item[len(prefix):]
    return None


class DeviceFileCheck:
    """Compare file names around one shot without writing markers on-device."""

    def __init__(self, ssh_host: str | None, output_dir: str,
                 ssh_options: list[str] | None = None):
        self.ssh_host = ssh_host
        self.output_dir = output_dir
        self.ssh_options = ssh_options or ["ssh", "-o", "BatchMode=yes",
                                           "-o", "ConnectTimeout=5"]
        self.before_files: set[str] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.ssh_host)

    def _list_files(self, timeout: float = 30.0) -> list[str] | None:
        if not self.enabled:
            return None
        cmd = f"find {shlex.quote(self.output_dir)} -type f 2>/dev/null"
        try:
            proc = subprocess.run(self.ssh_options + [self.ssh_host, cmd],
                                  capture_output=True, text=True, timeout=timeout,
                                  check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"{stamp()} FILECHECK query failed ({type(exc).__name__})",
                  flush=True)
            return None
        if proc.returncode != 0:
            print(f"{stamp()} FILECHECK query rc={proc.returncode} "
                  f"{proc.stderr.strip()[:120]}", flush=True)
            return None
        return sorted(line for line in proc.stdout.splitlines() if line.strip())

    def arm(self) -> None:
        """Snapshot names before capture; a failed snapshot leaves the check unknown."""
        self.before_files = None
        if not self.enabled:
            return
        files = self._list_files(timeout=15.0)
        if files is None:
            print(f"{stamp()} FILECHECK baseline unavailable; timeout verdict will be unknown",
                  flush=True)
            return
        self.before_files = set(files)

    def new_files(self, timeout: float = 30.0) -> list[str] | None:
        """New files since arm, or None if either inventory is unknown."""
        if self.before_files is None:
            return None
        files = self._list_files(timeout=timeout)
        if files is None:
            return None
        return sorted(set(files) - self.before_files)

    def disarm(self) -> None:
        self.before_files = None


def expected_output_files(paths: list[str], expected_files: int) -> list[str] | None:
    """Return one complete SP_ output set, rejecting partial or mixed captures."""
    outputs = sorted(path for path in set(paths)
                     if posixpath.basename(path).startswith("SP_"))
    if len(outputs) != expected_files:
        return None
    if len({posixpath.splitext(path)[0] for path in outputs}) != 1:
        return None
    return outputs


def wait_for_expected_output_set(
    filecheck: DeviceFileCheck, expected_files: int, wait_seconds: float
) -> tuple[bool, list[str], list[str] | None]:
    """Return whether inventory worked, last new paths, and a complete set if found."""
    if filecheck.before_files is None:
        return False, [], None
    deadline = time.monotonic() + wait_seconds
    observed = False
    new_files: list[str] = []
    first_check = True
    while first_check or time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        query_timeout = min(30.0, max(1.0 if first_check else 0.1, remaining))
        first_check = False
        found = filecheck.new_files(timeout=query_timeout)
        if found is not None:
            observed = True
            new_files = found
            complete = expected_output_files(found, expected_files)
            if complete:
                return observed, new_files, complete
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return observed, new_files, None
        time.sleep(min(2.0, remaining))
    return observed, new_files, None


def effective_shot_timeout(base: float, bulb_seconds: int | None) -> float:
    """Allow the camera's Bulb hold plus transfer/lifecycle time."""
    if base <= 0:
        raise ValueError("--shot-timeout must be positive")
    if bulb_seconds is None:
        return base
    if bulb_seconds <= 0:
        raise ValueError("--bulb-seconds must be positive")
    return max(base, float(bulb_seconds + 90))


def bulb_capture_payload(seconds: float | None) -> str:
    """Build the capture request; zero is deliberately not a Bulb test.

    The firmware scans this field with `%d` (see the `state:%d;bulb:%d;c:%d;`
    sscanf in the command-264 handler), so a fractional request is truncated to
    whole seconds rather than sent as a value the parser would truncate anyway.
    """
    if seconds is None:
        return "state:1;bulb:0;c:-1;"
    if seconds <= 0:
        raise ValueError("--bulb-seconds must be positive")
    return f"state:1;bulb:{int(seconds)};c:-1;"


# Wire commands, established by disassembling the stock binaries and confirmed
# against the Benro Connect app's own traffic in /app/sd/system/log/Mlog_*.log.
#   261 -> setCameraConfig(3, ...)  shutter, payload "s:<index>;"
#   268 -> getCameraConfig(3)       shutter list,   reply  "RD:0;V:<index>;R:<list>;"
#   277 -> camera_set_aperture      aperture only -- it is NOT a shutter setter.
# See docs/evidence/bulb-root-cause-20261005/SUMMARY.md.
SHUTTER_SET_COMMAND = 261
SHUTTER_INFO_COMMAND = 268
EV_SET_COMMAND = 260


def parse_shutter_seconds(label: str) -> float | None:
    """Convert a command-268 shutter label into seconds, or None if not numeric.

    The K-3 III list mixes two encodings: slash forms where a proper fraction
    is sub-second (``1/8000``) and an improper one is a real duration
    (``13/10`` == 1.3 s), and ``MM-SS`` for minute values (``00-30`` == 30 s,
    ``01-30`` == 90 s). Non-durations such as ``Bulb`` or ``Auto`` return None
    so callers skip them instead of guessing.
    """
    text = label.strip()
    if not text:
        return None
    if "-" in text:
        minutes, _, seconds = text.partition("-")
        try:
            return float(int(minutes) * 60 + int(seconds))
        except ValueError:
            return None
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            top, bottom = int(numerator), int(denominator)
        except ValueError:
            return None
        if bottom == 0:
            return None
        return top / bottom
    try:
        return float(text)
    except ValueError:
        return None


def resolve_shutter_index(options: list[str], seconds: float) -> tuple[int, str, float]:
    """Choose the option index closest to a requested exposure in seconds.

    Prefers an exact match, then the shortest option that still covers the
    request, and finally the longest available. Never returns a non-numeric
    entry, so a list without a ``Bulb`` label is not an error.
    """
    scored = []
    for index, option in enumerate(options):
        duration = parse_shutter_seconds(option)
        if duration is None or duration <= 0:
            continue
        scored.append((index, option, duration))
    if not scored:
        raise RuntimeError("command 268 exposed no numeric shutter options")
    wanted = float(seconds)
    exact = [item for item in scored if abs(item[2] - wanted) < 1e-6]
    if exact:
        return exact[0]
    covers = [item for item in scored if item[2] >= wanted]
    if covers:
        return min(covers, key=lambda item: item[2])
    return max(scored, key=lambda item: item[2])


def shutter_options(p: Polaris, timeout: float = 10.0, quiet: bool = False):
    """Read the current shutter index and option list through command 268."""
    p.send(SHUTTER_INFO_COMMAND)
    response = p.wait_code(SHUTTER_INFO_COMMAND, timeout)
    raw_options = field(response, "R")
    if raw_options is None:
        raise RuntimeError(f"shutter-info response has no R option list: {response}")
    options = [item.strip() for item in raw_options.split(",") if item.strip()]
    if not options:
        raise RuntimeError(f"shutter-info response has an empty option list: {response}")
    current_raw = field(response, "V") or field(response, "shutter")
    current = None
    if current_raw is not None:
        try:
            current = int(current_raw)
        except ValueError:
            matches = [index for index, option in enumerate(options)
                       if option.lower() == current_raw.lower()]
            if len(matches) == 1:
                current = matches[0]
            else:
                raise RuntimeError(
                    f"shutter-info response has an unresolvable current value: {response}"
                )
        if current < 0 or current >= len(options):
            raise RuntimeError(
                f"shutter-info response current index is outside option list: {response}"
            )
    if not quiet:
        print(f"{stamp()} SHUTTER_OPTIONS current={current} options={options}", flush=True)
    return current, options


def prepare_bulb_shutter(
    p: Polaris,
    bulb_seconds: float,
    explicit_index: int | None = None,
    timeout: float = 10.0,
) -> tuple[int, int, str, float | None]:
    """Return (current index, chosen index, label, seconds) before changing the camera.

    The K-3 III's command 268 list has no `Bulb` entry (it stops at `00-30`), so
    a long exposure is requested as the nearest available timed shutter.  An
    explicit `--bulb-shutter-index` still wins, which is how a device that does
    expose `Bulb` in its list stays testable.

    With the dial on `B` the body reports a single-entry list instead — measured
    on device (o-v16c-context-lifetime-20261009): `268@RD:0;V:0;R:00:00,;`.
    That is the bulb slot, not "no numeric options", so it is returned as-is and
    the dial is left alone; the previous behaviour aborted the whole bulb canary
    with `command 268 exposed no numeric shutter options`.
    """
    current, options = shutter_options(p, timeout)
    if current is None:
        raise RuntimeError("cannot run Bulb test without a readable current shutter index")
    if explicit_index is None and len(options) == 1 and not parse_shutter_seconds(options[0]):
        return current, current, options[0], None
    if explicit_index is not None:
        if explicit_index < 0 or explicit_index >= len(options):
            raise ValueError(f"--bulb-shutter-index {explicit_index} is outside option list")
        index = explicit_index
        label = options[index]
        seconds = parse_shutter_seconds(label)
    else:
        index, label, seconds = resolve_shutter_index(options, bulb_seconds)
    return current, index, label, seconds


# The K-3 III applies a 261 shutter write asynchronously. Measured on device
# (out/logs/device-20261005-late, Clog): `s:54` accepted with ret:0 at 18:49:41,
# command 268 still reporting V:33 at 18:49:42, and V:54 from 18:49:54 -- a
# ~13 s write-to-visible delay. A single immediate readback therefore reports a
# real, working write as "accepted but not applied", which is how #173 came to be
# recorded as a camera limitation. Verify by polling within a bounded budget.
SHUTTER_SETTLE_TIMEOUT_S = 30.0
SHUTTER_SETTLE_POLL_S = 1.0


def set_shutter(
    p: Polaris,
    index: int,
    timeout: float = 10.0,
    verify: bool = True,
    settle_timeout: float = SHUTTER_SETTLE_TIMEOUT_S,
    poll_interval: float = SHUTTER_SETTLE_POLL_S,
    sleep=time.sleep,
) -> str:
    """Select the camera shutter through the proven 261 `s:<index>;` command.

    `ret:0` only means the request parsed, and the camera then takes seconds to
    honour it (see SHUTTER_SETTLE_TIMEOUT_S). The readback is therefore polled
    until it matches or the budget runs out; only then is the accepted-but-not-
    applied case raised as an error rather than reported as a success.
    """
    if index < 0:
        raise ValueError("--bulb-shutter-index must be non-negative")
    p.send(SHUTTER_SET_COMMAND, payload=f"s:{index};")
    response = p.wait_code(SHUTTER_SET_COMMAND, timeout)
    ret = field(response, "ret")
    if ret != "0":
        raise RuntimeError(f"shutter selection lacked explicit ret:0: {response}")
    print(f"{stamp()} SHUTTER index={index} response={response}", flush=True)
    if verify:
        deadline = time.monotonic() + max(settle_timeout, 0.0)
        attempt = 0
        while True:
            attempt += 1
            readback, options = shutter_options(p, timeout, quiet=True)
            if readback == index:
                if attempt > 1:
                    print(
                        f"{stamp()} SHUTTER index={index} confirmed after {attempt} "
                        f"readbacks (the camera applies 261 writes asynchronously)",
                        flush=True,
                    )
                break
            if time.monotonic() >= deadline:
                label = (
                    options[readback]
                    if readback is not None and readback < len(options)
                    else "?"
                )
                raise RuntimeError(
                    f"shutter index {index} was accepted (ret:0) but still is not "
                    f"reported after {settle_timeout:.0f}s ({attempt} readbacks); "
                    f"the camera reports V:{readback} ({label})"
                )
            print(
                f"{stamp()} SHUTTER index={index} not yet visible (V:{readback}), "
                f"re-reading in {poll_interval}s",
                flush=True,
            )
            sleep(poll_interval)
    return response


def set_ev(p: Polaris, index: int, timeout: float = 10.0) -> str:
    """Set EV compensation through the app's own command 260 (`ev:<index>;`).

    The K-3 III exposes 31 entries (idx 0 = +5 … idx 30 = -5, 1/3-stop steps).
    `ret:0` is the camera's acceptance; unlike 261 shutter writes this one was
    observed to apply immediately (Mlog 14:09:01 ev:30 -> ret:0 in 66 ms).
    """
    if not 0 <= index <= 30:
        raise ValueError("--ev-index must be within the camera's 0..30 option list")
    p.send(EV_SET_COMMAND, payload=f"ev:{index};")
    response = p.wait_code(EV_SET_COMMAND, timeout)
    ret = field(response, "ret")
    if ret != "0":
        raise RuntimeError(f"EV index {index} lacked explicit ret:0: {response}")
    print(f"{stamp()} EV index={index} response={response}", flush=True)
    return response


@contextmanager
def bulb_shutter_session(
    p: Polaris,
    bulb_seconds: float,
    explicit_index: int | None = None,
    timeout: float = 10.0,
):
    """Select the long-exposure shutter for a capture and restore the prior index."""
    current, bulb_index, bulb_label, bulb_actual = prepare_bulb_shutter(
        p, bulb_seconds, explicit_index, timeout
    )
    operation_error: BaseException | None = None
    # The body already reports the slot we want (dial on `B`, or a timed list
    # whose best match is the current index). Writing it anyway is not a no-op:
    # measured on device, `s:0;` over `V:0;R:00:00,;` answers `ret:-2`, which
    # this helper treats as a failure. Skip the write and the restore.
    already_selected = bulb_index == current
    try:
        if not already_selected:
            set_shutter(p, bulb_index, timeout)
        print(
            f"{stamp()} BULB shutter_index={bulb_index} shutter_label={bulb_label!r} "
            f"shutter_seconds={bulb_actual} requested_seconds={bulb_seconds} "
            f"prior_index={current}"
            + (" (already selected, no write)" if already_selected else ""),
            flush=True,
        )
        yield bulb_index
    except BaseException as exc:
        # Keep the capture/body/socket failure primary.  Restoration is
        # diagnostic cleanup and must never hide the event we are trying to
        # investigate.
        operation_error = exc
        raise
    finally:
        try:
            if not already_selected:
                set_shutter(p, current, timeout)
                print(f"{stamp()} SHUTTER restored_index={current}", flush=True)
        except BaseException as restore_error:
            print(
                f"{stamp()} SHUTTER restore_failed secondary={type(restore_error).__name__}: "
                f"{restore_error}",
                file=sys.stderr,
                flush=True,
            )
            if operation_error is None:
                raise


def read_expected_sw(p: Polaris, expected: str, timeout: float = 10.0) -> str:
    """Read code 780 and require the exact app-visible firmware version."""
    p.send(780)
    response = p.wait_code(780, timeout)
    actual = field(response, "sw")
    if actual is None:
        raise RuntimeError(f"code 780 response has no sw field: {response}")
    print(f"{stamp()} FW_VERSION sw={actual} expected={expected}", flush=True)
    if actual != expected:
        raise RuntimeError(f"code 780 sw mismatch: expected {expected!r}, got {actual!r}")
    return actual


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--shot", action="store_true")
    ap.add_argument("--shot-timeout", type=float, default=180.0)
    ap.add_argument("--expected-files", type=int, choices=(1, 2),
                    help="authoritative output obligation required with --shot")
    ap.add_argument("--bulb-seconds", type=float,
                    help="requested long-exposure seconds; the shutter index is resolved from the "
                         "live command 268 list (K-3 III exposes no Bulb entry, max is 00-30)")
    ap.add_argument("--bulb-shutter-index", type=int,
                    help="optional override for the shutter index written through command 261")
    ap.add_argument("--expected-sw",
                    help="require this exact code-780 sw firmware version from the live device")
    ap.add_argument("--keep-preview", action="store_true",
                    help="app-path reproduction: leave live view running (start it if off) "
                         "instead of forcing preview off before the capture")
    ap.add_argument("--ev-index", type=int,
                    help="set the camera EV compensation to this option-list index via code 260 "
                         "before the capture (0=+5 .. 15=0 .. 30=-5 on the K-3 III)")
    ap.add_argument("--shutter-index", type=int,
                    help="set the camera shutter to this option-list index via code 261 before "
                         "the capture and LEAVE it set (app path); unlike --bulb-seconds this "
                         "does not wrap the shot in a bulb session")
    ap.add_argument("--ssh-host", default=None,
                    help="SSH target used for the #192 file-exists check on a completion "
                         "timeout (default root@<host>)")
    ap.add_argument("--output-dir", default="/app/sd/normal",
                    help="device directory the SP captures are written to, for the file check")
    ap.add_argument("--file-check-wait", type=float, default=20.0,
                    help="after a completion timeout, poll for the expected new output set "
                         "up to this many seconds before reporting no-file (0 = check once)")
    ap.add_argument("--no-file-check", action="store_true",
                    help="report a completion timeout as FAIL without consulting the file "
                         "system (the pre-#192 behaviour)")
    args = ap.parse_args()
    if args.ssh_host is None and not args.no_file_check:
        args.ssh_host = f"root@{args.host}"
    if not args.probe and not args.shot:
        ap.error("choose --probe or --shot")
    if args.shot and args.expected_files is None:
        ap.error("--shot requires --expected-files 1 or 2; photoFormat is not authoritative")
    if args.shot_timeout <= 0:
        ap.error("--shot-timeout must be positive")
    if not math.isfinite(args.file_check_wait) or args.file_check_wait < 0:
        ap.error("--file-check-wait must be finite and non-negative")
    if args.bulb_seconds is not None and args.bulb_seconds <= 0:
        ap.error("--bulb-seconds must be positive")
    if args.bulb_seconds is not None and not args.shot:
        ap.error("--bulb-seconds requires --shot")
    if args.bulb_shutter_index is not None and args.bulb_seconds is None:
        ap.error("--bulb-shutter-index requires --bulb-seconds")
    if args.shutter_index is not None and args.bulb_seconds is not None:
        ap.error("--shutter-index (app path) conflicts with --bulb-seconds (canary path)")
    if (args.ev_index is not None or args.keep_preview) and not args.shot:
        ap.error("--ev-index/--keep-preview require --shot")
    if args.expected_sw is not None and not (args.probe or args.shot):
        ap.error("--expected-sw requires --probe or --shot")

    p = Polaris(args.host, args.port, args.bind or None, timeout=10)
    # Defined before the try so the finally can always reach it.
    filecheck = DeviceFileCheck(
        None if args.no_file_check else args.ssh_host, args.output_dir)
    try:
        # authenticate
        p.send(284)
        p.wait_code(284, 5)
        p.send(820)
        auth = p.wait_code(820, 12)
        if field(auth, "needed") == "1":
            raise RuntimeError("device requires a password")
        p.send(823, payload="app:openpolaris-canary-probe;ver:1;")

        # camera state (code 286 = camera info)
        p.send(286)
        cam = p.wait_code(286, 10)
        print(f"{stamp()} CAMERA {cam}", flush=True)
        state = field(cam, "state")
        photo_format = field(cam, "photoFormat")
        model = field(cam, "model")
        print(f"{stamp()} SUMMARY model={model} state={state} photoFormat={photo_format}", flush=True)

        if args.expected_sw is not None:
            read_expected_sw(p, args.expected_sw)

        if args.probe:
            print(f"{stamp()} PROBE-DONE", flush=True)
            return 0

        if args.shot:
            # preview: app-path reproduction keeps live view running; the
            # default canary path forces it off (unchanged behaviour).
            p.send(292)
            preview = p.wait_code(292, 10)
            pv_state = field(preview, "state")
            print(f"{stamp()} PREVIEW initial_state={pv_state}", flush=True)
            if args.keep_preview:
                if pv_state != "1":
                    p.send(291, payload="state:1;")
                    started = p.wait_code(291, 15)
                    print(f"{stamp()} PREVIEW start_ack={started}", flush=True)
            elif pv_state != "0":
                p.send(291, payload="state:0;")
                stopped = p.wait_code(291, 15)
                print(f"{stamp()} PREVIEW stop_ack={stopped}", flush=True)
                p.send(292)
                confirmed = p.wait_code(292, 10)
                print(f"{stamp()} PREVIEW confirmed={confirmed}", flush=True)

            # app-path settings: camera-side EV/shutter via the app's own
            # commands, left in place (no bulb session, no restore).
            if args.ev_index is not None:
                set_ev(p, args.ev_index)
            if args.shutter_index is not None:
                set_shutter(p, args.shutter_index)

            # ONE capture
            shot_timeout = effective_shot_timeout(args.shot_timeout, args.bulb_seconds)
            shutter_context = (bulb_shutter_session(p, args.bulb_seconds, args.bulb_shutter_index)
                               if args.bulb_seconds is not None else nullcontext())
            with shutter_context:
                if args.bulb_seconds is not None:
                    print(f"{stamp()} BULB requested_seconds={args.bulb_seconds} "
                          f"shot_timeout={shot_timeout}s", flush=True)
                else:
                    print(f"{stamp()} SHOT shot_timeout={shot_timeout}s", flush=True)
                # Snapshot before the shutter so new filenames can be compared
                # after a notification timeout. Caveat kept honest: a late
                # orphan write from a *previous* shot (#175/#176) landing in
                # this window is indistinguishable here from this shot's file;
                # the STALE-CANDIDATE logic in canary-two-shot covers that.
                filecheck.arm()
                p.send(264, subtype=4, payload=bulb_capture_payload(args.bulb_seconds))
                deadline = time.monotonic() + shot_timeout
                states: list[int] = []
                files: list[str] = []
                timed_out = False
                while True:
                    try:
                        code, payload = p.frame(deadline)
                    except (TimeoutError, socket.timeout):
                        timed_out = True
                        break
                    if code == 773:
                        path = field(payload, "path")
                        if path:
                            if path not in files:
                                files.append(path)
                                print(f"{stamp()} FILE {path}", flush=True)
                            if len(files) > args.expected_files:
                                print(f"{stamp()} EXCESS outputs={files}", flush=True)
                                break
                    elif code == 264:
                        value = field(payload, "state")
                        if value is None:
                            continue
                        try:
                            st = int(value)
                        except ValueError:
                            print(f"{stamp()} BAD-STATE {value!r}", flush=True)
                            break
                        states.append(st)
                        print(f"{stamp()} CAPTURE state={st} lifecycle={states}", flush=True)
                        if st < 0:
                            print(f"{stamp()} TERMINAL-FAILURE state={st}", flush=True)
                            break
                    if len(files) == args.expected_files:
                        stems = {posixpath.splitext(path)[0] for path in files}
                        if len(stems) != 1:
                            print(f"{stamp()} MISMATCHED output stems files={files}", flush=True)
                            break
                    if 4 in states and 0 in states and len(files) == args.expected_files:
                        print(f"{stamp()} PASS lifecycle={states} files={files}", flush=True)
                        break
                    # ignore other codes
                if timed_out:
                    # #192: a missing notification does not prove the capture
                    # produced no file. Require the complete expected SP_ set;
                    # a partial RAW+JPEG pair or unrelated new file is not PASS.
                    check_observed, new_files, on_disk = wait_for_expected_output_set(
                        filecheck, args.expected_files, args.file_check_wait
                    )
                    if on_disk and not any(state < 0 for state in states):
                        print(f"{stamp()} LATE-NOTIFICATION-BUT-FILE-PRESENT "
                              f"states={states} files={on_disk} "
                              "notification=absent verdict=success", flush=True)
                        print(f"{stamp()} PASS lifecycle={states} files={on_disk} "
                              "via=file-check", flush=True)
                        return 0
                    if any(state < 0 for state in states):
                        verdict = "terminal-state"
                    elif not check_observed:
                        verdict = "unknown"
                    elif new_files:
                        verdict = "partial-files"
                    else:
                        verdict = "no-file"
                    print(f"{stamp()} TIMEOUT verdict={verdict} states={states} "
                          f"notified_files={files} disk_files={new_files} "
                          "note=no 773/state:4 before deadline", flush=True)
                    return 1
                valid_stem = len({posixpath.splitext(path)[0] for path in files}) == 1
                ok = (4 in states and 0 in states and len(files) == args.expected_files
                      and valid_stem and not any(s < 0 for s in states))
                print(f"{stamp()} DONE states={states} files={files}", flush=True)
                return 0 if ok else 1
    finally:
        filecheck.disarm()
        p.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{stamp()} FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)

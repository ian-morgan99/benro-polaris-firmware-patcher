#!/usr/bin/env python3
"""Host-only safety model for the unqualified Polaris axis-rate frame.

The exact `.73` app disassembly establishes only this static shape:
``AC 4A <axis> <little-endian IEEE-754 float>`` (7 bytes).  It does not
establish the MCU route, units, axis map, stop/torque semantics, or watchdog.
This module therefore never opens a socket and never sends a frame.  It is a
fault-injection harness for the host-side envelope that must exist before any
future firmware-backed implementation is considered.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass


PREFIX = b"\xac\x4a"
AXES = (1, 2, 3)
FRAME_SIZE = 7


class ProtocolError(ValueError):
    """A frame or command violates the known/static safety contract."""


def encode_frame(axis: int, rate: float) -> bytes:
    if axis not in AXES:
        raise ProtocolError("axis must be 1, 2 or 3")
    if not math.isfinite(rate):
        raise ProtocolError("rate must be finite")
    return PREFIX + bytes((axis,)) + struct.pack("<f", rate)


def decode_frame(frame: bytes) -> tuple[int, float]:
    if len(frame) != FRAME_SIZE:
        raise ProtocolError(f"expected {FRAME_SIZE} bytes, got {len(frame)}")
    if frame[:2] != PREFIX:
        raise ProtocolError("unexpected command prefix")
    axis = frame[2]
    if axis not in AXES:
        raise ProtocolError("unknown axis")
    rate = struct.unpack("<f", frame[3:])[0]
    if not math.isfinite(rate):
        raise ProtocolError("non-finite rate")
    return axis, rate


@dataclass
class SafetyState:
    rates: dict[int, float]
    last_update: float | None
    safe_stopped: bool
    reason: str


class RateSafety:
    """Fail-closed, host-only command envelope with watchdog and ramp limits."""

    def __init__(self, *, max_rate: float, max_accel: float, watchdog_s: float):
        if not all(math.isfinite(x) and x > 0 for x in (max_rate, max_accel, watchdog_s)):
            raise ValueError("limits must be finite and positive")
        self.max_rate = max_rate
        self.max_accel = max_accel
        self.watchdog_s = watchdog_s
        self.rates = {axis: 0.0 for axis in AXES}
        self.last_update: float | None = None
        self.safe_stopped = True
        self.reason = "initial"

    def state(self) -> SafetyState:
        return SafetyState(dict(self.rates), self.last_update, self.safe_stopped, self.reason)

    def request(self, frame: bytes, *, now: float) -> SafetyState:
        axis, rate = decode_frame(frame)
        if abs(rate) > self.max_rate:
            raise ProtocolError("requested rate exceeds host safety limit")
        if not math.isfinite(now):
            raise ValueError("time must be finite")
        if self.last_update is not None:
            dt = now - self.last_update
            if dt < 0:
                raise ValueError("time moved backwards")
            if abs(rate - self.rates[axis]) > self.max_accel * dt + 1e-12:
                raise ProtocolError("rate step exceeds host acceleration limit")
        self.rates[axis] = rate
        self.last_update = now
        self.safe_stopped = False
        self.reason = "commanded"
        return self.state()

    def tick(self, *, now: float) -> SafetyState:
        if not math.isfinite(now):
            raise ValueError("time must be finite")
        if self.last_update is None or now - self.last_update > self.watchdog_s:
            self.stop(reason="watchdog")
        return self.state()

    def stop(self, *, reason: str = "stop") -> SafetyState:
        self.rates = {axis: 0.0 for axis in AXES}
        self.safe_stopped = True
        self.reason = reason
        return self.state()

    def disconnect(self) -> SafetyState:
        return self.stop(reason="link-disconnect")


def _json_state(state: SafetyState) -> str:
    return json.dumps(
        {
            "rates": state.rates,
            "last_update": state.last_update,
            "safe_stopped": state.safe_stopped,
            "reason": state.reason,
        },
        sort_keys=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    dec = sub.add_parser("decode")
    dec.add_argument("hex_frame")
    sim = sub.add_parser("simulate")
    sim.add_argument("--axis", type=int, required=True)
    sim.add_argument("--rate", type=float, required=True)
    sim.add_argument("--now", type=float, default=0.0)
    sim.add_argument("--max-rate", type=float, default=1.0)
    sim.add_argument("--max-accel", type=float, default=10.0)
    sim.add_argument("--watchdog", type=float, default=0.5)
    sim.add_argument("--tick", type=float)
    args = parser.parse_args()
    if args.command == "decode":
        axis, rate = decode_frame(bytes.fromhex(args.hex_frame))
        print(json.dumps({"axis": axis, "rate": rate}, sort_keys=True))
        return 0
    safety = RateSafety(max_rate=args.max_rate, max_accel=args.max_accel, watchdog_s=args.watchdog)
    state = safety.request(encode_frame(args.axis, args.rate), now=args.now)
    if args.tick is not None:
        state = safety.tick(now=args.tick)
    print(_json_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

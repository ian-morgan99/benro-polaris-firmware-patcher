#!/usr/bin/env python3
"""Deterministic event recorder for Pentax/Polaris stability experiments.

This deliberately does not implement camera control. It provides a stable JSONL
schema that a Polaris-side test harness can call around the real pgphoto/libgphoto2
operations. Keep observation separate from control so instrumentation cannot
silently alter camera behaviour.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    run_id: str
    experiment: str
    event: str
    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    wall_time_ns: int = field(default_factory=time.time_ns)
    pid: int = field(default_factory=os.getpid)
    phase: str | None = None
    command: str | None = None
    camera_state: str | None = None
    session_state: str | None = None
    usb_fingerprint: str | None = None
    candidate_count: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


class Trace:
    def __init__(self, path: Path, experiment: str, run_id: str | None = None):
        self.path = path
        self.experiment = experiment
        self.run_id = run_id or str(uuid.uuid4())
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **kwargs: Any) -> Event:
        item = Event(
            run_id=self.run_id,
            experiment=self.experiment,
            event=event,
            **kwargs,
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(item), sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--event", required=True)
    parser.add_argument("--phase")
    parser.add_argument("--command")
    parser.add_argument("--camera-state")
    parser.add_argument("--session-state")
    parser.add_argument("--usb-fingerprint")
    parser.add_argument("--candidate-count", type=int)
    parser.add_argument("--details-json", default="{}")
    args = parser.parse_args()

    details = json.loads(args.details_json)
    if not isinstance(details, dict):
        raise SystemExit("--details-json must decode to an object")

    trace = Trace(args.out, args.experiment, args.run_id)
    event = trace.emit(
        args.event,
        phase=args.phase,
        command=args.command,
        camera_state=args.camera_state,
        session_state=args.session_state,
        usb_fingerprint=args.usb_fingerprint,
        candidate_count=args.candidate_count,
        details=details,
    )
    print(event.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

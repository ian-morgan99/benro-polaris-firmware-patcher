#!/usr/bin/env python3
"""Pair each 'will captureImage' attempt with the completion line that follows it.

Reports attempts that produced no completion line at all, which is the 61-vs-56
gap left open in docs/evidence/silent-capture-loss-20261126/FINDINGS.md.
Read-only over a captured log corpus; nothing here touches the rig.
"""
import re
import sys

ATTEMPT = "will captureImage"
COMPLETE = re.compile(r"captureImage ret -?\d+")
TS = re.compile(r"\[(\d\d:\d\d:\d\d:\d+)")


def main(path):
    lines = open(path, errors="replace").read().splitlines()
    attempts = []          # (idx, ts)
    for i, line in enumerate(lines):
        if ATTEMPT in line:
            m = TS.search(line)
            attempts.append((i, m.group(1) if m else "?"))

    unmatched = []
    for pos, (idx, ts) in enumerate(attempts):
        # The next attempt bounds this one's window.
        end = attempts[pos + 1][0] if pos + 1 < len(attempts) else len(lines)
        window = lines[idx:end]
        if not any(COMPLETE.search(w) for w in window):
            unmatched.append((idx, ts, end - idx))

    print(f"attempts   : {len(attempts)}")
    print(f"completions: {sum(1 for l in lines if COMPLETE.search(l))}")
    print(f"unmatched  : {len(unmatched)}")
    for idx, ts, span in unmatched:
        print(f"  line {idx:>7}  {ts}  window={span} lines to next attempt")
        # Show what the attempt was asked to capture and how its window ends.
        for w in lines[idx:idx + 1]:
            m = re.search(r"sPath:(\S+)", w)
            print(f"      requested: {m.group(1) if m else '(no sPath)'}")
        tail = [w for w in lines[max(idx, idx + span - 4):idx + span] if w.strip()]
        for w in tail[-2:]:
            print(f"      window end: {w[:110]}")


if __name__ == "__main__":
    main(sys.argv[1])

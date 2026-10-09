# 30-capture bulb soak on `.62` (2026-10-09, 14:05–14:12 UTC)

`canary-probe.py --shot --expected-files 2 --bulb-seconds 5 --expected-sw 6.0.0.54.62`
run 30 times back-to-back with 3 s between runs, dial on B.

**Result: 28/30 PASS, 2 consecutive FAIL (runs 23, 24).**

## 1. The 60-second stall is in the notification path, not the download

Two runs held `state:4` for **exactly 61.0 s** (runs 4 and 6). The device clock
is UTC+1, so the `cTime` in the 773 notification gives the time the file was
actually written:

| run | state:4 | file cTime (→UTC) | 773 notification | written at | notified at |
|---|---|---|---|---|---|
| 4 | 14:06:08 | 15:06:11 → 14:06:11 | 14:07:09 | **+3 s** | **+61 s** |
| 6 | 14:07:26 | 15:07:30 → 14:07:30 | 14:08:27 | **+4 s** | **+61 s** |

**The photo was on the card within 3–4 s, exactly as in the fast runs. Only the
notification was late — by ~58 s — and both stalls are 61.0 s to the second.**

That rules out my earlier guess (SD write or USB contention). A variable I/O
problem produces variable durations; two identical 61.0 s values with the file
already written is a **fixed ~60 s timeout expiring in the download/notification
path, after which the completion is reported normally and successfully.** The
capture is not slow. The client is told about it late.

Distribution of `state:4` holds across the 28 successful runs:
`2,2,2,2,3×15,4×6,6,61,61` — median 3 s, p95 4 s, then a hard jump to 61 s.
Rate: 2/28 ≈ 7%. There is no middle ground, which is what a timeout looks like
and not what a slow tail looks like.

## 2. Two consecutive runs got no reply to the first command

Runs 23 and 24 each sent `284` (preview/state query — the first thing the canary
does) and got **nothing back within 5 s**:

```
run-22  14:11:03  PASS  SP_0322
run-23  14:11:09  TX 1&284&2&-100#   → TimeoutError (no reply)
run-24  14:11:20  TX 1&284&2&-100#   → TimeoutError (no reply)
run-25  14:11:28  TX 1&284&2&-100#   → RX 284@mode:1;state:0;#  (recovers)
```

No capture was requested in either failed run — the daemon did not answer a
read-only state query for ~19 s, then answered normally and completed 6 more
captures. No crash artifact, no core file, and the runs either side are clean.

This is #182's exact failure mode (a capture-wedged daemon is invisible to the
USB-identity-only supervisor) and matches #181 (a request accepted then silently
lost). It is not the #190 crash: no segfault, no restart, self-recovered.

## 3. Post-soak: both service ports refuse connections

~37 min after the soak ended, the device answers `ping` (0 % loss, ~5 ms) but
**both port 22 and the control port 2653 refuse connections**. Not yet
diagnosed — no shell was available to check whether a service exited or the
device changed power/Wi-Fi state. Recorded because it is the same class of
symptom as #187 (unreachable service while the host is up).

## Implications for stability

- The dominant remaining risk is **not** capture failure. 28/30 captures that
  were attempted produced correct output, and the two stalls still wrote correct
  files.
- The two concrete defects are both **reporting/availability** faults: a fixed
  ~60 s notification delay, and a ~19 s window where the daemon does not answer
  at all.
- A client with any timeout under 60 s will report a successful capture as a
  failure ~7 % of the time. If it then retries, it takes a second photo the user
  did not ask for.

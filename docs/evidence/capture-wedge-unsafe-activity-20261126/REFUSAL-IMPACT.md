# Do admission refusals cause user-visible capture failures? Mostly no.

2026-11-26, K-1 II rig (v118). This answers the question I flagged as unmeasured in CORRECTION.md, and the
answer changes what should be fixed. Source: all 8 Clog files on the rig, 15,465,009 bytes / 193,387 lines,
streamed to `/tmp/rig_all.txt` for analysis (device has no python3 and no scp daemon; `ssh 'cat file'` works).

## Headline numbers

| measure | value |
|---|---|
| admission refusals | 348 |
| capture attempts logged | 59 |
| outcomes `ret 0` (success) | 20 |
| outcomes failed | 24 |
| failure codes | `-110`: 15, `-6`: 4, `-112`: 3, `-1`: 2 |

Minutes containing refusals: **83**. Minutes containing capture attempts: **43**. Overlap: **31**.

**52 of the 83 refusal minutes contain no capture attempt at all.** Those are contention on config and
preview paths — a control arriving while a native operation holds the gate, waiting ~1 s, and being refused.
The camera was genuinely busy (median hold 3026 ms against a ~1 s budget), so refusing is correct behaviour.

## The failures mostly are not refusals

Minutes with capture failures, split by whether any admission refusal occurred in that minute:

```text
failures with NO admission refusal in the minute:
  11:42  [-1]
  19:59  [-112, -110, -110]
  20:05  [-6, -6]
  20:21  [-6, -6, -112]
  20:22  [-110, -110]
  20:23  [-110, -110]
  20:24  [-110]

failures WITH refusals in the minute:
  12:05  [-110]            refusals=2
  12:26  [-110]            refusals=2
  12:29  [-1]              refusals=36
  12:31  [-112]            refusals=4
  12:35  [-110, -110, -110] refusals=6
  17:03  [-110]            refusals=3
  19:58  [-110]            refusals=5
  20:09  [-110]            refusals=2
```

**7 of 15 failure minutes have zero refusals.** The dominant user-visible failure is `-110` (15 of 24), which
is a retrieval/publication failure *after* the exposure was accepted — it never touches the admission gate.
`-6` (4) is the mode guard refusing timed bulb outside B, also not the gate.

So raising the budget or shortening the lease would fix almost none of what a user actually experiences.
That is worth stating plainly because "348 refusals, budget too small" is the obvious conclusion and it is
wrong.

## One aggregate I deliberately do not report as a finding

Bucketing failure rate by minute gives 21.4% in minutes with refusals versus 76.5% without. That is an
artifact of my own testing: the no-refusal high-failure minutes (20:21–20:24) are exactly when I was
deliberately triggering the camlib wedge, where every capture fails for reasons unrelated to admission. The
per-minute listing above is the honest view; the aggregate ratio is not a signal and should not be quoted.

## What this changes

- Do **not** tune `budget` or `stage2_camera_lease_ms` on the strength of refusal counts. The stage2 gate
  self-heals (proven at production values in commit 71eef93c) and most refusals are correct contention.
- The user-visible failure to chase is `-110`: exposure accepted, output never retrieved. That is #175/#270
  territory, not the locking work.
- The camlib `capture_output_pending` latch remains a real dead end (no timer, three clear paths all needing
  a successful capture cycle), but on this rig it is a *consequence* of a failed capture rather than the
  first cause: the sequence is `-110` -> latch -> every later capture refused.

## Caveats

Correlating refusals to minutes uses the nearest following timestamp, because `[stage2]` lines carry none;
a refusal can therefore be attributed to the minute after the one it belongs to. Log lines are also truncated
mid-line by the device logger in places. Neither affects the central observation — that most failure minutes
contain no refusal at all — since that requires only the absence of refusals, which is robust to a one-minute
skew.

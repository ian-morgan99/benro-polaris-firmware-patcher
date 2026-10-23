# K-1 II session report — 2026-10-23 (logged, not yet worked)

Logged on request so the session is not lost. **Deliberately deferred**: the K-3 III
Bulb investigation (`docs/evidence/bulb40s-20261023/SUMMARY.md`) finishes first.

## Log capture — mostly lost again, for the same known reason

The user asked for Mlog/Clog "whilst it is fresh". What actually survived:

| artifact | state |
|---|---|
| `/app/Mlog.txt` | 18,925 bytes captured → `out/k1ii-mmode-20261023/Mlog-snapshot.txt` (250 lines) |
| `/app/Clog.txt` | **0 bytes**, truncated at 19:58 by the pgphoto restart |
| live capture | started immediately after, `Mlog-live.txt` (840 KB), `Clog-live.txt` (0 B) |

The snapshot contains **only polling chatter** — `code:284` ×49 and `code:517` ×49,
nothing else. No capture, no control writes, no errors. The user's actual test traffic
predates the 19:58 truncation, so it is gone. This is exactly **issue #213** ("Mlog/Clog
retain ~30 s and are truncated at boot, so no failure can be diagnosed after the fact")
biting a second time, now on a body-swap rather than a boot.

## The K-1 II is not currently attached — needs resolving before any diagnosis

Enumerated USB devices at 18:59Z (host) / 19:59 (device clock):

```
 8 1a40:0101 USB2.0 HUB
 1 1d6b:0002 xHCI Host Controller
 1 1d6b:0003 xHCI Host Controller
11 25fb:0189 PENTAX K-3 Mark III
```

- **No `25fb:0183`** (K-1 II PTP) and **no `25fb:0182`** (K-1 II MSC).
- `/sys/block/` shows only the Polaris's own `mmcblk0`/`mtdblock*` — **no MSC block
  device**, so no body was presenting as mass storage at that moment.
- Interface classes present: one `06` (PTP) and three `09` (hub). No `08` (mass storage).
- Note on driver state, corrected after a first wrong reading: `grep usb_storage
  /proc/modules` returns nothing, but `/sys/bus/usb/drivers/` *does* list a
  `usb-storage` directory while `/sys/module/usb-storage` does not exist. Whether it is
  built-in or merely registered is unresolved; the loadable-module check alone is not
  evidence (see [`../ipolar-20261023/SUMMARY.md`](../ipolar-20261023/SUMMARY.md), where
  the same mistake was made about `uvcvideo`). The observable fact used here is simply
  that no block device appeared.
- Live capture since 19:58 contains **zero** `k-1 mark ii` sightings; models seen are
  only `none` and `pentax k-3 mark iii`.

So the reported session cannot be reproduced from the current rig state. Two candidate
explanations, neither yet tested:

1. The body was swapped back to the K-3 III (or dropped off the bus) before I probed.
   The 19:58 pgphoto restart is consistent with a swap event around then.
2. "M mode" means **mass-storage**, in which case per the corrected finding in
   `docs/evidence/k1ii-pid-0182-20261006/SUMMARY.md`: *"A body in MSC mode has no PTP
   interface to talk to… the remedy is the camera's USB mode setting, and the `0182`
   sighting is a usage fault, not a code fault."* That document also records that a
   `0182` attachment autodetected to **zero** cameras and the host then silently fell
   back to hardcoded `Pentax K-3 Mark III (MTP mode)` abilities — which would make an
   MSC-mode body look exactly like a working K-3 III.

Note the K-1 II *does* bind correctly sometimes: the two-shot harness logged
`model=pentax k-1 mark ii state=1 photoFormat=1` at 16:36Z today. So this is not a
permanent binding failure.

## Reported symptoms (user, K-1 II in "M mode")

| # | symptom | notes / prior art |
|---|---|---|
| 1 | Preview works | Only symptom that behaves. |
| 2 | Setting values is very slow | Unquantified. Needs a timed write trace (261/260) to separate camera-side settle from transport. |
| 3 | Focus controls do not seem to work | No focus command found in `scripts/canary-probe.py`; unclear whether the app path issues one at all. |
| 4 | Everything is very laggy | Likely same root cause as #2. |
| 5 | Shows "image is processing" while it should be exposing; did not expose; returned "shot failed" | Same signature as the K-3 III Bulb failure — status text appears to assume wall time ≈ exposure. |
| 6 | No EV setting | EV compensation is command **260** (`ev:<index>;`, `canary-probe.py:717`, observed applying in 66 ms on K-3 III). Absent here suggests a per-body capability gap, not a transport fault. |

Symptoms 5 and 6 line up with existing open issues rather than being new:

- **#217** — "K-1 II has no qualification evidence on any build since .65". This session
  is the first K-1 II contact since then and produced no usable logs.
- **#213** — log retention, which destroyed this session's evidence.
- **#218** — pgphoto logs every capture duration as negative, so a success is
  indistinguishable from a timeout in Mlog. Relevant to symptom 5: `capture end -83117 ms`
  was seen on the K-3 III for a *successful* 40 s exposure, so negative durations cannot
  be read as failures.
- **#219** — Android and iPhone report different capability lists for the same body.
  Symptom 6 (no EV) may be the same class of defect on a third body.

## What is needed to actually diagnose this

1. Reconnect the K-1 II and confirm it enumerates as `25fb:0183`. If it shows `0182`,
   switch the camera's USB mode setting — that is a usage fix, not a code fix (#179).
2. Start the host-side log capture **before** testing (it appends every 3 s and survives
   Clog truncation):
   ```bash
   export PATH="$PWD/tools/host-bin:$PATH"
   mkdir -p out/k1ii-$(date +%Y%m%d)
   while true; do ssh root@192.168.0.1 'cat /app/Mlog.txt' >> out/k1ii-$(date +%Y%m%d)/Mlog-live.txt; \
                 ssh root@192.168.0.1 'cat /app/Clog.txt' >> out/k1ii-$(date +%Y%m%d)/Clog-live.txt; sleep 3; done
   ```
3. Then reproduce each symptom once, in order: one value write (timed), one focus
   attempt, one short capture. With capture running from before the test, the writes and
   the failure state will actually be on disk.

## Artifacts

- `out/k1ii-mmode-20261023/Mlog-snapshot.txt` — 250 lines, polling only
- `out/k1ii-mmode-20261023/Mlog-live.txt` — 840 KB from 19:58 onward, no K-1 II traffic
- `out/k1ii-mmode-20261023/Clog-live.txt` — 0 bytes (driver log truncated at swap)

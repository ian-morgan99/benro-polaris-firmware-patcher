# Regression trail — 2026-10-23, `6.0.0.54.69`

Purpose: a single clear record of **what was tried, on which body, on which version**,
so later sessions can tell what is already known rather than re-testing blind.

Provenance of the build under test (verified, not inferred):

| field | value |
|---|---|
| `FwVer` on device | `6.0.0.54.69;date:2026.10.23` |
| patcher commit | `437e0d3fac284ef8b1502d58bd4336e0bbff5ec8` |
| libgphoto2 commit | `731d7fbd5b5c590490f2783dd549762fc5dc3b9d` |
| installed `ptp2.so` | `748b00f698aa` — matches the candidate byte-for-byte |

`.69`'s only behavioural change is libgphoto2 `23008c229` (`camlibs/ptp2/pentax-utils.c`,
dark-frame budget). `.68`→`.69` differs in loader + `ptp2.so`; `pentax.so` and the
`pgphoto` wrapper are unchanged.

## Summary of every body tried today

| body | state | what worked | what failed | evidence |
|---|---|---|---|---|
| **K-3 III** (`25fb:0189`) | qualified | two-shot GREEN 14/14; 30/40/50 s timed captures all PASS | app-side Bulb at 30 s and 40 s → "shot failed" | `bulb40s-20261023/` |
| **K-1 II** (`25fb:0183`) | not reproducible | preview only, per user report | slow writes, no focus, no EV, capture failed | `k1ii-mmode-20261023/` |
| **K-01** | model recognised, JPEG reported | recognition + format readout | nothing further attempted by user | `k01-regression-20261023/` |
| **iOptron iPolar** (`1233:1455`) | not recognised | — | nothing; device never surfaced | `ipolar-20261023/` |

## K-3 III — qualified for timed capture, Bulb path still open

Passing on `.69`:

```
--two-shot --expected-files 1  →  14 passed, 0 failed, 0 skipped
SHOT1 FILE /app/sd/normal/SP_0406.dng
SHOT2 FILE /app/sd/normal/SP_0407.dng
```

Timed captures, with measured wall time (exposure + dark frame):

| requested | state 1 → 4 | wall | pre-`.69` budget (`exp+30`) | result |
|---|---|---|---|---|
| 30 s | 18:41:47 → 18:42:50 | **63.5 s** | 60 s — too short | PASS `SP_0413.dng` |
| 40 s | 18:29:37 → 18:30:59 | **82.4 s** | 71 s — too short | PASS `SP_0410.dng` |
| 50 s | 18:31:36 → 18:33:18 | **102.6 s** | 80 s — too short | PASS `SP_0411.dng` |

Clog corroborates the dark frame independently: `capture_image[3164]:----capture end
-83117 ms` for the 40 s shot. (Per issue #218 that negative duration is a logging bug —
it does **not** mean failure; this capture passed.)

Still open: the **app-side Bulb** path fails at roughly the *requested* duration, which
matches neither budget (old `exp+30`, new `2·exp+30`). See
[`bulb40s-20261023/SUMMARY.md`](bulb40s-20261023/SUMMARY.md) for the reproduction, the
dial-state confound that currently blocks it, and the app-side-timer hypothesis.

## K-1 II — reported working only for preview; no usable logs

User report (body in "M mode"): preview works; setting values very slow; focus controls
do nothing; everything laggy; **no EV setting**; capture showed "image is processing"
while it should have been exposing, never exposed, returned "shot failed".

Device state when I probed: **the K-1 II was not attached.** Only `25fb:0189` (K-3 III)
was enumerated; no `0183`, no `0182`, and `usb_storage` is not even loaded. The earlier
two-shot harness *had* seen it correctly at 16:36Z (`model=pentax k-1 mark ii
state=1 photoFormat=1`), so the binding works when the body is present.

Evidence was lost to the same truncation as always (issue #213): Clog 0 bytes, Mlog
rotated to polling-only chatter before I could read it. Details and the capture-before-
test procedure in [`k1ii-mmode-20261023/SUMMARY.md`](k1ii-mmode-20261023/SUMMARY.md).

Cross-reference: "no EV" may be the same capability-list defect as **#219** (Android and
iPhone report different capability lists for the same body). EV compensation is command
**260** (`ev:<index>;`), which applies in 66 ms on the K-3 III — so absence here looks
like a per-body capability gap, not transport.

## K-01 — model recognised and JPEG format reported; nothing further attempted

User's regression test on `.69`. Outcome as reported:

- **Recognised** — the app identifies the model.
- **Format readout works** — reports it is using JPEG settings.
- Nothing else was attempted; the user judged there may be nothing more to expect from
  this hardware.

That is a **positive result for recognition and format readout**, and it is not a
regression: those two paths work on `.69`.

What this does *not* establish, because it was not tested: capture, control writes,
preview, EV, focus. So K-01 remains **unqualified beyond recognition/format**, consistent
with the standing position in `docs/HANDOVER-2026-09-24-O-V12N-AUDIT.md:34`:

> `| K-01 still capture | UNSUPPORTED / NOT QUALIFIED | one request returned -6 promptly; no crash |`

Two things worth recording so this isn't re-litigated:

1. **K-01 is two separate code paths**, per `docs/PENTAX_GENERIC_CONTROL_COMPATIBILITY.md:30`:
   legacy `25fb:0130` USB-SCSI (`camlibs/pentax`) and `25fb:0131` generic PTP/MTP
   (`ptp2`). The Stage-2 package centres on `ptp2`. Which PID the body presented today
   was **not captured**, so we cannot say which path served it.
2. **No device-side evidence exists for this session.** My continuous capture (3 s
   polling, host-side append) was running and contains **zero** K-01 sightings — models
   seen were only `none` and `pentax k-3 mark iii`. The 53 apparent `0130`/`0131` hits in
   the log are coincidental digits inside IMU pitch values
   (`pitch:0.760130`), not USB product IDs. The body was already unplugged when I probed,
   and `/sys/bus/usb/devices/` showed no Pentax at all.

So the K-01 result rests on the user's observation alone. If it needs to be verifiable,
reconnect it and run:

```bash
export PATH="$PWD/tools/host-bin:$PATH"
# which path did it present? 0130 = USB-SCSI/legacy, 0131 = PTP/MTP
ssh root@192.168.0.1 'for d in /sys/bus/usb/devices/*/idProduct; do v=$(dirname $d); \
  echo "$(cat $v/idVendor):$(cat $d) $(cat $v/product 2>/dev/null)"; done'
python3 scripts/canary-probe.py --probe          # model + photoFormat as the driver sees it
```

## iOptron iPolar — not recognised, and that is unimplemented scope

User plugged an iPolar in; nothing recognised it. The device was already unplugged when
I probed, so the kernel-side binding for that session is **unverified**.

What is established about the host, independent of the device:

| check | result |
|---|---|
| `/sys/module/uvcvideo/` | present, version `1.1.1`, params `clock/hwtimestamps/nodrop/quirks` |
| `/sys/bus/usb/drivers/uvcvideo/` | registered with `bind`/`new_id`/`remove_id` |
| `/proc/devices` char 81 | `81 video4linux` — V4L2 core present |
| `/dev/video*` | none (nothing attached at probe time) |
| kernel | `4.9.37`; `modprobe` unusable (`/lib/modules` absent) |

I first reported the UVC driver as missing from `grep uvc /proc/modules` → 0. That was
**wrong**: `/proc/modules` lists loadable modules only, not built-ins. Corrected in
[`ipolar-20261023/SUMMARY.md`](ipolar-20261023/SUMMARY.md).

Why non-recognition is expected: `docs/IPOLAR-UVC-BACKEND-PLAN.md` (#159) states that
`patch.sh` only compile-checks the adapter and frame store and **no runtime camera-source
consumer calls them**. So even with `/dev/video*` created, nothing surfaces the device to
Benro Connect. This is **unimplemented scope, not a `.69` regression**.

Still unanswered on hardware (open item #1 of that plan): does attaching the iPolar create
`/dev/video*` on this kernel? Needs the device plugged in — command is in that summary.

## Standing caveat on every row above

`photoFormat` is **not** authoritative for output count — `canary-probe.py:882` and
`CURRENT-STATE.md:710` both say so, and I reasoned past that warning earlier today.
Output counts in this trail were established from files actually written, never from
that field.

## Related open issues

| # | relevance |
|---|---|
| #213 | Mlog/Clog retain ~30 s and truncate at restart — destroyed evidence for all three sessions today |
| #217 | K-1 II has no qualification evidence since `.65`; today added no usable evidence |
| #218 | pgphoto logs every capture duration as negative — a pass looks like a timeout |
| #219 | Android/iPhone capability-list divergence — likely the same class as "no EV" on K-1 II |
| #221 | `.69` provenance and why the canary failure was not the budget change |

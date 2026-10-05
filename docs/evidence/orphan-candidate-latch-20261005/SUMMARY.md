# The `-110` wedge is self-inflicted: the pre-shutter gate latches on an orphan candidate

Date: 2026-10-05. Device: Polaris @ 192.168.0.1, firmware `6.0.0.54.55`
(o-v15r). Camera: Pentax K-3 III Mark III, RAW+JPEG, Manual mode.

## 1. What was observed

A plain Manual canary shot (`--shot --expected-files 1`, no Bulb) failed
immediately:

```
TX 1&264&4&state:1;bulb:0;c:-1;#
RX 264@state:1#
RX 264@state:-1005#
```

The device's own `Clog_000249.log` shows the shutter was never fired:

```
[pentax] capture=2 boundary=preconditions-return ptp=0x2001 size=576
[pentax-recovery] capture=2 path=recovery-probe reason=transfer-candidate-available
    ptp=0x2001 size=576 field32=0x00000001 field36=0x00000001 field104=0x00000000
    accepted=0 action=recover-output-with-ownership;preserve-candidate
ERROR: Could not capture image.
[18:52:35] capture_image[3096]:----ARG_CAPTURE_IMAGE  -110
```

There is no `boundary=initiate-enter` line, so `PTP_InitiateCapture` was never
sent. The camera was idle and healthy; **our own admission gate refused the
shot.**

## 2. The sequence that produces the latch

From the same log, with the file listing on `/app/sd/normal` as corroboration:

| time  | event | file on disk |
|-------|-------|--------------|
| 16:29:23 | SP_0224 captures cleanly, `state:3` for both `.dng` and `.jpg` | SP_0224.* present |
| 18:50:02 | SP_0225 `boundary=initiate-enter` → `initiate-return ptp=0x2001` (accepted) | **never written** |
| 18:50:42+ | every later request blocked pre-shutter, `field32=1 field36=1` | — |
| 18:52:35 | SP_0226 blocked pre-shutter → `-110` | — |
| 19:12:37 | SP_0227 blocked at recovery-probe → `-110` | — |

`SP_0225.dng`/`.jpg` do not exist in `/app/sd/normal` (last real file is
SP_0224, 16:29). So the capture at 18:50 was accepted by the body, the
Polaris process lost it mid-retrieval, and the image handle stayed in the
camera's object-creation-info list.

`pentax_admission_block_reason()` (`camlibs/ptp2/pentax-utils.c`) then returns
`PENTAX_ADMISSION_BLOCK_TRANSFER_CANDIDATE_AVAILABLE` purely from `+32 == 1`,
and every subsequent capture is refused.

## 3. The defect: the prescribed recovery is never performed

`pentax_admission_recovery_action()` returns the string
`"recover-output-with-ownership"` for exactly this reason, and the log line
prints it. Grepping the driver for any code that implements it:

```
$ grep -n "recover-output-with-ownership" camlibs/ptp2/*
pentax-utils.c:201:  return "recover-output-with-ownership";   <- the string only
```

It appears **only** as a log/diagnostic string. There is no function that
downloads or deletes the orphan, and `capture_output_pending` is only ever set
by our own capture path (library.c:6764, 7226) — never from a pre-existing
device-side candidate. The gate therefore has no exit:

* the candidate is (correctly) never consumed or deleted, because it has no
  generation id and might belong to an earlier session;
* nothing ever claims it;
* `+32` stays `1` until the camera drops the object, which in practice only a
  power cycle does.

This is the mechanism behind the long-standing reports in #160, #172 and #163:
"one shot works, then everything returns `-110` until the camera is restarted".
It also explains the user's observation that a second trigger while the first
capture is still in progress is what breaks the run — that is precisely how the
orphan is created.

## 4. Consequences for the current work

1. The `-110` is **not** a PTP transport wedge and not a camera fault. It is a
   policy deadlock in our Stage-2 patch.
2. The EXIF verification for #173 cannot be run behind this latch, which is why
   the 261 shutter test in `bulb-root-cause-20261005` could not be completed.
3. "Preserve the candidate" is the right instinct but is incomplete on its own:
   preserving without ever recovering converts one lost frame into a permanently
   dead camera session.

## 5. Proposed fix (see issue #175)

Give the recovery an owner. On a pre-shutter block whose reason is
`transfer-candidate-available` / `selector-present`, and only when this process
has no capture of its own in flight:

1. enumerate the object list once and take the handle(s) present *before* the
   new shutter (the baseline is already read here — `bdata + 32/36`);
2. claim them by downloading to a recovery path derived from the requested
   output name (e.g. `SP_0226-orphan-1.dng`), so the file is preserved, not
   deleted;
3. delete the object only after a successful, verified download;
4. re-probe conditions once; if `+32`/`+36` are now clear, continue to
   `InitiateCapture` in the same call rather than returning `-110`;
5. if the download fails, keep the current fail-closed behaviour and return
   `-110` — never shoot over an unrecovered candidate.

Ownership is "proven" by the download succeeding into a path we created, which
is the same standard the current comment text demands, just actually enforced.

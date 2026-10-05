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

## 6. As-built fix (libgphoto2 `e65404f5f`, carried by o-v15s / `6.0.0.54.56`)

Implemented differently from §5 in two respects, both deliberate:

1. **Reuse over a new loop.** The claim reuses `pentax_reconcile_extra_candidates()`
   — the same bounded (≤4 objects, ≤30 s) transfer → publish → delete machinery
   already proven by dual-format reconciliation (#73). Only the ownership
   predicate differs. A separate download-to-`-orphan-1` path would have been a
   second transfer implementation to trust.
2. **Preservation is by publishing under the candidate's own name**, not by
   renaming. `pentax_reconcile_transfer_candidate()` reads the candidate's
   filename while the object still exists, writes the bytes into the camera
   filesystem (collision-free: it probes for an existing name first), and only
   then deletes the PTP object. The frame therefore lands on the Polaris SD
   under its original name. If the name cannot be read, the transfer returns
   `GP_ERROR_CORRUPTED_DATA` and the object is **kept** — we never delete what
   we could not publish.

Claimability is decided once, before the loop, by
`pentax_orphan_candidate_claimable()` (`pentax-utils.c`): a candidate-bearing
admission reason, **and** `capture_output_pending == 0`, **and** a non-zero
handle. `OUTPUT_UNRESOLVED` is excluded because it is derived only from our own
pending flag — that is our capture, not an orphan. Both admission sites
(recovery-probe and pre-shutter baseline) now claim → re-probe from one fresh
conditions frame → decide, so a single refusal can no longer be terminal.

A failed claim leaves the object in place and the fail-closed `-110` intact.

**Assumption not yet verified on hardware:** after a successful claim the
function clears `pentax_capture_publications_clear()` and zeroes
`extra_capture_count`, so an orphan is not reported as the *next* capture's
output. The rationale is that the Polaris app reads images from the camera SD
rather than through `gp_camera_file_get()`. If that assumption is wrong the
symptom would be a missing file event for the capture *following* a recovery —
which is exactly what step 3 of the acceptance test below watches for.

## 7. Acceptance test (blocked on hardware)

The device must first be power-cycled: it is latched on SP_0228 and, before
this fix, nothing short of a power cycle cleared it. As of 2026-10-05 19:53 the
camera is additionally USB-detached (`286` reports `manufacturer:none
state:-5`; `dmesg` shows `usb 1-1.2: USB disconnect`; a software re-bind of the
hub enumerates 4 ports but nothing downstream), so a physical reseat is needed
too.

1. **Identity.** `python3 scripts/canary-probe.py --probe --expected-sw 6.0.0.54.56`
   — proves the flashed build is the one under test, not a stale install.
2. **The regression itself.** Five consecutive Manual captures in **one**
   session, no reconnect, no pgphoto restart, no re-plug:
   `python3 scripts/canary-two-shot.py --expected-files 1 --expected-sp-prefix /app/sd/normal/SP_ --shot-count 5 --expected-sw 6.0.0.54.56`
   Pass = five distinct new `SP_` paths, each `state:1 → 4 → 0`, no negative
   state, no repeated path. Before the fix this died at shot 2 (or at shot 1 of
   the *next* session) with `state:-1005`.
3. **Recovery must not steal the next frame.** After any capture that logs
   `path=orphan-recovery outcome=cleared`, the *following* capture must still
   produce its own new file. A missing 773 event there falsifies the
   publication-clearing assumption in §6.
4. **Then #173.** Only once 1–3 pass can the Bulb EXIF test in
   `docs/evidence/bulb-root-cause-20261005/SUMMARY.md` §5 be run; it was
   blocked behind this latch.

The harness changes in this commit (`--shot-count`, `--expected-sw`, and the
three new sequence tests) exist so that steps 1–3 are one command and so that
"the second capture is where it breaks" is a case the offline suite models.

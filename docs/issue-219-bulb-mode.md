
## 2026-10-23: measured wall time is roughly TWICE the requested duration (refines the app-side gate)

New measurement, not previously on this thread. On `.69` with the K-3 III, via the normal
timed path (`--timed-seconds`), state `1 → 4`:

| requested | wall time | ratio |
|---|---|---|
| 30 s | **63.5 s** | 2.1× |
| 40 s | **82.4 s** | 2.1× |
| 50 s | **102.6 s** | 2.1× |

Clog corroborates independently: `capture_image[3164]:----capture end -83117 ms` for the
40 s shot (per #218 that negative sign is a logging bug and does not mean failure — all
three passed, files on card).

Why this matters to the open question above. The user's app-side failures land at roughly
the **requested** duration ("after around 40s", and again at 30 s), while the body needs
about **twice** that because long-exposure noise reduction appends a dark frame of its own.
So an app-side gate that assumes wall time ≈ exposure would declare "shot failed" while the
camera is legitimately still working — which matches the reported sequence exactly:
"image is processing" during what should be the exposure, then failure, then recovery
shortly afterwards once the dark frame lands.

This does not change the conclusion that the `-6` is decided in the app before libgphoto2;
it supplies a concrete timing signature to test against. A falsifiable check: instrument
the elapsed time at which the app gives up versus the elapsed time at which the file
appears, for one 30 s capture. If give-up ≈ 30 s and file ≈ 63 s, the gate is duration-
naive.

Also verified today so nobody chases it as a bug: **`exposure_phase_ms` in libgphoto2 is
diagnostic only.** All 15 references in `camlibs/ptp2/library.c` are assignment, clamping,
or logging (`GP_LOG_D` at 7299, `GP_LOG_E` at 7379). The capture wait loop is bounded by
`capture_timeout_ms` alone — `} while (waiting_for_timeout (&back_off_wait, started,
capture_timeout_ms));` at line 7358. So the dark-frame budget added in libgphoto2 `23008c229`
governs pgphoto's wait correctly, and there is no second timer inside the camlib that could
produce a ~duration failure.

Evidence: [`evidence/bulb40s-20261023/SUMMARY.md`](evidence/bulb40s-20261023/SUMMARY.md),
[`evidence/regression-trail-20261023.md`](evidence/regression-trail-20261023.md).

## 2026-10-21 evening: the -6 is decided in the APP, before libgphoto2 (fresh battery)

Battery went flat mid-session; replaced. Camera re-enumerated on USB as
`25fb:0189 PENTAX K-3 Mark III` (`/sys/bus/usb/devices/1-1.2`, node
`/dev/bus/usb/001/007`). Grip did NOT reboot (`/proc/uptime` 23928 s), so the patch
stayed live throughout (boundary markers 72 -> 74).

With a healthy rig, one request each:

| Path | Lifecycle | File | `boundary=camlib-enter` in Clog delta |
|---|---|---|---|
| Timed (`b` field absent) | `1 -> 4 -> 0` | `SP_0390.dng` | **present** |
| Bulb (`b:5`, camera-timed bulb) | `1 -> -6` (same second) | none | **absent** |

Two conclusions, both load-bearing:

1. **The battery was not the confound.** Timed capture works end-to-end on the same
   rig minutes later. The `-6` is specific to the bulb path.
2. **The app rejects bulb before reaching the library.** No `camlib-enter` marker in
   the byte-offset delta of `Clog_000299.log`, and no `boundary=camlib-exit`. So the
   failure is an application-side branch in the 264 handler, not a libgphoto2 return
   code. My library patch cannot be what "fixes" bulb, and cannot be what breaks it.

### Reversal test: NEGATIVE (hypothesis refuted as stated)

The hypothesis was that the patch removes the library's `Camera-timed Bulb is active`
refusal, so an unpatched grip would return `-6` in camera-timed mode. Instead the
**patched** grip returns `-6` in camera-timed mode too. The `-6` therefore does not
come from the removed check.

### New leading hypothesis: an app-side gate on the dial/mode

`out/dial-check.py` reads the live shooting-mode list (codes 284 + 517):

```
DIAL-EVIDENCE entries=56 current_index=0 collapsed=False
  SHAPE: full 56-entry list -> consistent with a TIMED dial, NOT B
```

Bulb requests succeeded earlier today (`SP_0382`-`SP_0386`, 5/5) when the dial was
physically on **BULB**; they return `-6` now that the mode list is a full 56-entry
timed list. That is consistent with the app gating bulb requests on the current
shooting mode -- i.e. the `-6` may be *correct* behaviour for a non-B dial, and the
real question is what the app does when a bulb capture is requested while the dial is
on B but the camera reports a camera-timed exposure.

**Open test:** dial physically on B + `--bulb-seconds N`. PASS there means `-6` is a
mode gate, not a defect; FAIL there means a genuine bug in the 264 handler.

### Method note (a bug worth not repeating)

The first reversal run silently produced no Clog delta: `ls -C /app/sd/system/log/Clog_*`
emitted multi-column output, so the filename/size split yielded `2920\n1144269` and the
arithmetic failed (`bash: arithmetic syntax error`). Use `ls -1`, and assert the offset
is a single integer before computing `tail -c +N`.

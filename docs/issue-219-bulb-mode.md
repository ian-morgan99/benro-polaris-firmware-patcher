
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

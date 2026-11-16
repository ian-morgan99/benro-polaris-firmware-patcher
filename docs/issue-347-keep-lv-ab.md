# Does keeping live view on cause the K-3 III to fall off USB? (issue #347)

**Status:** scripted — `scripts/keep-lv-ab.py`. Not yet run.

```
scripts/keep-lv-ab.py --plan                                  # touches nothing
scripts/keep-lv-ab.py --host 192.168.0.1 --i-am-present --confirm-move
scripts/keep-lv-ab.py --analyze-only docs/evidence/<bundle>    # re-score offline
```

It moves the mount, so it refuses to run without both confirmation flags. Evidence
(dmesg first, then Mlog/Clog) is captured per run into `docs/evidence/`.

Before this was possible at all, `STAGE2_PENTAX_KEEP_LV` could not be changed on a
running device: the loader reads it at `gp_camera_init` and advertises
"set STAGE2_PENTAX_KEEP_LV=0 to A/B", but pgphoto is launched by the vendor watchdog
with a fixed environment, so there was no caller to export it from. The wrapper now
reads that one allowlisted key from `/var/run/openpolaris-stage2.env` (grepped, not
sourced; value must be 0 or 1; applied value logged on every start).

## Why this test exists

`STAGE2_PENTAX_KEEP_LV` defaults **on**. It tells the driver to leave Pentax PC live
view switched on between preview requests instead of turning it off after each one.
It was turned on by default in `08a8730` (2026-09-10) to stop preview churn starving
the **Wi-Fi radio** (issues #36/#55). It was never evaluated against USB stability,
and the driver itself calls the toggle a "research harness".

Two things make it worth testing now:

1. **Issue #86 is direct precedent.** On the K-1 II, an empty frame reply (`0x2002`
   with zero bytes) was treated as fatal, which tore live view down immediately —
   and *that took the camera off USB*. Fixed by retrying instead of tearing down.
   So "live view teardown takes a Pentax off USB" is a fault class we have already
   confirmed once, on a different body.
2. **The one fatal loss in session 34 happened mid-stream.** The last thing pgphoto
   logged before the kernel removed the device was its 63rd consecutive preview
   frame. Every earlier preview burst (1–16 frames, with idle gaps) survived, and
   motor load on its own survived too. Sustained streaming plus motor load is the
   only combination that has ever failed.

## What to run

Same body both times (**K-3 III** — PC live view does not exist on other bodies),
same starting charge, camera attached after Polaris boots (that is how every
captured session has run).

| Run | Setting | Action |
|---|---|---|
| A | `STAGE2_PENTAX_KEEP_LV=1` (current default) | Start preview, let it stream steadily, then start a goto slew. Keep both running ~2 min. |
| B | `STAGE2_PENTAX_KEEP_LV=0` | Identical sequence. |

Repeat each at least 3 times. One success in condition B is not proof; three is
reasonable.

Set it in the pgphoto wrapper environment before pgphoto starts — the C loader reads
`STAGE2_*`, not `OPENPOLARIS_*`.

## What to record for every run

- Whether the camera survived, and if not, the timestamp.
- `dmesg | grep -iE "usb|xhci|hub" | tail -40` **immediately**, before the ring buffer
  rolls. This is the evidence we have never had — see `e21e90d`, which now dumps it
  automatically on loss, so also grab `[camera-usb] usb-evidence:` lines from the
  supervisor log.
- Whether the kernel removal uevent stream was complete (six lines: interfaces then
  device) or truncated (two). Both fatal losses were truncated; that is currently our
  best physical clue.
- Preview frame count and cadence just before any loss, from Clog
  (`Pentax preview stage get-frame`).

## How to read the result

| Result | Conclusion | Next step |
|---|---|---|
| A fails, B survives repeatedly | keep-LV is implicated | Implement idle live-view release properly — see R2 in `docs/issue-camera-idle-power-drain.md`. It must go at the session-ownership layer, **not** as a process-global timer in `stage2_loader.c` (#147 forbids that; a naive version was already tried and rejected). |
| Both survive | sustained streaming is not the trigger | Stop chasing live view. Focus on the truncated teardown uevent and capture kernel evidence on the next real loss. |
| Both fail | motor load during streaming is fatal regardless of teardown policy | Investigate mount-side power/controller behaviour during slews. |

## Also worth doing in the same sitting

- **Restore or decide on autosuspend.** I set `usbcore.autosuspend=-1` on the device
  while testing. It is runtime-only and vanishes on reboot. Either put it back to `2`
  or deliberately keep it off and say why — do not leave it as an undocumented
  accident.
- **Try `OPENPOLARIS_USB_PIN_POWER=1`** (default off, `8d53588`) in one run to rule
  out the two-second autosuspend window as a contributor. It pins only the camera's
  own `power/control`, nothing else.

## Known limits of this test

- The fatal case is **n=1**. This experiment exists precisely because we have almost
  no data, so treat early results as directional.
- I have been wrong twice on #347 (inverted causality, mislabelled opcode). Anything
  here that contradicts a fresh log should lose.

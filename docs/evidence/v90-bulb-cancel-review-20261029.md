# v90 Bulb cancellation: static cross-layer review

This is a source and binary review, not a camera test. The affected v90
package reports libgphoto2 `63a894b0821a510fc40244c5cc4ef84a5220a91c`
and patcher `f344e41261a886f8f6107b9467095bc90b3835a1`. The examined
`pgphoto.stage2ondisk` has SHA-256
`8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`.

## What the code says

* In that exact pgphoto binary, `capture_image_with_Bulb` builds `bulb=0`
  and sends it through `cb_arg_run` (command selector 30) and
  `set_config_action` at the shared stop path. At `+0x330`, v90 replaces
  the conditional branch after the `-52` cancellation comparison with an
  unconditional branch. The local WIP patch restores the conditional branch,
  but its stop path still overwrites the cancellation status. The emulator
  regression in `tools/audit_polaris_bulb_cancel.py` demonstrates the latter
  with simulated callbacks, not a camera.
* In the exact libgphoto2 source, `config.c:_put_Pentax_Bulb` maps a zero
  toggle to `ptp2_pentax_bulb_action(..., 0, ...)`. When a prior start saw
  `PENTAX_CONDITION_BULB_TIMER`, `library.c:camera_pentax_capture_internal`
  records a timestamp and returns without starting a shutter. The matching
  zero call computes elapsed seconds, writes shutter property `0xd00f`, and
  invokes ordinary timed capture. Neither this zero toggle nor the helper's
  arguments say whether the wait ended normally or through cancellation.
* Consequently, **if** a cancellation reaches this same zero-setting path
  while the deferred timed fallback is active, it can start a new exposure
  after the cancellation. This is a control-flow risk, not a claim that the
  reported v87 untimed exposure used this fallback or that a physical cancel
  has been reproduced. A different held-shutter path has different stop
  requirements: it must close an exposure already started, without guessing
  whether a previous transport operation succeeded.
* The fallback also logs a rejected shutter write but initiates a capture at
  the old setting. The existing source-contract test specifically forbids an
  early return in this region. This is a known unresolved trade-off, not a
  guarantee that a successful file used the requested duration. Previous
  `.75` error handling caused an app spinner; simply reinstating it is not a
  complete fix. See patcher issues #239 and #243 and libgphoto2 commits
  `df9d7274565a5c0ebf310b9e7bfec75c28a8dabc` and `387bfea59147a6f5259dd764d9c6c28875f0e9fd`.
* The helper model gate explicitly excludes K-3 III Monochrome, accepts the
  standard K-3 III only for PID `0x0189`, and falls back to the model
  capability table for other models. Selection of a model by that code is
  not evidence that its camera-timed or held-Bulb behaviour was qualified.

## Vendor reference and limits

IMAGE Transmitter 2's decompiled `MtpDevice.cs` reads the timer flag from
condition offset 504; its condition processing selects release mode 2 for
B/B-lens/Astro when the camera timer is off, otherwise mode 0, subject to
later drive-mode overrides. `CamRelease` calls terminate only when its own
`_shutterReleased` or movie-recording state says a release is active;
otherwise it initiates capture. These anchors describe IT2's behaviour, not
proof that Polaris' deferred `bulb=0` design is an IT2 feature. Full UI,
transport, state, cleanup and model paths still require tracing for a proposed
change.

## Required before a candidate

Trace whether an actual app cancellation reaches the -52 edge and distinguish
normal expiry from cancellation across pgphoto and the library. Design an
explicit completion/cancellation contract: cancelled deferred starts must not
start an exposure; an accepted held start needs a single evidence-backed close
and correct error propagation; a failed or unverified duration write must not
silently yield a wrong-duration success. Test all outcomes, output handling,
and unrelated camera paths; then conduct separately gated, supervised
hardware qualification. A code-only change to make the return value look like
cancel is insufficient. The WIP qualification runner remains blocked before
device access and the cancellation regression remains deliberately failing.

## Isolated dispatcher hardening (not release clearance)

The WIP dispatcher previously searched the conditions text for three Bulb
strings; every other non-null text, including a missing field or unknown value,
was treated as permission to use the stock capture path. The branch now parses
the canonical `; exposure-mode-raw=%u;` field emitted by the exact library
`config.c:_get_Pentax_Conditions`. It accepts the values 0–31 listed in
`IT2_2625_decompile/RemoteAssistant/ExpMode.cs`, sends 9, 12 and 20 to the
existing Bulb path, and leaves the other recognized values on the stock path.
Missing keys, malformed or out-of-range values, and duplicate exact
`exposure-mode-raw=` keys return camera-busy for cameras selected by the
current name gate instead of starting a capture. The parser does not detect
every possible misspelling of a duplicate field.
An enum value does not by itself
prove a particular camera supports that mode; it is used only to distinguish a
recognized non-B value from an invalid field in this existing dispatcher.

The ARM emulator executes all 32 recognized values, invalid/missing/exact-key
duplicates and terminated strings against a guard page, alongside other-model,
zero-duration and widget-lifetime checks: 74 tests pass. These stubs do not
prove the full target ABI or behavior with corrupt widget internals; they do
clobber caller-saved registers and verify call-stack alignment and restoration.
The guard-page cases exercise the emitted parser and a simulated `strstr`, not
the target libc implementation.
The prior dispatcher fails the new missing/unknown field cases. The exact v90
ELF accepts the revised patch and its idempotence check in memory; the full
cancellation-return test still fails, as expected. This is an offline partial
fix only. It does not establish the behavior of a physical K-3 III, repair the
deferred cancellation contract, or lift any release or Bulb-test block. The
independent reviewer also identified that the existing manufacturer/model
substring checks are not an exact product identity and that the cancellation
patch affects the shared helper; both remain release blockers. The parser
validates the mode field, not every other field in the conditions text.

# Issue #251 — cancellation-return fix (2026-11-01)

Baseline HEAD before this change: `8c015c0`.
Diagnostic input (immutable v90, SHA-256):
`8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`

## What was wrong

The dispatcher retargets `capture_image_with_Bulb`'s `GP_ERROR_CANCEL` branch onto
the helper's normal stop path. That alone was not enough, because the helper's
return slot `[fp,#-16]` is an outcome accumulator written at seven sites, and two
of them run *after* `wait_and_handle_event` has recorded `-52` there:

| offset | instruction | value |
|---|---|---|
| `+0x438` | `str r3,[fp,#-16]` | stop-callback result |
| `+0x6dc` | `str r0,[fp,#-16]` | `getImageToBuffer` result |

With a successful stop and successful publication both returned `0`, so a
cancelled Bulb capture was reported to the caller as a completed one. That is
precisely what made the v87 red-cancel report dangerous.

## The fix

Each store is redirected into a conditional record in unused code-cave words.
`TRAMPOLINE_SIZE` is unchanged (`0x300`); the first stub occupies `+0x228..+0x23C`
(free between the dispatch tail at `+0x224` and the literal pool at `+0x240`) and
the second `+0x2B8..+0x2D8` (free after the match strings, which end at `+0x2B7`).

The two records deliberately use **opposite** rules, because the callbacks have
different authority over the reported outcome:

* **stop path** — record the result only when it is itself a failure. Whether the
  shutter actually closed is a safety signal, so a failed closure outranks the
  cancellation and the caller learns the exposure may still be open.
* **publication** — keep any saved non-zero outcome, otherwise record the result.
  Retrieving an image from a capture the user cancelled is downstream
  housekeeping; its failure must not replace `GP_ERROR_CANCEL`. A normal capture
  still reports a genuine publication failure.

Collapsing both into "last failure wins" would hide `GP_ERROR_CANCEL`; collapsing
both into "first outcome wins" would hide an open shutter. Neither callback is
skipped, nothing is short-circuited, and `bulb=0` is not special-cased: the stop
callback still runs so an already-held exposure is still closed, and
`getImageToBuffer` still runs so its output is still reconciled.

The stop-path stub needs no scratch register. The publication stub uses `r1`,
which is provably dead at its resume site `+0x6e0`: the first later mention is the
definition `ldr r1,[pc,#364]` at `+0x71c`, and the failure branches into `+0x750`
never read it.

## A false pass that had to be caught first

The first version of this fix appeared to work and was not correct, twice over:

1. The emulator loaded segments using the **original** ELF `p_filesz`, so the tail
   of the grown code cave was never written. Execution ran through zero-filled
   memory (`andreq r0,r0,r0` = NOP), which *unconditionally skipped* the store
   rather than preserving it conditionally. The diagnostic reported `-52` for the
   wrong reason. `tools/audit_polaris_bulb_cancel.py` now derives segment sizes
   from the patched image.
2. Preserving at `+0x438` alone was insufficient — publication at `+0x6dc` still
   returned `0`. And the initial "keep any non-zero saved outcome" rule applied to
   both sites would have hidden a failed shutter closure behind a cancellation.

Both were caught by executing the real binary rather than trusting the patch bytes.
The new ARM tests are mutation-tested: reverting the stop-path rule to the earlier
wrong one fails 5 of them.

## Verification

* `cancel-return-diagnostic.txt` — exact-binary execution of the patched helper.
  Cancellation survives cleanup and publication; a failed stop still outranks it.
* `prerelease-gate.txt` — offline gate, **11 passed / 0 failed / 0 skipped**. The
  diagnostic is now a registered check, required whenever `--build` is supplied or
  `--require-bulb-cancel-return` is given. Verified non-vacuous: with the input
  moved aside and the flag set, the gate reports
  `FAIL: REQUIRED Bulb cancellation-return diagnostic not run` and exits 1.
* `arm-and-layout.txt` — 102 ARM tests (85 dispatcher + 17 new outcome) and the
  patch layout suite, which gained 7 assertions pinning both redirects and their
  distinct rules.

## Limits

This is in-memory execution of the patched binary with simulated callbacks. It is
**not** hardware evidence: nothing here establishes that a physical shutter closed,
that a file was published, or that Benro Connect reports the cancellation
correctly. Physical qualification on K-3 III and K-1 II remains outstanding, as do
the deferred-camera-timed-start criterion and the remaining original criteria.

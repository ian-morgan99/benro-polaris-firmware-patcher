# Pentax capture version ledger and reconstructed lifecycle

This document is the control plane for issue #122 and the o-v12j/o-v12k
regressions. It separates a command acknowledgement, a physical exposure, a
transferred file, restored control, and repeated-capture readiness. None of
those observations implies the next one.

## Evidence-backed lineage

| Candidate / source | What changed | Physical evidence | What it proves | Disposition |
|---|---|---|---|---|
| o-v9d / `90de508a5` | Early Pentax capture plus model-aware focus | Exposure started, then transfer candidate remained; app reported `state:-1005` | Shutter initiation worked; lifecycle completion did not | Superseded |
| o-v9e / `90de508a5` | Patcher-only focus idle budget | Live View and manual focus passed | Focus fix was independent of capture completion | Retain behavior |
| o-v9p / `397c362e1` | Capture/preview isolation and broad reconciliation bounds | Ordinary DNG plus five Astro-equivalent DNGs plus a final DNG all passed, with preview restored | Single-output repeated capture and preview suspension/restoration worked end to end | Last broad repeated-capture PASS; do not infer RAW+JPEG |
| o-v9q / `dacfc8986` | Bulb port/phase budgets | Astro multi-shot passed; some long/manual result paths still reported failure after a real exposure | Exposure completion and API result were still conflated in some modes | Partial |
| o-v10 / `35318c1b5` lineage | Churn/startup guards plus capture readiness work | Astro, panorama and time-lapse sequences passed; ordinary Manual single-shot still lost the session after exposure | Multi-shot path worked while ordinary control-return did not | Partial |
| o-v12f / `7c60f8cbd` | Publish completed primary before the disproven 63-second readiness gate | First JPEG published in about two seconds; second shutter refused fail-closed | Primary transfer/finalization worked; delayed companion ownership remained unresolved | Diagnostic only |
| o-v12g / `252b98d57` | Recovery-field logging only | First capture passed; second refused before exposure with `state:-1005` | `state:-1005` mapped post-capture `GP_ERROR_CAMERA_BUSY`, not failed shutter initiation | Diagnostic only |
| o-v12h / `c0592d178` | Appliance-visible recovery evidence | RAW+JPEG Pixel Shift: four audible actuations, one JPEG published in about seven seconds; later `+32=1,+36=1,+104=0` | Pixel Shift produces a composite result, not four host files; RAW+JPEG had one delayed companion | Last first-capture working baseline; repeated capture unqualified |
| o-v12i / `971c8727e` | Pre-shutter read of `+524` plus minimum companion count | Not installed | Package tests alone did not exercise the camera callback boundary | Superseded before install |
| o-v12j / `6da9612a6` + unsafe LV init | Added async guard and forced LV settings at init | First deliberate RAW+JPEG call entered Stage-2 then SIGSEGV before return/PTP capture trace; restart loop | Mixed candidate; invalid for causal attribution | Failed; do not install |
| o-v12k / `6da9612a6`, LV delta reverted | Clean capture A/B | Valid preview, then the first and only deliberate capture SIGSEGV before the real call returned; USB remained enumerated but PTP wedged | Unsafe LV init was not necessary for the synchronous crash; first executed source delta is in `c0592d178..971c8727e` | Failed; do not install |
| o-v12l / `c0592d178` | Immutable recovery/control artifact | Not installed | Preserves the last first-capture-working bytes for a defined A/B only | Candidate, not final |
| next / `ba206d8af` | Post-capture observation of format/candidates; no destructive pre-drain; recovery checks `+36` | Source tests pass; hardware not yet run | Corrects the identified ownership/design divergences; physical result still unknown | Review/build candidate |

The authoritative hashes and install status remain in
`docs/FWPKT-PROVENANCE-CONTRACT.md`. Raw evidence remains under
`docs/evidence/`; especially the o-v9p qualification, o-v12g/o-v12h recovery
records, and o-v12j/o-v12k crash records.

## Reference lifecycle reconstructed from IMAGE Transmitter 2

The decompiled reference is under PrivateResearch at
`openpolaris-research/it2_research/ImageTransmitter2/IMAGETransmitter2/MtpDevice.cs`.
Its relevant behavior is:

1. A one-shot 100 ms conditions timer disables itself before work
   (`ConditionRefreshTask`, around lines 3308-3357).
2. It executes `GetAllConditions` (`0x900f`) and reads the candidate flag and
   handle at offsets `+32/+36` (`MtpGetAllConditions`, around 5434-5462).
3. If one candidate is advertised and no transfer is active, it transfers that
   object (`ExecuteFileTransfer`, around 3856-4316).
4. It acknowledges/deletes the transferred candidate only after the transfer
   completes (`MtpDeleteTransferCandidate`, call around 4314).
5. It clears transfer ownership and rearms the one-shot conditions poll. A
   later RAW+JPEG companion is therefore discovered as a later object; four
   Pixel Shift actuations are not treated as four files.
6. Live View has its own non-overlapping 33 ms callback, while command methods
   serialize WPD/MTP access through the shared command lock. Disconnect stops
   timers before closing the device.

The important invariant is observation-driven ownership: initiate one exposure,
observe one advertised candidate, transfer it, finalize it, then observe again.
Output mode supplies a completion obligation (one object for JPEG or RAW, two
for RAW+JPEG); it does not replace candidate observation and it is not inferred
from elapsed time or physical shutter sounds.

## Regressions identified in our lineage

1. The pre-capture stale-candidate path could transfer to a throwaway buffer
   and delete an object with no generation identity. That violates the prior TA
   ownership review and risks silent data loss.
2. `971c8727e` read the output-format contract in a new pre-shutter path and
   carried it through the large synchronous capture function. o-v12j and
   o-v12k crash before InitiateCapture/reconciliation, so later wait logic is
   not the immediate failure point; this pre-shutter delta is the first new
   executed source behavior.
3. `pentax_recovery_probe_ok()` claimed that no candidate was pending but did
   not inspect `+36`.
4. Earlier fixes alternated between fail-open completion, fail-closed refusal,
   and destructive cleanup. Those policies were individually plausible but
   never made one coherent ownership lifecycle.

## `ba206d8af` design

- Restore the pre-shutter barrier: unreadable conditions or an unowned pending
  candidate refuse the exposure without transferring/deleting anything.
- Remove the new pre-shutter output-format read.
- During post-primary reconciliation, read `+524` from the same serialized
  `GetAllConditions` sample used for `+32/+36`. RAW+JPEG raises the obligation
  to one companion after the primary; JPEG/RAW require none.
- Continue through transient empty samples until the declared obligation is
  met, then transfer/finalize each advertised candidate.
- Require recovery probes to prove both no active capture and no non-zero
  candidate handle.
- Preserve cancellation, candidate-count and global wall-clock safety bounds.

## Hardware promotion gate

Do not call the next packet fixed unless all rows pass independently:

1. Cold boot, runtime hashes/maps, no unsolicited shutter, preview OFF by
   default at the product/session-owner layer (not a Stage-2 init write).
2. JPEG-only: three captures; each has physical exposure, file event, normal
   result, next AF/config command, and preview restoration when demanded.
3. RAW-only: the same three-capture sequence.
4. RAW+JPEG: at least two consecutive captures, with both camera-declared
   candidates transferred/finalized per exposure and no stale candidate before
   shot two.
5. Pixel Shift RAW+JPEG: one four-actuation composite capture yielding the two
   declared output objects, followed by another valid shutter.
6. Camera remains USB-enumerated and PTP-openable; pgphoto PID/session remains
   stable; no `state:-10`, `state:-1005`, SIGSEGV or restart loop.
7. K-1 II and Canon R5 Mark II remain unqualified until their physical
   regression rows are rerun; no previous PASS is silently inherited.


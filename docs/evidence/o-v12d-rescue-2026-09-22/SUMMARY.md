# o-v12d K-3 III rescue evidence — 2026-09-22

## Provenance and identity

- Polaris AP: `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`.
- Route: `192.168.0.1 dev wlp8s0 src 192.168.0.4`.
- Installed firmware: `6.0.0.54.14-o-v12d`.
- Installed libgphoto2: `c57a8a3ac083ee77c715e0bd1436e540c0ee8c2a`.
- Installed patcher: `c0c18cb50f4dbde12d80d808ca43262a3113b304`.
- Camera: Pentax K-3 III, USB `25fb:0189`.
- Runtime loader proof: Stage-2 and stock-path core/port hashes matched and the
  running `pgphoto.stage2ondisk` maps showed the Stage-2 libraries.

## Capture reproduction

One bounded `scripts/test-astro-multishot.py --execute --shots 1` run was made.
Preview stopped successfully, capture was accepted at 17:38:38Z, state remained
busy, and `264@state:-1005` arrived at 17:39:40Z. The lifecycle was exactly
`[1, -1005]`; preview then restored successfully.

The 62-second interval matches the current long post-capture readiness bound.
Static analysis shows `camera_pentax_capture()` can expose, transfer, cache and
finalize the camera candidate, then return `GP_ERROR_CAMERA_BUSY` if readiness
does not positively become IDLE, before filesystem publication. This timing is
strong localization evidence, but the installed build lacks boundary return
logging, so it is not yet proof that every earlier step succeeded in this shot.

## Static defects and diagnostic candidate

- The candidate-timeout diagnostic tested `candidate_handle` inside a branch
  entered only when it was zero. That post-exposure attribution was unreachable.
- The capture cleanup retains `have_candidate` after a successful
  `DeleteTransferCandidate`; a later readiness failure can therefore attempt a
  duplicate delete from `out:`. This is a candidate behavioural fix, not included
  in the observation-only diagnostic.
- Diagnostic libgphoto2 `38d6e2fcb` adds one capture correlation id and boundary
  logs for initiation, candidate observation, transfer, delete, publication and
  final return, and corrects the unreachable timeout message.
- Diagnostic patcher `4995055` logs correlated Stage-2 entry, exact real-core
  return and elapsed time.
- No timeout, retry, readiness, CONFIG, preview, USB or Live View policy changes
  are included in o-v12e diagnostic.

## Camera heat / Live View static audit

The first Pentax preview enables camera PC Live View and sets `inliveview`.
Stage-2 deliberately enables `pentaxpclvkeep`; successful preview therefore
does not call the normal Live View restore/stop path. The current normal stop
owners are error cleanup, capture/session transition, forced camera teardown or
process restart. There is no observed normal UI-preview-idle/disconnect demand
signal at this layer that positively turns camera-side Live View off.

That proves persistent Live View residency is a real Polaris workload difference;
it does not yet prove it is the dominant heat cause. Per issues #67/#123, the fix
must be demand-owned Live View in the persistent serialized pgphoto scheduler,
not a global `pentaxpclvkeep=0` change or another Stage-2 timer. A controlled
connected-LV-OFF versus connected-LV-ON/no-fetch A/B remains required.

## Classification

- o-v12d capture: **FAIL** (`state:-1005`, `[1,-1005]`).
- o-v12d runtime/provenance: **PASS**.
- o-v12e source/build/package gates: **PASS**; hardware validation pending.
- Heat mechanism: persistent LV residency **PROVEN STATICALLY**; thermal
  causality and scheduler fix **NOT YET TESTED**.

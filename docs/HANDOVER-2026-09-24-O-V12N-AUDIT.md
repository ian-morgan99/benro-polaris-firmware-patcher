# o-v12n audit handover — 2026-09-24

## Outcome

`o-v12n-companion-ownership` remains an installed diagnostic candidate, not a
release. Do not build or install a successor merely because the PR #81
ownership test was repaired. The first unresolved product boundary is
same-session capture recovery/liveness after a successful RAW-only shot.

## Confirmed current identities

- Device: `FwVer:6.0.0.54.23-o-v12n-companion-ownership`
- Runtime libgphoto2: `ab0de090c63e707afccc6d425c1c596799952341`
- Runtime patcher: `7bcbc390a3016ca5a3473eb18a09b95e2c7dc19a`
- Matched core MD5: `5973e8c8999b1f4f01be70a9cafdb7ba`
- Registered FwPkt MD5: `2c9c45b0476091982888f84e95c7e986`
- Registered FwPkt SHA-256:
  `8b3c845bad0fcf4324ced23a09387cf4235e1c2071494f1485ebc265fa6cb235`
- Registered appfs MD5: `c53dd8f2e69c007fbdd7753c46f5a43d`
- Current libgphoto2 review head: `62402cc2c`

## Evidence matrix

| Claim | Status | Evidence |
|---|---|---|
| o-v12n installed bytes/provenance | PASS | FwVer, embedded provenance, matched core hashes |
| K-3 III RAW-only first capture | PASS | `SP_0074.dng`, 32,900,659 bytes, capture states `[1,4,0]` |
| K-3 III same-session second capture | FAIL / NOT REACHED | run 1 lost camera after shot-1 idle; script correctly withheld shot 2 |
| K-3 III repeat run | FAIL | shot 1 did not complete; camera later reported `state:-10` |
| RAW+JPEG companion retrieval on o-v12n | NOT TESTED | no valid o-v12n two-object canary is recorded |
| Pixel Shift RAW+JPEG repeat | NOT TESTED | do not infer from o-v12m or RAW-only |
| K-1 II product path on o-v12n | NOT TESTED | issue #136 used an invalid standalone Stage-2 CLI environment |
| K-01 product-path init | PASS | USB `25fb:0131`, `sp_Gphoto_Init ret 0`, `pentax/k-01/state:1` |
| K-01 still capture | UNSUPPORTED / NOT QUALIFIED | one request returned `-6` promptly; no crash |
| PR #81 ownership regression coverage | PASS at `62402cc2c` | focused tests 2/2 plus `ptp2.so` compile |
| New release packet | NOT BUILT | no runtime fix has yet been justified |

## Corrections to prior work

1. The `74d9e1f50` regression test was self-fulfilling: its mock cleared the
   transfer buffer itself. Commit `62402cc2c` factors the ownership decision
   into a production helper called by the real publication callback and tests
   success, pre-transfer failure, and later-publication failure ownership.
2. Issue #136's standalone Stage-2 CLI slot collision is not a K-1 II protocol
   result. The fixed-address collision guard must remain fail-closed. The real
   daemon path successfully initializes the currently attached K-01, proving
   the packaged camera database is not generally empty.
3. The uncommitted primary patcher checkout removes launch-lock identity checks
   and packaging assertions. Those changes were not used, committed, reverted,
   or included in any artifact during this audit.
4. Public documentation now describes observable interoperability behavior
   without naming or linking private analysis sources.

## Smallest next experiment

Use the installed o-v12n unchanged with the K-3 III, preview confirmed OFF, and
one client only:

1. Record pgphoto PID, USB identity, camera-info state and current log offsets.
2. Send exactly one RAW-only capture.
3. After the `state:4` file event, poll camera-info only; do not issue config
   writes or a second shutter.
4. Correlate the first transition among USB removal/reset, pgphoto restart,
   PTP/session error, camera-info `state:0/-10`, and candidate/readiness logs.
5. Only if state remains healthy and idle, send shot 2 in the same session.

This discriminates camera/USB loss from an over-conservative recovery
predicate without adding a guessed delay or weakening the fail-closed barrier.
If the camera disappears before shot 2, the next source change belongs at the
first divergent layer; if it remains healthy but the recovery predicate blocks,
capture the raw conditions frame before changing that predicate.

## Stop conditions

- Any unsolicited shutter actuation.
- Any SIGSEGV, pgphoto PID change, restart loop, USB reset/removal or
  camera-info `state:-10`.
- A pending candidate with uncertain generation ownership.
- Any proposal to remove launch-lock/package gates or relax the Stage-2
  fixed-slot collision check to make a diagnostic CLI run.

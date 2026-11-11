# Autonomous session record — 2026-11-11

Continuation of the v105 field-test triage. Worked unattended. Everything below is either
pushed or explicitly marked as not done.

## Shipped (pushed)

| Repo | Commit | What |
|---|---|---|
| patcher `main` | `9a49b07` | #329 apply-last contract: new module + node tests + gate registration |
| patcher `main` | `ca58501`, `28d7e60`, `6ee1d81` | v106 change summary, twice corrected |
| patcher `feature/astro-native-platesolve` | fast-forwarded to `main` | builder requires this branch by name |
| libgphoto2 `main` | `96cb7b8b4` | #148 — route generic `exposurecompensation` to the Pentax EV handler |

Candidate built: `astro-v106-appliance-fixes-20261111`, display fwver `6.0.0.54.106`.
**GATE: GREEN (23 passed, 0 failed, 3 skipped)**, artifact verdict
`ARTIFACTS_INTERNALLY_CONSISTENT_WITH_UNKNOWN` (21 checks, 0 fail, 1 unknown), candidate
identity `PASS (deployable)`. Not published, not installed — see boundary below.

## 1. #329 — implemented, and two of its asks deliberately refused

`#solve-apply` posted an empty body, showed nothing on success, and on failure showed only a
bare error string. The user wrote a mount alignment from a solution whose RA/Dec, roll and
pixel scale were never displayed, even though `/api/state` already returns the whole solver
JSON and `/api/apply` already reports `age_sec`.

Decision table moved to `container/astro/webui/solve-apply.js`, DOM-free like `shutter.js`
(#309), asserted under node by `tests/test_astro_solve_apply.js` (17 groups) through the
pytest wrapper, registered in `PY_TESTS`.

Refused deliberately, with reasons recorded on the issue and in the module header:

- **Focal length is not threaded into apply.** Focal selects the search space at *solve* time;
  a solved frame's RA/Dec are already resolved and applying them writes no focal anywhere.
  `polaris-httpd.c` runs every solve as `--focal auto` on purpose — "Forcing g_focal here would
  reintroduce the bug that cost a whole night". Sending a UI focal through apply recreates it.
- **The align checkbox is not consulted by this button.** `/api/apply` always writes the
  alignment, so honouring an unticked box would mean silently doing nothing.
- **No client-side staleness gate.** `/api/state` does not report frame age — only `/api/apply`'s
  reply carries `age_sec` — so a UI-side refusal would be guessing, and duplicating the server's
  rule creates a second source of truth that can disagree with it. Same class as #309, where the
  WebUI tried to decide shutter subtype itself.

The part I would argue matters most: `applyOutcome()` treats a missing body, a non-object, an
array, or an object with no `ok` field as **not confirmed**. Previously all of those fell through
to a generic failure line that read as though the head had refused the write — a different event
that must be said differently.

## 2. #323–#328 — checked against shipped bytes, not inferred

Six issues asked pgphoto to call Pentax guards before forwarding config writes. Three independent
blockers, each verified:

1. `_pentax_readiness_preflight`, `_pentax_verify_property_value` and
   `_pentax_verify_rational_in_conditions` are all `static`, declared in no header, so not
   exported from `ptp2.so`. pgphoto cannot link to them.
2. `params->pentax.vendor_mode_enabled` lives inside `PTPParams`, internal to the camlib. pgphoto
   only ever holds the public `gp_camera_*` API.
3. Both public entry points already funnel into the guarded `_put_` handlers:
   `camera_set_config`/`camera_set_single_config` → `_set_config` (config.c:16498/16504) →
   `cursub->putfunc` (:16316) → `_put_Pentax_DirectShutter` (:15352).

So pgphoto is not an unvalidated pass-through; it calls a path that validates. Our own
`stage2_shim_gp_camera_set_single_config` is deliberately pure pass-through for config writes, so
nothing short-circuits the camlib either.

**What is genuinely broken** (in #328): on verification failure the driver does not revert the
widget it was handed — `continue` at config.c:16333 with no value restore, then
`gp_widget_set_changed(widget, FALSE)` at :16339 anyway. `_put_Pentax_DirectShutter` contains zero
`gp_widget_set_value` calls (232 exist elsewhere in `config.c`). A consumer caching from
`gp_widget_get_value()` on a widget it already holds therefore caches the *attempt*, not the state.
The read path is unaffected: `_get_config` calls `cur->getfunc` per widget, so a fresh
`get_single_config()` re-queries the camera.

#324 closed as duplicate of #325. #328 given a proposed retitle and driver-side scope. #323/#326/#327
corrected in place. No libgphoto2 change made for these: `_set_config` is generic across every
vendor in the file, and driver `AGENTS.md` forbids changing it for a consumer-discovered failure
without a repo-boundary reproducer plus impact statement.

Also noted: #328's own environment block cites libgphoto2 `0562e8a`, which is upstream and **930
commits behind** the pin v105 ships (`49b67fa44`). The analysis was done against a library not in
the build being tested.

## 3. #148 — recovered, and its recorded blocker proven gone

`0ca7c9205` (tag `archive/pre-consolidation/fix/k1ii-benro-controls`) was never landed during the
2026-11-09 consolidation. It adds one `PTP_VENDOR_PENTAX` row routing the standard name
`exposurecompensation` to `_get/_put_Pentax_DirectEV`.

Its recorded blocker was:

```
FAIL line 298: ret == GP_OK && ev != NULL
```

That no longer reproduces. Established by control, not assumption, in an isolated worktree at
`49b67fa44` with a meson build in a separate prefix:

| State | Result |
|---|---|
| EV row absent, test's EV assertions present | `FAIL line 298` — reproduces #148 exactly |
| EV row present | passes |
| assert `count_choices == 99` instead of 3 | `FAIL line 303` |

The last row is what makes this worth landing: a green test that never reached the EV block would
have looked identical to a fixed one. Full suite unchanged at 24 passed / 1 failed; the failure is
`test-gp-port` in the `no-ci` suite, present on plain main, excluded by
`tests/run-pentax-host-check.sh`.

## 4. v106 built via the documented process — and what that took

`docs/ASTRO-CANDIDATE-RELEASE.md` specifies a clean clone of the pushed Astro branch, not the dirty
worktree. Three failures before it succeeded, each a real gap rather than a flake:

1. **Gate RED** — `check_bulb_cancel_return` needs an immutable v90 binary under `out/`, which is
   gitignored. Located it, verified its sha256 against the pinned value
   (`8973d948…eaac`) before supplying it, rather than substituting a similar file.
2. **Release identity failed** — my change summary used component names outside the validator's
   vocabulary `{libgphoto2, patcher, packaging, tests, docs}`. Fixed by running
   `create-release-change-manifest.py` *directly* before rebuilding, instead of discovering it 15
   minutes into another cycle.
3. **`--libgphoto2-commit` requires a full SHA**, not an abbreviated one.

The builder independently corroborated the #323–#328 analysis: `libgphoto2 commits since baseline:
0` at the v105 pin, and `patcher commits since baseline: 31`.

## 5. New issue filed: #331 — GPL source ships in the tarball but never reaches a user

The archive gate reported 5 licence files outside `COPY-TO-SD-CARD-ROOT`, so a user following the
bundle's own README copies binaries built from GPL-2/LGPL-2.1 components with none of the licences
or corresponding sources. Not a v106 regression — the check arrived with #292, so v105 and earlier
were never examined by it. Filed rather than fixed: whether to copy licence texts plus a written
offer, ship the tarballs on the card, or change the README is a distribution decision I should not
make unilaterally, and verifying any of them needs a supervised window.

## 6. Methods I got wrong, and how they were caught

Worth recording because each produced a confidently wrong answer.

- **Claimed the built binary did not contain the #329 change.** Searched `polaris-httpd` for raw JS
  bytes; found none. Ran a control with `shutter.js`, a known-good pre-existing asset, which also
  returned nothing — because `embed_webui.py` **gzips** every asset into `.rodata`. Inflating the
  embedded streams showed all five assets present and correct. The first conclusion was an artefact
  of the method, not a build defect.
- **Reported "OLD empty-body handler gone: FAIL" on the inflated assets.** The string appears in
  `solve-apply.js`'s own header comment describing what the old code did. Checked per-asset and the
  live handler is correctly `post('/api/apply' + req.query, {})`.
- **First #148 control was invalid.** `git stash` reverted the test file as well as `config.c`, so
  plain main "passed" trivially with no EV assertions to run. Redone by reverting only `config.c`
  and keeping the assertions, which then failed at line 298 as expected.
- **String-count comparison cannot prove a table row exists.** `exposurecompensation` appears 3× in
  both parent and fixed builds because `.rodata` deduplicates literals. The behavioural control is
  the proof; the byte-level check was decorative.
- **Wrong date in a path** (`20261111` for the v105 dir, which is `20261110`) made `find` return
  nothing and briefly suggested v105 had shipped no `ptp2.so`.

## 7. Verification that actually landed

- **WebUI change is in the shipped ARM binary.** Inflated all five embedded gzip assets from the
  built `polaris-httpd`: `solve-apply.js` present, `describeSolution` and `applyOutcome` present,
  `app.js` calls `SOLVE_APPLY.applyRequest`/`applyOutcome`, `S.solveState = st` present,
  `/solve-apply.js` referenced by the embedded `index.html`, and the bare empty-body post absent
  from `app.js`. Control: `shutter.js`'s `decideDispatch` still present.
- **Driver change is in the shipped ARM binary.** v105's `ptp2.so` md5 is `b18d45a8bc1dcde29dad4151091608cc`
  — byte-identical to the md5 recorded from the device, which independently confirms the "the driver
  on the device is ours" claim used in the #323–#328 corrections. v106's is `83ea3baf01df…`, 28 bytes
  larger.
- **Patcher suite**: 697 passed, 15 skipped (was 694 before the three new tests).
- **Mutation-checked both directions** for #329: restoring the old empty-body post fails exactly one
  test; making `applyOutcome()` accept a missing reply fails exactly one group.

## Not done / not claimed

- **Nothing was installed, flashed, staged, rebooted or published.** No Polaris reachable at
  `192.168.0.1` or `192.168.1.1`, and no Pentax/Benro device on USB — checked before concluding.
  `docs/ASTRO-CANDIDATE-RELEASE.md` additionally forbids staging until the camera owner accepts the
  baseline, #251 is resolved or waived, and a supervised test window is scheduled. All three are
  outstanding, so publishing would have been wrong regardless of connectivity.
- **No hardware verification of anything this session produced.** The #329 fix is verified by
  execution under node; "alignment written" reflects what `/api/apply` reported, not independently
  confirmed mount state. The #148 fix is an offline seeded-descriptor fixture result — per the
  driver's own rules, "the build passes" is not "this is correct". Whether a real K-1 II answers
  `0x5010` the way the seeded descriptor does is untested, as is the `GP_WIDGET_TEXT` fallback for
  bodies advertising no enumeration.
- **The widget-not-reverted defect behind #328 is not fixed.** It needs its own offline fixture test
  first; `tests/test-pentax-aperture-alias.c` already demonstrates the pattern needed (seeded
  `Camera`, no wire I/O). Proposed scope is on the issue.
- **#331 not fixed** — distribution/licensing decision, left for the owner with three options.
- **The `licence-reachability` check still reports `UNKNOWN`.** Left unsilenced deliberately; it
  should become decidable once a route is chosen.
- **Three gate skips remain**: firmwareInfo manifest gate (no stock FwPkt.zip in repo),
  shipped-artifact differential (no previous candidate with a manifest to compare), provenance
  registry hash check (no built artifacts to compare). Recorded here as required by the gate output.
- **#297 root cause still unknown.** This cut carries read-only diagnostics only; layer 3 remains
  unfixed.
- **`test-gp-port` fails on plain main** in the `no-ci` suite. Pre-existing, unrelated to Pentax,
  excluded by the documented host check. Not investigated.

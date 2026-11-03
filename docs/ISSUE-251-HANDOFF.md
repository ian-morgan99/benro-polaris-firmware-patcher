# Issue 251: source recovery and build handoff (2026-10-30)

Canonical issue: <https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/251>.
Reusable emulator development is tracked separately in
<https://github.com/ian-morgan99/benro-polaris-test-harness/issues/15>.

## Active source and preserved work

The authorized patcher delivery worktree is `/home/ian/polaris-build-73`, on
`main`. Its directory name is historical and does not identify the firmware
version. The separate `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher`
worktree is on `feature/astro-native-platesolve` with unrelated uncommitted
work. Do not switch, reset, or build a release from that tree.

Partial fix `aecf7a360d90f35df9dd60b29ee93101e8da0036` is on patcher `main`:

- `GP_WIDGET_TEXT` is read as a borrowed `char *` and used before widget free.
- The cancellation branch retains `BEQ` rather than becoming unconditional.

These changes do not complete #251. The previously scattered experimental
work is preserved by tag `archive/issue-251-wip-20261030`, pointing to
`c8fa42910b6a2c6ecdecf4cd558cce5645fa6cc0`. It is historical source, not a
candidate or a branch to merge wholesale. It contains the stronger widget
type/null/mode checks, ARM execution tests, exact-v90 cancellation diagnostic,
qualification-runner block, and cross-layer review. Its cancellation test is
deliberately failing for the unresolved defect. The local original remains at
`LibGphoto2/polaris-bulb-review`; nothing was removed or overwritten there.

To inspect that source from GitHub without creating another working branch:

```sh
git fetch origin tag archive/issue-251-wip-20261030
git show archive/issue-251-wip-20261030:tools/audit_polaris_bulb_cancel.py
git show archive/issue-251-wip-20261030:container/test_polaris_bulb_dispatch_arm.py
git show archive/issue-251-wip-20261030:docs/evidence/v90-bulb-cancel-review-20261029.md
```

The clean libgphoto2 `main` worktree at this check is
`/home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main`, SHA
`051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff`. The adjacent
`LibGphoto2/libgphoto2` worktree is a feature branch, not the release input.
No libgphoto2 source changed during this recovery.

## Dispatcher follow-up on main (2026-10-30)

The reviewed widget/type/mode checks are now on main, with two additional
corrections found during executable testing: clearing the reused text-output
slot (otherwise an omitted output can turn type `2` into a pointer), and
matching the exact registered `Pentax:K-3 Mark III (MTP mode)` abilities label
instead of a model-name substring. The label comparison ignores case.

Failed/invalid widget reads and missing/malformed/out-of-range/duplicate exact
mode fields return camera-busy for the selected K-3 III without entering a
capture helper. Valid modes 9/12/20 retain the existing Bulb route; other
recognized values retain stock capture. Other models, nonpositive durations
and nonzero status retain stock dispatch. This does not establish the safety
of the Bulb helper itself.

The trampoline grows from `0x220` to `0x300` bytes (224 bytes) for these checks.
It still makes one same-session conditions read, not a polling loop. No new
vendor opcode, retry, capture timing, library or shared stop-path change is
included. The archived WIP was not merged wholesale.

The executable ARM tests are registered in the offline gate. Unicorn 2.1.4
was installed only in `/tmp/polaris-251-arm-tests-20261030`, not in the system
environment. Missing Unicorn explicitly skips those tests and never counts as
physical qualification. The recovered exact-binary diagnostic is on main as
`tools/audit_polaris_bulb_cancel.py` and still fails. See the
[follow-up evidence](evidence/issue-251-dispatch-20261030/README.md).

## What prevented progress and what was repaired

The Codex sandbox runner failed before executing any command with
`mountinfo path is not absolute`. Approved execution outside that failing
sandbox restored access. No sandbox policy or host configuration was changed.
That runner error did not demonstrate a compiler failure.

Both desktop build icons target `scripts/release/build-and-install.sh` in
`/home/ian/polaris-build-73`. Its default was still `.77`, a consumed version.
The wrapper now passes `auto` for version and build ID to the canonical builder,
which derives and validates the next version from the registry. Explicit
overrides remain subject to the existing checks. Candidate IDs no longer use
the old v18g label, and logs distinguish requested values from resolved values.

The runbook now includes the mandatory `CHANGE_SUMMARY` / `--change-summary`
argument and names the verified main worktrees. A desktop launch without a
reviewed summary still stops intentionally; it does not invent release claims.

## Verification

- Stage-2 ARM shared-library cross-compile passes with `-Wall -Wextra -Werror`.
- Existing deterministic patcher checks: 25 pass, 0 fail, 2 prerequisite skips
  (`test_source_input.sh`, `test_polaris_pentax_build_package.sh`).
- The clean libgphoto2 SHA above was built from scratch with the release
  runbook's Meson test configuration (`ptp2,pentax,directory`): 20 pass, 0 fail.
  The hardware-dependent `no-ci` suite was excluded as documented.
- New wrapper regression failed against the old `.77` default; all four cases
  pass after the correction. Combined wrapper/version tests: 45 pass.
- Final full offline gate: 9 checks pass, 0 fail, 1 source-input skip;
  its Python suite has 397 passes and 8 skips. The source contract skipped by
  this invocation passes in the separate 20-test clean-library run.
  Transcripts and tested-source hashes are in
  [the recovery evidence](evidence/issue-251-recovery-20261030/README.md).
- The partial dispatcher patch applies to the retained stock pgphoto ELF;
  its marker check and repeated-application check both pass. This verifies
  real-binary patch layout, not ARM execution or camera behavior.

These are source/compiler/offline results. The Meson host build is not the
shipped ARM/autotools package. No firmware was built, published, installed,
or operated on a camera during this recovery. No release version was consumed.

## Return-path fix landed 2026-11-01 (`8351065`, pushed)

Criterion 2's second sentence is now implemented and verified offline. Evidence:
[cancellation-return fix](evidence/issue-251-cancel-return-fix-20261101/SUMMARY.md).

`capture_image_with_Bulb` accumulates its return value in `[fp,#-16]`, written at
seven sites. Two run *after* `wait_and_handle_event` records `GP_ERROR_CANCEL`
there: the stop-callback store at `+0x438` and the `getImageToBuffer` store at
`+0x6dc`. With both succeeding the helper returned `0`, so a cancelled capture was
indistinguishable from a completed one. Each store is redirected to a conditional
record in previously unused code-cave words; `TRAMPOLINE_SIZE` is unchanged.

The two records use opposite rules deliberately, because the callbacks have
different authority over the outcome:

- stop path — record only a failure. Whether the shutter actually closed is a
  safety signal, so a failed closure outranks the cancellation.
- publication — keep any saved non-zero outcome. Retrieving an image from a
  capture the user cancelled is downstream housekeeping and must not replace
  `GP_ERROR_CANCEL`; a normal capture still reports a real publication failure.

Neither callback is skipped and `bulb=0` is not special-cased, so an already-held
exposure is still closed and its output still reconciled.

Two false passes had to be caught before this was trustworthy, and both were
found by executing the real binary rather than trusting patch bytes:

1. The diagnostic loaded segments using the original ELF `p_filesz`, so the tail
   of the grown code cave was never written. Execution ran through zero-filled
   memory (`andreq r0,r0,r0` = NOP), which *unconditionally skipped* the store
   instead of preserving it conditionally — the diagnostic reported `-52` for the
   wrong reason. Segment sizes now come from the patched image.
2. Preserving at `+0x438` alone still returned `0`, because publication overwrote
   it. And an initial "keep any non-zero saved outcome" rule applied to both sites
   would have hidden a failed shutter closure behind a cancellation.

The new ARM outcome tests are mutation-tested: reverting the stop-path rule to the
earlier wrong one fails 5 of them. The exact-binary diagnostic is now a registered
prerelease-gate check, implied by `--build` or `--require-bulb-cancel-return`, and
verified non-vacuous — with its input absent and the flag set the gate reports
`FAIL: REQUIRED Bulb cancellation-return diagnostic not run` and exits 1. Offline
gate: 11 passed, 0 failed, 0 skipped.

This is in-memory execution with simulated callbacks. It does not establish
physical closure, publication, or how Benro Connect reports a cancellation.

## Criterion 3 analysis — deferred camera-timed start (not fixed)

Static analysis only; no change was made and none should be without a reproducer.

`ptp2_pentax_bulb_action()` in libgphoto2 `051d224db` defers the capture at the
start edge when camera-timed Bulb is active, setting
`bulb_action_timed_fallback = 1` and recording `bulb_action_start_ms`. The stop
edge then converts the measured hold into a shutter speed and runs one ordinary
camera-timed capture. If the context was cancelled between the edges, that stop
edge still issues a new exposure — the defect.

Two facts block a fix here:

- `ptp2_pentax_bulb_action()` takes `GPContext *context` but discards it with
  `(void) context;`, so nothing on the path currently consults cancellation. A
  query *is* available — `gp_context_cancel(context)` returns `GPContextFeedback`,
  including `GP_CONTEXT_FEEDBACK_CANCEL` (`gphoto2/gphoto2-context.h:124`) — but it
  is a callback into the caller, not a stored flag, so whether pgphoto's context
  actually reports a cancel at that moment must be established by observation, not
  assumed.
- The repository ownership rule states: "Do not make a libgphoto2 change to fix a
  Polaris-only symptom without a direct source-repo reproducer." This behavior was
  discovered through the Polaris consumer and has not been reproduced directly
  against the source repo on a directly attached camera.

A universal skip of the `bulb=0` callback remains unsafe for the same reason as
before: it would also suppress closing an already-held exposure. The distinction
required is *deferred start* versus *held exposure*, which already exists in
`bulb_action_timed_fallback`.

Candidate shape, once a reproducer exists: at the stop edge, if
`bulb_action_timed_fallback` is set (so nothing was armed and there is no held
shutter to close) and `gp_context_cancel(context)` reports
`GP_CONTEXT_FEEDBACK_CANCEL`, discard the start record and return
`GP_ERROR_CANCEL` instead of setting a shutter speed and issuing a capture. When
the action is a held exposure, close it regardless — cancellation must never leave
a shutter open. This is a targeted outcome decision on an existing state flag, not
a callback skip.

Next step for criterion 3, in order: build a direct source-repo reproducer on an
attached camera (start a camera-timed Bulb, cancel mid-hold, observe whether a new
exposure is issued), and confirm what pgphoto's context reports at that edge. Then
implement the branch above with a source-repo test alongside it.

Ownership assessment (2026-11-01): the state that distinguishes the two cases lives
in libgphoto2, not in pgphoto. The deferral is recorded as `params->pentax.bulb_action_timed_fallback`
and consumed by the stop edge reached from `config.c:9378`, which calls
`ptp2_pentax_bulb_action(camera, val != 0, context)`. pgphoto only writes that
property; it has no view of the flag, so a patcher-side fix would have to infer the
state from outside — exactly the guessing the ownership rule exists to prevent. The
change therefore belongs in libgphoto2 and needs the direct reproducer first.
`tests/test-pentax-capture-contract.py` is the natural home for the accompanying
assertion, but it is a source-contract test and does not substitute for observing
the behaviour on an attached camera.

## Remaining #251 work, in order

1. Type/null/mode and exact abilities-label checks are now implemented and
   ARM-tested. Installed-ABI/hardware confirmation is still owed. The label
   check is not a new USB identity probe or proof of physical support.
2. Distinguish normal expiry, message stop (`264/state:0`) and context cancel.
   Preserve cancellation and stop errors through cleanup and file handling.
   *Return-path preservation landed in `8351065` (see above). Distinguishing the
   three termination causes on hardware is still owed.*
3. Ensure cancelling a deferred camera-timed start cannot issue a new exposure,
   while cancelling an already held exposure still closes it. A universal
   skip of the `bulb=0` callback is unsafe. Follow the repository ownership rule
   before changing libgphoto2 for this consumer-discovered behavior.
   *Not fixed; blocked pending a direct source-repo reproducer (see analysis above).*
4. Cover normal/cancel, stop failure, output publication, and shared non-Pentax
   behavior with the available regression tests. The reusable harness project
   is future work; record any unavailable executable test distinctly.
5. Build and publish through the canonical release process only after the
   known unsafe paths have been addressed. Qualify on supervised hardware with
   short exposures, stop on the first mismatch, and verify physical closure,
   publication and recovery before longer tests. Do not run the existing full
   qualification round on v89/v90: it contains an automatic Bulb shot.
6. Complete the other original criteria separately: missing timed-B shutter
   list, exposure duration rather than pre-delay, Manual wheel behavior and
   transitions/recovery. Dispatcher tests do not close those physical gates.

The immutable local diagnostic input is
`out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk`,
SHA-256 `8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`.
It is already patched and must not be passed off as pristine stock or modified
in place. The preserved diagnostic reconstructs only its verified patch effects
in memory. Obtain release inputs through the stock-packet runbook.

## 2026-10-30: corrected binary ownership scan, and criterion 6 verified offline

### Binary ownership — the earlier "no copy owns the helper" claim was WRONG
The first scan hashed **file offset** `0x101aac`, but that value is a **virtual
address**. `.text` is `sh_addr=0x15710`, `sh_offset=0x5710`, so the correct file
offset is `0x101aac - 0x15710 + 0x5710 = 0xf1aac`. The first scan therefore hashed
unrelated bytes and reported 0 matches for both hashes.

Re-scanned all 280 `pgphoto.stage2ondisk` files under `/home/ian` at the correct
offset (2176-byte helper region):

- **15 match the pinned helper** `23398c6e…` — every one is a build we produced,
  including `out/o-v18m-k1ii-pgphoto-readiness-20261029/...` (the candidate) and
  the extracted packet copy. **The candidate does own the helper.**
- **112 match the stock helper** `333a3f66…` — these are *older patched builds*
  whose helper region was never modified, not pristine binaries.
- 69 files are a third variant.

**Correction to record:** the candidate owns the helper; the earlier statement that
"no copy on disk owns the helper" was an artifact of the address/offset bug and is
withdrawn.

### Pristine stock base — it DOES exist (this claim was also wrong, now corrected)
An intermediate claim in this session — "no pristine stock binary exists on disk" —
was **wrong**, caused by scoping the search to the filename `pgphoto.stage2ondisk`.
The pristine copy is named `pgphoto.stock`, so it was never in the candidate set.

**Usable pristine BASE:**
`openpolaris-research/BenroPolarisPatcher/docs/evidence/stock-baseline-2026-09-07/bin/pgphoto.stock`

- size 7,801,576 bytes (identical to every patched copy)
- MD5 `a766aaf9320978e271d1d8cf0f1677a5` — **matches `BIN_MD5_PGPHOTO` in the
  baseline `state.txt` exactly**
- SHA-256 `0308393632dd41d974bd1064e61942655131fe5392959a334cf24623d1bd4a62`
- helper region at file offset `0xf1aac` hashes to `333a3f66…`, i.e. it is the
  reference the 112 patched builds are diffed against
- **0** real patch markers (`stage2-ondisk`, `libpolaris_stage2`, `pgphoto.wrapper`,
  `camera_usb_supervisor`)
- baseline `state.txt`: `FwVer:4.0.0.32;date:2025.05.09`, stock libgphoto2 2.5.27.1

Note on an earlier false alarm: grepping this file for `polaris|stage2-ondisk|libpolaris`
returned 322 hits, which I read as "already patched". That was a bad pattern — the
word *polaris* occurs naturally throughout the stock firmware. Restricting to the
strings our patch actually injects gives 0. The same mistake invalidated the earlier
"firmware-extracted copy is already patched" statement about `8973d948…`; that file
is a **build output**, and its patched status must be judged by injected strings, not
by the word `polaris`.

**Consequence:** rebuilds do not need to re-extract from `FwPkt.zip`. The stock packet
remains the authoritative durable input (`4.0.0.32--stock/FwPkt.zip`, zip SHA-256
`f980fe52…`, appfs MD5 `47f2ae68…2397b`), but `pgphoto.stock` is a verified,
immediately usable base for the canonical release process.

### Criterion 6 (missing timed-B shutter list) — implemented, tested, shipped
This criterion was already addressed under issue **#241**, not #251:

- `ptp2/pentax: always populate the Bulb/seconds entries in the shutter list`
  (`8db3785f7`, 2026-10-27) is an ancestor of the shipped branch.
- `_get_Pentax_DirectShutter` synthesises the body's own 1 s–30 s entries when the
  camera returns `enum-count=0` in B mode, and points the current value at a valid
  entry so the widget is coherent. Gated by
  `pentax_shutter_list_may_synthesise_bulb()` — **K-3 III only**; K-1 II, K-3 II,
  KP and K-70 are excluded.
- Verified in the shipped artifact: `stage2-ondisk/libgphoto2/2.5.34/ptp2.so`
  contains the fix's log string.
- `tests/test-pentax-utils` rebuilt from current source and **passes** (exit 0),
  covering the 1..30 s table, value formatting, and the model gate.

**Still open:** on-camera confirmation that Benro Connect no longer crashes in
timed-B / on a mode-dial change. The code path is verified offline; the crash-free
behaviour is not yet observed.

### Criterion 6, part 2 (duration rather than pre-delay) — implemented, tested, shipped
Also already addressed, under issue **#243**:

- `ptp2/pentax: stop using the pre-shutter Bulb timer as the duration`
  (`27540e122`) is an ancestor of the shipped branch.
- The camera-timed fallback now derives the duration from the **measured hold**
  (`pentax_bulb_hold_to_seconds(start_ms, now)`). The body's pre-shutter report is
  logged alongside for comparison only and explicitly "must never drive the
  duration", because at the start edge it still reflects the *previous* shot.
- Verified in the shipped artifact: `stage2-ondisk/libgphoto2/2.5.34/ptp2.so`
  contains the fallback log string; `libgphoto2.so.6` correctly does not.
- `tests/test-pentax-utils` covers the rounding table (1000→3000 ms = 2 s,
  3500 = 3 s, 12000 = 11 s, sub-second and negative clamps to 1 s) and passes.

### Unit suite status on this tree
`meson test` in `build-static-audit`: **19 ok, 1 skipped, 1 fail**.
- `test-pentax-utils` OK (3.50 s), `test-pentax-reconcile` OK (1.20 s).
- `test-pentax-aperture-alias` SKIP (exit 77) — pre-existing skip.
- `test-gp-port` FAIL is in upstream's **`no-ci`** suite (`libgphoto2_port/tests/
  meson.build`, `suite: 'no-ci'`) and enumerates real host ports; it is an
  environment artifact, not a regression from this work. No Pentax test fails.

### Criterion 6 — remaining gate
Of the three sub-criteria, two are now closed offline (#241 timed-B list, #243
duration). **Manual wheel behavior and transitions/recovery has no offline
substitute** — it requires observing the physical dial and mode transitions on the
body. That remains camera-blocked, as do the physical closure/publication checks in
criterion 5.

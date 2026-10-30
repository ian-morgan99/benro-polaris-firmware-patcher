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

## Remaining #251 work, in order

1. Review the preserved type/null/mode checks against the current dispatcher;
   main's partial fix does not include them. Preserve the stock path for other
   models and verify the exact K-3 III identity gate.
2. Distinguish normal expiry, message stop (`264/state:0`) and context cancel.
   Preserve cancellation and stop errors through cleanup and file handling.
3. Ensure cancelling a deferred camera-timed start cannot issue a new exposure,
   while cancelling an already held exposure still closes it. A universal
   skip of the `bulb=0` callback is unsafe. Follow the repository ownership rule
   before changing libgphoto2 for this consumer-discovered behavior.
4. Cover normal/cancel, stop failure, output publication, and shared non-Pentax
   behavior with the available regression tests. The reusable harness project
   is future work; record any unavailable executable test distinctly.
5. Build and publish through the canonical release process only after the
   known unsafe paths have been addressed. Qualify on supervised hardware with
   short exposures, stop on the first mismatch, and verify physical closure,
   publication and recovery before longer tests. Do not run the existing full
   qualification round on v89/v90: it contains an automatic Bulb shot.

The immutable local diagnostic input is
`out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk`,
SHA-256 `8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`.
It is already patched and must not be passed off as pristine stock or modified
in place. The preserved diagnostic reconstructs only its verified patch effects
in memory. Obtain release inputs through the stock-packet runbook.

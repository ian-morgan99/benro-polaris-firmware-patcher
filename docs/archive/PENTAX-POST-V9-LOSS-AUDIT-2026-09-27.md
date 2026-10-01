# Pentax post-v9 loss audit — 2026-09-27

## Scope and method

This audit covers the three convergence repositories only:

- `ian-morgan99/libgphoto2`;
- `ian-morgan99/benro-polaris-firmware-patcher`;
- `ian-morgan99/benro-polaris-test-harness`.

OpenPolaris is deliberately out of scope. The comparison used Git ancestry,
`git cherry` patch equivalence, semantic symbol/control comparison, every
Pentax-related remote branch, all GitHub PR review comments, and the firmware
provenance ledger. A commit being absent by SHA is not by itself a loss: rebased
or reconstructed equivalents are classified separately.

Audit target for libgphoto2: PR #90 head `75f9e4b1e`. Audit target for the
patcher: PR #156 head `734b19a`. Harness target: PR #13 head `a8b658173`.

## Confirmed omissions

| Item | Where it originally existed | Current state | Consequence | Required disposition |
|---|---|---|---|---|
| Restore the normal PTP port timeout on every abnormal capture exit | libgphoto2 PR #78, commit `983373767`, mixed with rejected high-ISO work | Missing from PR #90; isolated and corrected in PR #92 head `27b6c3314` | A cancel, conditions error or timeout can leave later PTP operations with a minutes/hours timeout and appear hung | Retain PR #92; include it in the final convergence SHA |
| Restore normal timeout before metadata/transfer after a normal exposure wait | Original pre-review capture path; fresh PR #92 review | Corrected in PR #92 head `27b6c3314` | A stalled transfer could inherit the exposure timeout and defeat bounded transfer/cancellation checks | Retain PR #92 corrected head |
| Preserve strict next-shutter admission as the sole runtime authority | libgphoto2 PR #89, commit `0a23d07f9` | **Not an ancestor of PR #90 head** | `PENTAX_ADMISSION_MODE=output-safe` can authorize an unproven shutter predicate | Merge/rebase PR #89 before constructing the convergence SHA; add an ancestry gate |
| Attribute capture timeout using the last camera activity flags | libgphoto2 PR #78, commit `983373767` | Missing from PR #90; isolated in PR #93 head `23023c2be` | Processing timeout is mislabeled as exposure timeout, obscuring the first failing phase | Retain PR #93 after review; it excludes high ISO and adds deterministic phase classification |
| Exact long-duration shutter labels and reverse mapping | Behaviour request after the v9 line; initial minute support in `dacfc8986` handled only exact minute values | Implemented in PR #91 head `957b5ab58`; overflow review fixed | 80/90 second choices remain hard to scan without exact `1m20s`/`1m30s` labels | Retain PR #91; preserve exact reversible values rather than rounding |
| Atomic stale launch/supervisor lock takeover | patcher issue #104 / PR #100 review | **Still absent** although #104 was closed as superseded by open #146 | Concurrent reclaimers can delete a replacement live lock and launch/restart duplicate owners | Implement under #146 with generation identity and deterministic replacement-race coverage |
| Dirty diagnostic artifact mechanically barred from release | patcher PR #100 review | Warning/hash exist, but no explicit source-policy field or package/release rejection was found | A dirty diagnostic build can look like a normal candidate after handoff | Add explicit `clean`/`dirty-diagnostic` provenance and fail the release/registry gate on the latter |

## Present by equivalent reconstruction — not lost

The August pre-rebase branch `backup/pre-rebase-2026-08-24` does not share
ancestry with the current convergence line, but its accepted ptp2 implementation
was reconstructed on the later upstream base. Subject-by-subject equivalents
exist from `342c053ae` through `adb5efcc6`, covering:

- guarded Pentax vendor-mode core and model gates;
- candidate transfer/finalisation and transfer fault handling;
- preview state restoration, bounded preview retry and complete-JPEG checks;
- condition parsing, verified shutter/ISO/exposure writes and aperture parsing;
- focus drive, focus peaking, PC-LV, bracketing, composition and model gates;
- keep-live-view and capability controls.

The semantic inventory found no old-only `pentax_*` helper or configuration key
at the August tip. Later accepted lifecycle/ownership commits `121675124`,
`35318c1b5`, `d0419942d`, `a46421c8e`, `ab0de090c`, `c57a8a3ac`,
`62402cc2c` and `d8c0c0026` are all in PR #90 ancestry.

The patcher PR #156 line contains patch-equivalent versions of the v9 release
and runtime fixes: clean-tree checks, fail-propagating deterministic runner,
capture/preview isolation, bounded restart policy, selected-camera fingerprint,
settle/rebind handling, direct still-capture dispatch and config pass-through.
The two unique PR #100 commits not represented are documentation/cache-ignore
changes, not runtime fixes.

Harness PR #13 has no competing or abandoned branch. Its generation/stale
completion contract is present at `a8b658173`, but remains open rather than
merged.

## Intentionally excluded or still unqualified

These are not losses and must not be silently restored:

- PR #78 high-ISO synthesis: rejected because camera/mode descriptor evidence
  and setter admission were unsafe/incomplete.
- PR #79 Star AF / `0xd038`: still hardware-unqualified.
- archived `pentaxmodern` branches: superseded by the ptp2 implementation;
  their model IDs and named capabilities were checked semantically.
- PR #157 multi-camlib packaging: open and not part of PR #156. It is pending
  integration, not missing Pentax runtime behaviour.
- PR #90 publication changes: code fixes exist, but production-path regressions
  and capture-to-disconnect lifecycle analysis remain incomplete; it is not yet
  a release input.

## How the omissions happened

1. **Mixed-purpose commits.** PR #78 bundled valid capture cleanup/diagnostics
   with unsafe high-ISO synthesis. Closing the feature PR discarded the valid
   independent changes with it.
2. **Sibling stacked PRs without an ancestry gate.** PR #89 targeted PR #87,
   while PR #90 was independently based on the older convergence head. Review
   text said #89 was required, but no machine check required its commit in the
   eventual build SHA.
3. **Reconstruction instead of a merge train.** The August Pentax work was
   replayed onto a new upstream history. Git SHA ancestry stopped being useful,
   while the earlier issue #40 audit covered the obsolete `pentaxmodern`
   branches, not every later feature/rescue/release branch.
4. **“Superseded” closed the record, not the acceptance criterion.** Patcher
   #104 was closed in favour of #146, but the concrete atomic-lock requirement
   was not converted into a coded gate and current code still has the defect.
5. **Artifact pins captured one branch head, not the required patch set.** The
   provenance ledger accurately records what was built, but did not assert that
   all mandatory review commits were ancestors of the embedded libgphoto2 SHA.
6. **Tests detect regressions in code that is present, not omitted commits.** A
   focused suite can be green while an independently reviewed sibling fix never
   entered the selected source SHA.

## Required prevention gates

Before the next firmware build:

1. Create one immutable libgphoto2 convergence commit containing the reviewed
   PR #90 result plus PR #89, PR #91, PR #92 and PR #93's activity-phase
   fix. Do not build from a moving PR branch.
2. Add a machine-readable required-commit/semantic-feature manifest to the
   patcher build. Fail unless every required commit is an ancestor of the source
   SHA, or an explicitly recorded replacement commit supplies the named test.
3. Add the lock-generation/replacement-race tests and implementation under
   patcher #146 before claiming reconnect ownership deterministic.
4. Make dirty-diagnostic provenance mechanically non-releaseable.
5. Merge harness PR #13 (after review) so the generation contract is on its
   canonical branch rather than another long-lived side branch.
6. Run the complete deterministic gates only after the single convergence SHA
   exists, then package one candidate and verify the embedded component hashes.

## Current release decision

**Do not build or install another candidate yet.** PR #91/#92 are corrected and
tested, and PR #93 is source-tested, but PR #89 is absent from PR #90
ancestry, PR #90's production-path test/analysis work is incomplete,
and the patcher lock takeover remains nondeterministic.

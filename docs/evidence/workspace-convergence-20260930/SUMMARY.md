# Workspace convergence verification — completed 2026-10-01

- **PASS:** 42 worktree registrations across four Git stores reduced to three
  canonical delivery worktrees. Twenty-seven registrations already pointed to
  missing directories; remaining noncanonical worktrees were archived and retired.
- **PASS:** 38 local branches reduced to `main` only in each of the three active
  delivery repositories. The overlapping NINA/research Git metadata is archived,
  while its working research files stay at their original paths.
- **PASS:** PrivateResearch preservation commit `74fde6402` was pushed and
  independently verified before retirement; completion records are in `383cc8c4d`.
  Every bundle/part SHA and live archived worktree file/symlink was rechecked.
- **PASS:** Both immutable library prefix relocations preserve all 75 regular
  file hashes; actual relocated camlib classifier and CLI loader checks pass.
- **PASS:** Patcher offline gate: 16 container checks and 25 Python tests, with
  two nested prerequisite skips (`test_polaris_pentax_build_package.sh` and
  `test_source_input.sh`). The aggregate zero-skip count omits these nested skips.
- **PRESERVED:** Original user stash, OpenPolaris untracked post-update evidence,
  and two unrelated PrivateResearch untracked app build files. Authored StarShoot
  plan and current Pentax evidence are recovered into canonical patcher main.
- **NOT TESTED:** Device runtime, physical camera capture/recovery, package gate.
  No new firmware was built or installed. K-3 III was still absent from host USB
  on 2026-10-01; no camera operation was issued.

`inventory-before-delivery.txt` records the source heads and canonical ownership
before the final docs commit. Exact post-push identities are recorded in the
private convergence archive's final delivery record and issue #149. The tested
code is unchanged by this documentation/archival commit.

See `../../WORKSPACE-CONVERGENCE-20260930.md` for branch-by-branch disposition
and recovery instructions. No deferred or rejected feature patch was silently
promoted to firmware main to reduce branch counts.

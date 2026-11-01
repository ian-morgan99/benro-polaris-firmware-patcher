# Astro / standard-camera integration handoff

Review date: 2026-11-01

This record separates the Astro variant from the shared camera and release
baseline. It is deliberately written before any merge or rebase because the
Astro worktree contains another agent's uncommitted changes.

## Worktree inventory

| role | worktree | branch | commit | state |
|---|---|---|---|---|
| Astro owner | `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher` | `feature/astro-native-platesolve` | `5b6c5879e178e3f402859cd5283db20cd669fa90` | local branch one commit ahead of origin; dirty |
| standard camera owner | `/home/ian/polaris-build-73` | `main` | `8c015c0a73c8affea8fa723badcceb4070ef81b4` | matches origin; existing untracked #251 evidence preserved |
| libgphoto2 canonical input | `/home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main` | `main` | `051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff` | clean |

The adjacent `/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2`
checkout is `feature/polaris-capture-events` at
`908d272ee99938339f1f5be081a99df38a2d4556`, not the canonical clean `main`
input. It must not be substituted silently.

## Shared camera/release work

The following committed Astro-branch history is shared camera/release or
release-process work and is not Astro-owned:

- `977c86b`, `3d41493`, `ab4135c`, and `2c68c2b`: firmware installation and
  v71 release evidence;
- `8c7a973` and `864b70a`: K-1 II and Bulb evidence;
- `4e4c75a`: Bluetooth wake/preflight behaviour;
- `11c2823`: crash-session evidence collection.

The current dirty worktree also contains shared/unaccepted changes in the
Stage-2 loader, release/install/provenance scripts and documents, prerelease
tests, harness evidence, and release identity helpers. These include
`container/stage2_loader.c`, `container/test_stage2_empty_choice_guard.*`,
`scripts/build-release-candidate.sh`, `scripts/release/release-fwpkt.sh`,
`scripts/polaris-bt-probe.sh`, `tests/run_prerelease_gate.sh`, and their
associated release/harness documentation.

They remain owned by the camera/release work and are not included in the Astro
integration. In particular, Astro must not retain a competing #251 Stage-2
implementation. The standard issue handoff records that #251 is still
release-blocking; its cancellation diagnostic remains RED even though the
dispatcher source and offline tests have advanced.

The current standard source tip is `8c015c0a`, but the camera owner has not yet
designated an accepted Astro handoff commit. It is therefore recorded as the
proposed source baseline, not as physically qualified firmware.

## Astro-owned work

The Astro feature set is the committed work under:

- `build-astro.sh` and the `container/astro/` native C, shell, catalogue,
  solver, WebUI, simulator and test tree;
- `tools/` catalogue, geometry, pointing-model, rate-safety and verification
  tools added by the Astro work;
- Astro solver, capture-flow, EXIF, catalogue, motor-rate boundary, and mission
  readiness documentation;
- the Astro-specific tests and evidence under `container/astro/tests/` and
  `docs/evidence/dual-solver-*`, `native-*`, and related Astro records.

The native rate planner and fake-head/wire tests are Astro research features;
they do not prove or enable a live firmware motor-rate command. The rate path
remains gated on issue #240 / PrivateResearch issue #3.

## Integration contract

1. The camera owner designates one accepted standard patcher commit and one
   clean `libgphoto2` `main` commit.
2. Astro integration is prepared in a clean staging worktree from that exact
   standard commit. The dirty Astro checkout is not stashed, reset, rebased,
   merged over, or used for a release build.
3. Only Astro-owned commits/files are applied to the standard baseline. Shared
   camera/release changes are transferred by commit identity, not recreated or
   cherry-picked from the Astro dirty tree.
4. Every camera-adjacent difference is audited. Any intentional Astro change
   to capture scheduling, session ownership, file publication, or lifecycle
   behaviour requires an explicit integration test and an explanation here.
5. The Astro candidate receives a distinct registry ID and packet path. Its
   manifest must name the standard camera baseline, Astro commit/features,
   exact libgphoto2 commit, stock-package hash, and final ZIP/appfs hashes.
6. The shared camera harness and Astro-specific tests run against the actual
   Astro artifact. Standard-firmware results are not reused as Astro evidence.
7. No device deployment occurs until the camera owner confirms the test window;
   only the documented FwPkt/Bluetooth-wake process may be used.

## Current decision

No merge or rebase has been performed. No camera code has been changed by the
Astro owner. The next safe action is to integrate the owner-designated standard
commit in a clean staging worktree and then audit the resulting camera diff.

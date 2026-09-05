# Canonical Pentax source — what to build, and what to ignore

After the August-2026 libgphoto2 consolidation (the one that absorbed the
Pentax matrix evidence into a single master branch), several other
branches were left in the working fork. Some of them contain useful
additional work; most of them are exploratory attempts that **do not**
belong in the canonical source. This document says which is which, and
gives a single SHA to build from.

## TL;DR — build this

| What | Where | Commit |
|---|---|---|
| **libgphoto2** (the Pentax camlib) | `https://github.com/ian-morgan99/libgphoto2.git` branch `master` | **`da8c33482e674692023fddcf32cb73d1dd4da05d`** |
| Polar-patcher (the consumer) | `https://github.com/ian-morgan99/BenroPolarisFirmwarePatcher.git` branch `agents/attachment-plan-follow-up` | (the worktree HEAD at the time of build — pinned in `docs/TESTED.md` for each validated release) |
| Target firmware | Benro Polaris `FwVer 4.0.0.32` (date 2025.05.09) | unchanged |

The rest of this document explains what *else* exists in the fork and
why we are **not** building from it.

## The canonical `master`

`master` at `da8c33482` carries the consolidated Pentax matrix work:

- `ptp2/pentax-utils.c` (K-3 III Astro mode, vendor 0x9011, battery-pull
  recovery, K-1 II 4-capture DNG regression, K-1 II smart storage
  selector, K-3 III post-power-cycle vendor wedge, K-3 III vendor
  wedge recurrence).
- The "durable vendor-state reconciliation" change
  (`106ae5f98` — widens the unsafe-activity barrier so the wedge cannot
  re-arm during a settle window).
- The "0-byte DNG download" fix (`1340d8bd1` — fs-cache refcount, also
  kills the spurious delete error).
- `8ba60c3e7` — stale-session recovery (close + USB port reset + reopen,
  plus `CameraShutdown` on exit).

The Pentax camlib used by the rebuilt `ptp2.so` is `camlibs/pentax/`
(mature pslr-based), with model detection entries in
`camlibs/ptp2/pentax-utils.c`. There is no separate `pentaxmodern/`
camlib in canonical master — see the next section.

## The other branches — do **not** build from these

| Branch | Tip SHA | Reason it is not canonical |
|---|---|---|
| `origin/c99-compliance-pentax` | `8567b212a` | Adds an independent `camlibs/pentaxmodern/` directory (1786 insertions). Uses its own protocol layer that does not share state with `ptp2`. Not exercised on the Benro Polaris. |
| `origin/copilot/add-failed-print-detection` | `6dc3819ac` | Branched from a pre-consolidation point (`a5dede52`). Contains speculative work and an "Initial plan" commit that is not in master. |
| `origin/fix-pentax-deps` | `023322793` | Same `pentaxmodern/` camlib as `c99-compliance-pentax`, plus Meson build plumbing. Not in master because the canonical Pentax support is in the `pentax/` camlib, not `pentaxmodern/`. |
| `origin/pentax-modern-integration` | `173d9848e` | Earliest of the `pentaxmodern/` family. Also contains a model-handling split based on a C# reference (`imagetransmitter2`) that is not in master. |
| `backup/pre-rebase-2026-08-24` | `79969033b` | Pre-rebase backup; all of its useful content has been re-applied to `master` via the rebase of 2026-08-24 / 2026-08-26. Kept for archaeological reasons only. |

**All four "pentaxmodern" branches share the same fork-base** (a
libtool bump `bfce85402`); none of them is a descendant of the
canonical Pentax matrix. They are **archived**, not merged.

## How the patcher picks the source

The patcher's `build_ptp2.sh` (lines 41-58) takes input from one of
three sources, in priority order:

1. `/libgphoto2-source-input` mounted as a **directory** (must be a git
   checkout; if dirty, `ALLOW_DIRTY_SOURCE=1` is required to proceed).
2. `/libgphoto2-source-input` mounted as an **archive** (tar.xz or
   tar.bz2; SHA-256 is captured as `SOURCE_INPUT_SHA256` for
   reproducibility).
3. A downloaded tarball from `gphoto/libgphoto2` GitHub release.

For the e2e regression test and the reproduction build we use path (2)
with a tarball of `da8c33482`; the source-provenance block in
`/out/build-source-provenance.txt` records the exact SHA, the tarball
SHA-256, and which build path was taken. See
`container/test_polaris_pentax_build_package.sh` step 2 for the assertion.

## Re-deriving the canonical SHA

The following command, run from the libgphoto2 working tree, should
print `da8c33482e674692023fddcf32cb73d1dd4da05d`:

```bash
git rev-parse master
```

The Pentax matrix evidence is the chain of `docs(pentax): …` commits at
the tip of master, plus the `ptp2/pentax: …` driver fixes
(`8ba60c3e7`, `106ae5f98`, `1340d8bd1`, etc.) immediately below them.
If those commits are missing or replaced, the canonical pointer in
this document is stale — file an issue and re-pin.

## What to do if you want to re-merge `pentaxmodern/`

The four `pentaxmodern/` branches are kept under `archive/` in the
fork (see the `archive-stale` work) for reference. If a future user
wants to attempt a merge:

1. Pick one of the four branches (start with `pentax-modern-integration`
   — it is the oldest and cleanest of the family).
2. Re-base it onto current master; expect a moderate number of textual
   conflicts in `camlibs/ptp2/pentax-utils.c` and `camlibs/ptp2/library.c`.
3. Verify the merged build reproduces the canonical Pentax matrix
   (K-3 III Astro mode 0x9011, K-1 II smart storage, vendor wedge
   recovery) AND the `pentaxmodern/`-specific capability — those two
   are independent of each other in the canonical code.
4. Update the canonical pointer in this document to the new merge SHA.
   Do not delete this document; the older pointer is part of the
   evidence trail.

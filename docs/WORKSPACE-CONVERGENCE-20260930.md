# Pentax workspace convergence — 2026-09-30

Completed 2026-10-01: **42 → 3 active worktree registrations; 38 → 3 active
local branches**. Each delivery repository now has one worktree and `main` only.
The private preservation upload was independently verified at
`74fde6402b329120bc38779c2b07bce84895c601` before retiring the source workspaces.

The delivery line is **main in each owning repository**. Temporary diagnostic
or release worktrees are not independent delivery forks. The inventory found
42 worktree registrations (15 existing, 27 missing) and 38 local branches across
four Git stores. GitHub already exposed only `main` in each delivery fork;
most fragmentation was local and included stale registrations for deleted
`/tmp` directories.

## Canonical ownership

| Purpose | Canonical checkout under `/home/ian/Documents/VSCodeProjects` | Delivery ref |
| --- | --- | --- |
| Firmware packaging, Stage-2 and lifecycle integration | `BenroPolarisPatcher` | `ian-morgan99/benro-polaris-firmware-patcher:main` |
| Camera library | `LibGphoto2/libgphoto2` | `ian-morgan99/libgphoto2:main` at `df64a63300585dbd8642861d760668b1ace92f78` |
| Application | `OpenPolaris` | `ian-morgan99/OpenPolaris:main` at `5345e5e173fc8f057404d80d1ff394e5009821c9` |

The parent `LibGphoto2` directory contained an overlapping checkout with origin
`ian-morgan99/nina-pentax-spec`, on a one-off combined-UVC build branch. It is
**research material, not the canonical library source**. Its documentation,
IT2 corpus and evidence stay at their existing paths. Its Git metadata and
all historical branches are preserved in the archive; retiring that overlapping
checkout prevents its tracked core directory from being confused with the nested
library repository. No NINA remote branch is changed.

## Preservation and recovery

Private archive:
[PrivateResearch, archives/pentax-workspace-convergence/20260930](https://github.com/ian-morgan99/PrivateResearch/tree/main/archives/pentax-workspace-convergence/20260930).
The initial preservation commit is `74fde6402`; the archive README, manifests
and final verification identify subsequent completion records.

- `inventory-before.json`: original branches, SHAs, dirty files and all worktrees.
- Four verified Git bundles: every ref plus each detached worktree head,
  including missing worktree registrations; existing stash history is included.
- Complete tar snapshots of every existing noncanonical worktree, including
  ignored build files, plus the patcher main's dirty files/directories.
- `archives.json`: full-file hashes and ordered split-part hashes. Parts are
  at most 45 MiB; concatenate in lexical order and verify the full hash.
- Every regular tar member was compared byte-for-byte with its source before
  retirement. Large original payloads are also retained locally under
  `.retired-repositories/pentax-20260930/payloads`.
- `restored-working-files.json` records authored notes and current evidence
  recovered into the canonical patcher. Remaining raw/snapshot material stays
  recoverable in the private archive, not in a detached active worktree.

To recover a branch, reconstruct its named bundle, verify SHA-256, and clone
it to a deliberate temporary location. Select the original ref recorded in
`inventory-before.json`. Extract dirty/ignored files from the matching tar to a
separate directory. Never apply an entire historical tree over current `main`.
Archived `.git` pointer files are historical metadata, not standalone Git stores.

The two exact-source test prefixes are kept at
`LibGphoto2/libgphoto2/_baselines/<full-source-sha>/prefix` for `fbc2e7e65`
(installed lineage) and `df64a6330` (current source). Each has a manifest of all
75 regular installed files; relocation preserved every hash. These are ignored
immutable test fixtures, with no Git branch or worktree registration. Their
complete original build/source trees remain in the private archive.

## Branch disposition

| Original branches | Disposition and reason |
| --- | --- |
| Patcher `main` at a7601b7 | Fast-forwarded through all 14 missing main commits; current source investigation delivered here. No rebase/reset. |
| Patcher `fix/pentax-orphan-recovery-20260930` | Investigation commit fast-forwarded into canonical main; temporary workspace retired. |
| Patcher `agents/attachment-plan-follow-up` | Archived. Old process-global init logging/backoff experiment, not an approved replacement for current identity-based lifecycle ownership. No pending remote PR. |
| Patcher `agents/benro-polaris-firmware-docs`, `agents/libgphoto2-only-fork` | Archived together. Unique HDMI research/static geometry implementation is deferred, not qualified Pentax recovery work. The latter is an earlier subset of the former. Recover from its bundle when the HDMI task is explicitly resumed. |
| Patcher `fix/release-safety-gates` | Closed PR #100 already records applicable gates incorporated on main; remaining historical evidence preserved. |
| Patcher `fix/stage2-direct-capture-20260924` | Closed PR #138 explicitly superseded by merged direct-capture convergence; do not reintroduce its obsolete release/artifact state. |
| Patcher `rescue/shutter-thermal-20260922` | Closed PR #130 records archived historical evidence; obsolete runtime lineage is not merged. |
| Patcher `audit/final-handover-20260924`, `convergence/pentax-candidate-20260925`, `release/o-v13d-review-convergence-20260926`, `rescue/final-shutter-20260923` | Already ancestors of current main; retired. |
| Patcher `fix/multifamily-camera-packaging-20260926` | Patch-equivalent change already on main; archived original head, retired. |
| Library `feature/pentax-iso-highrange` | PR #78 explicitly closed as unsafe/superseded. Do not merge synthetic ISO ranges over camera-mode restrictions. Original work is recoverable. |
| Library `feature/pentax-star-af` | Closed, unmerged PR #79; preserved as deferred feature work, not promoted into a stability fix or qualification claim. |
| Library `fix/pentax-timeout-phase-attribution-20260927` | PR #93 closed as incorporated/superseded; preserve exact former head. |
| Library `backup/pre-rebase-2026-08-24`, `pr/pentax-docs-2026-08-29`, `pr/pentax-p0-2026-08-26` | Historical rebased/upstream-review lines archived with all objects. Do not merge their broad old generic PTP2 history into current Pentax work. |
| Library `master` | Historical hardware/probe evidence preserved in archive; main is the sole delivery branch. |
| Library `convergence/pentax-admission-20260925`, `convergence/pentax-restored-fixes-20260927`, `fix/pentax-capture-publication-145`, `pr/pentax-portfolio-v1`, `rescue/final-shutter-20260923`, `rescue/shutter-observability-20260922` | Already ancestors of main; retired. |
| Library `fix/pentax-admission-review-20260926`, `fix/pentax-minute-duration-labels-20260927`, `fix/pentax-port-timeout-cleanup-20260927` | Patch-equivalent changes already on main; original heads archived, retired. |
| Research parent `build/combined-uvc-pentax-20260928` | Retired as a build source. Its added table incorrectly groups measured vendor-specific StarShoot with UVC; current owning-library table/test is authoritative. No cherry-pick. |
| Research parent `main`, `issue-85-uvc-ipolar`, `agents/hardware-testing-research-k3iii` | Research/NINA history and unique notes preserved, including the untracked hardware summary; not alternative library delivery branches. Normative research files remain accessible at existing paths. |
| Research parent `fix/pentax-capture-publication-145` | Historical library PR head already superseded; archived. |
| OpenPolaris `agents/desktop-executable-github-release`, `codex/issue-90-capture` | Both already ancestors of application main; worktrees and local branches retired. |

Release tags and provenance history are retained. Upstream remote-tracking refs
are references, not delivery branches; they are not deleted. No force-push or
upstream merge is part of this cleanup.

## Preserved dirty work and verification

The patcher loader's 59-line dirty diagnostic change was already present on
remote main; its only remaining difference was comment whitespace. The local
`CURRENT-STATE.md` edit removed newer installation/failure evidence; its exact
bytes are archived rather than reapplied as a false rollback of current state.
The StarShoot plan and link are preserved as historical authored notes, and the
current Pentax assessments and ordinary two-shot evidence are integrated.

The existing OpenPolaris untracked post-update probe directory is untouched.
PrivateResearch's unrelated two untracked app build files are untouched.
The pre-existing patcher stash is retained as user-owned prior work. The cleanup-created
stash was dropped only after its exact dirty state was privately archived and
selected authored files were restored. Its SHA/disposition is recorded privately.

Final branch/worktree counts, local/remote SHAs, clean-source status, offline gate
output and archived exceptions are recorded in `evidence/workspace-convergence-20260930/`.
Hardware recovery remains a separate pending task. Workspace convergence is not
firmware qualification.

One old o-v13x worktree contained root-owned container build output. Git removed
its registration but could not unlink those files. The remaining directory was
moved intact to `.retired-repositories/pentax-20260930/residual-trees/` without
changing permissions; its complete pre-retirement snapshot is also privately
archived. It is not an active worktree. The original firmware ZIP/appfs hashes
were recomputed and matched the registry before relocation.

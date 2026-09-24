# Divergence Matrix — 2026-09-24 (vs codex baseline)

Audit of every local/remote branch, worktree, stash and untracked artifact across
the three repos, measured against the codex session baseline.

## Codex baseline identification

- Codex session: `rollout-2026-09-22T18-26-40` (codex_vscode, cwd BenroPolarisPatcher),
  started 2026-09-22 18:26 local, continued into 2026-09-23.
- Patcher baseline (pre-codex): `main @ 634af4f` (2026-09-22 11:57, "registry: add o-v12d") —
  merge-base of the codex branch `rescue/shutter-thermal-20260922`.
- LibGphoto2 baseline: `master @ c57a8a3ac` (merge-base of codex branches
  `rescue/shutter-observability-20260922` and `rescue/final-shutter-20260923`).

## BenroPolarisPatcher — branch matrix (main @ e10c776)

| Branch | Ahead | Behind | Divergence date | Content / status |
|---|---|---|---|---|
| `fix/stage2-direct-capture-20260924` | 9 | 0 | 2026-09-24 | **Live head.** 073f471 direct still-capture fix + o-v12o/o-v12p registry/docs. PR #138 OPEN, mergeable. |
| `rescue/shutter-thermal-20260922` (codex) | 5 | 34 | 2026-09-22 | o-v12e/v12f registry + evidence. 4/5 superseded by main ledger (o-v12f row present); **o-v12e registry entry missing from main**. |
| `fix/release-safety-gates` | 12 | 325 | 2026-09-14 | 10/12 already in main by subject; unique: 142d5af (provenance doc), d5b2fd8 (gitignore chore). Tracked by issues #101–#107. |
| `agents/benro-polaris-firmware-docs` | 14 | 478 | 2026-08-21 | HDMI/EDID docs + patch scripts. Missing from main: `container/gen_hdmi_edid.py`, `hdmi_edid_patch.py`, `hdmi_venc_patch.py`, `ondisk/pgphoto.wrapper`. Tracked by #106/#107. |
| `agents/libgphoto2-only-fork` | 8 | 478 | 2026-08-21 | Strict subset of the docs branch (8 of its 14 commits). |
| `audit/final-handover-20260924` | 0 | 6 | 2026-09-24 | Pointer only — safe to delete. |
| `integrate/stability-20260916` | 0 | 79 | 2026-09-16 | Fully merged — safe to delete. |
| `agents/astro-mode-forks-review` | 0 | 475 | 2026-08-28 | Merged; worktree has untracked `analysis/` (3 md files). |
| `agents/attachment-plan-follow-up` | 0 | 455 | 2026-08-27 | Merged; **worktree has uncommitted `container/stage2_loader.c`** (init-log rate-limiter + no-camera backoff, STAGE2_INIT_LOG_EVERY / STAGE2_NO_CAMERA_BACKOFF_SECS) — not in main, not in stash. |
| `agents/check-connection-status` | 0 | 449 | 2026-09-02 | Merged — safe to delete. |
| `agents/phase-3-cellular` | 0 | 466 | 2026-08-31 | Merged — safe to delete. |
| `agents/work-out-why-our-firmware-just-disappears-when` (+ `.live-dup`) | 0 | 460 | 2026-08-30 | Merged; archive worktrees show staged deletions of 3 docs (POLESTAR_APP_REVERSE_ENGINEERING.md, diagnostic-test-card-matrix.md, tools/build_test_cards.py) — all later deleted on main by db1dce9 (issue #116 archive). |
| `origin/diagnostic/128-config-pass-through` (remote-only) | 0 | 43 | 2026-09-21 | Merged — safe to delete remotely. |

### Patcher unpushed / uncommitted / untracked

- **Local main is ahead of origin/main** (4+ commits at time of writing, all unpushed):
  e10c776 "test: add mandatory deterministic pre-release gate + codify agent rules",
  the divergence-matrix commit, and its correction commits. Push when ready.
- PR #138 (`fix/stage2-direct-capture-20260924`, head c474e9c) OPEN + mergeable.
- Stash@{0} (3 files, −242/+14): removes POLESTAR_BULB_PATCH block from patch.sh,
  trims stage2_loader.c — older experiment; main still ships the bulb patch.
  Distinct change-set from the attachment-plan worktree diff (verified by patch diff).
- Untracked in main worktree: `GITHUB_ISSUE_ORION_STARSHOOT.md`,
  `GITHUB_ISSUE_UVC_SUPPORT.md` (drafts behind #137/#135),
  `IOPTRON_IPOLAR_TEST_SUMMARY.md`, `docs/FUTURE-UVC-SUPPORT.md`,
  `test_ioptron.py`, `test_ioptron_v1.py`, and
  `docs/evidence/o-v12n-clean-raw-failure-2026-09-24/` (Clog/Mlog/dmesg/device-state;
  only SUMMARY.md is tracked).

## LibGphoto2 — branch matrix (remote master @ c57a8a3ac)

| Branch | Ahead of master | Status |
|---|---|---|
| local `main` | **8** | Unpushed docs/evidence commits (e9061402f…10118e5d7, 2026-09-01→09-08). 0 behind. |
| `agents/hardware-testing-research-k3iii` | 0 (contained in local main) | Worktree has untracked `HARDWARE_TEST_SUMMARY_2026-09-06.md`. |
| `feature/pentax-iso-highrange` | 5 | PR #78 OPEN but **CONFLICTING** (ISO high-range, issue #77) — needs rebase. |
| `feature/pentax-star-af` | 2 | PR #79 OPEN (Star AF / 0xd038, issue #76). |
| `rescue/shutter-observability-20260922` (codex) | 2 | PR #80 OPEN. |
| `rescue/final-shutter-20260923` (codex) | 9 | PR #81 OPEN — includes ab0de090c companion-buffer ownership fix (o-v12n lineage) + regression test 74d9e1f50. **Not in master.** |
| `libgphoto2/` nested clone (untracked, 454M @ c57a8a3ac) | — | Dirty: modified `docs/pentax/REAL_HARDWARE_TEST_LOG.md`, untracked `docs/pentax/evidence/2026-09-24-k3iii-bulb-ev/` + `-iso/`, `examples/pentax-k3iii-bulb-capture-probe.c`, `examples/pentax-k3iii-bulb-ev-probe.c` — today's (2026-09-24) uncommitted evidence. |
| `/tmp/libgphoto-v12n-clean` (worktree @ ab0de090c) | — | Clean build of the o-v12n companion-ownership fix; commit not in local main. |

## PrivateResearch

- `main` == `origin/main` (0/0, in sync). Latest: 161aaf5 o-v12p firmware packet.
- Untracked artifacts: `openpolaris-research/Benro-Connect/benro-connect-decompiled/`
  (519M), `benro-connect-java/` (336M), `pentax_firmware/gr4_v111.zip` (33M) +
  `gr4_v111_extracted/`, `.lmstudio/`, `.vscode/`; modified `LMStudioLogEnhancements.md`.

## Findings requiring action

1. Patcher: push e10c776 (main is 1 ahead of origin).
2. Patcher: PR #138 mergeable — decision needed (o-v12p head).
3. Patcher: o-v12e registry entry missing from main ledger (only o-v12f row present).
4. Patcher: uncommitted stage2_loader.c rate-limiter/backoff in attachment-plan worktree — commit or discard.
5. Patcher: stash@{0} is a superseded bulb-patch experiment — keep or drop.
6. Patcher: 7 untracked ioptron/UVC drafts + o-v12n-clean-raw-failure evidence (4 files) untracked.
7. LibGphoto2: local main 8 commits ahead of master (unpushed docs).
8. LibGphoto2: PRs #78/#79/#80/#81 all open; o-v12n companion-ownership fix (ab0de090c) only on PR #81.
9. LibGphoto2: nested 454M clone dirty with today's K-3 III bulb/EV + ISO evidence (uncommitted).
10. PrivateResearch: 888M+ of untracked decompiled/JAVA/firmware artifacts; main in sync.

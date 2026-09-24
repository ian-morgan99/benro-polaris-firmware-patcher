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

1. Patcher: push e10c776 (main is 1 ahead of origin). **DONE 2026-09-24.**
2. Patcher: PR #138 mergeable — decision needed (o-v12p head). **Updated:** o-v12o installed, first RAW+JPEG transfer failed (-108, `sd //IMGP3609.JPG` doubled-slash); o-v12p installed, canary pending (camera not enumerated on Polaris after reboot).
3. Patcher: o-v12e registry entry missing from main ledger (only o-v12f row present). **Still open.**
4. Patcher: uncommitted stage2_loader.c rate-limiter/backoff in attachment-plan worktree — **COMMITTED** (77ecea1) in worktree branch.
5. Patcher: stash@{0} is a superseded bulb-patch experiment — keep or drop.
6. Patcher: 7 untracked ioptron/UVC drafts + o-v12n-clean-raw-failure evidence (4 files) untracked.
7. LibGphoto2: local main 8 commits ahead of master (unpushed docs).
8. LibGphoto2: PRs #78/#79/#80/#81 all open; o-v12n companion-ownership fix (ab0de090c) only on PR #81.
9. LibGphoto2: nested 454M clone dirty with today's K-3 III bulb/EV + ISO evidence (uncommitted).
10. PrivateResearch: 603M pentax_firmware + 519M benro-connect-decompiled + 336M benro-connect-java; main in sync.

## #143 audit results (2026-09-24)

### D1 inventory — complete
- Patcher main @ 22169e5 (pushed), 5 unpushed docs commits now on origin.
- PR #138 (fix/stage2-direct-capture-20260924, c474e9c): 17 files, direct Stage-2 capture dispatch + o-v12o/o-v12p registry/docs.
- Attachment-plan worktree diff COMMITTED (77ecea1): stage2_loader.c rate-limiter + no-camera backoff.
- Stash@{0}: superseded bulb-patch experiment, unmodified.
- Uncommitted tracked: patch.sh, restart_gphoto.sh, test script, settings.json (LMStudio bridge config).
- Untracked: 2 issue drafts, ioptron tests, FUTURE-UVC-SUPPORT.md, o-v12n crash evidence.
- LibGphoto2: local main 8 commits ahead; PRs #78/#79/#80/#81 open; nested clone dirty with today's K-3 III evidence.
- PrivateResearch: 888M+ untracked artifacts; main in sync.

### D2 lineage — corrected
- o-v12h provenance contract says "camera not enumerated after install"; ledger says "last first-capture working baseline" with Pixel Shift RAW+JPEG completion. **Contradiction — ledger overstates o-v12h.** The o-v12h evidence folder exists (docs/evidence/o-v12h-pixelshift-rawjpeg-2026-09-23/) but the contract status must be corrected: o-v12h was installed and the camera did NOT enumerate; no first-capture evidence exists for o-v12h.
- o-v12o/o-v12p rows exist in provenance contract (PR #138, not merged) but are MISSING from the divergence matrix. o-v12o installed 2026-09-24, first RAW+JPEG shutter reached state:4 but transfer failed (-108, `sd //IMGP3609.JPG` doubled-slash). o-v12p installed, canary pending (camera not enumerated on Polaris after reboot).
- o-v12n clean RAW-only canary FAILED 2026-09-24: SIGSEGV at pc=0x4e20 (not in slot region), before gp_camera_capture(). Stage-2 callback/slot/ABI boundary is first owning layer.

### D3 first-success boundary
- Last broad repeated-capture PASS: o-v9p (397c362e1). Confirmed by physical evidence.
- o-v12h does NOT qualify as first-capture-working — camera did not enumerate after install.
- o-v12o removed the pre-dispatch SIGSEGV but RAW+JPEG transfer failed (-108).
- o-v12p canary pending.

### D4 first regression
- The 9p→9q/r/s/t interval needs source-level bisect. o-v12j/o-v12k/o-v12n all crashed at pc=0x4/0x4e20 before gp_camera_capture(). The crash symbol 0x4e20 is not in the slot region — likely a stale trampoline or misdirected boundary function. Needs symbol resolution against the stage2_loader.c slot table.

### D5 re-grade
- o-v12n companion-ownership fix (ab0de090c): Grade B (deterministic correctness for single-output; repeated capture unproven).
- o-v12o direct Stage-2 capture dispatch: Grade C (diagnostic — removed SIGSEGV but exposed -108 transfer divergence; not a behavioral fix yet).
- o-v12p mode-contract: Grade D (unproven — canary pending, camera not enumerated).

### D6 evidence corrections
- Ledger overstates o-v12h (claims Pixel Shift RAW+JPEG completion; contract says camera not enumerated).
- Divergence matrix missing o-v12o/o-v12p rows.
- o-v12n row status updated: "AWAITING FIRST-SHOT CANARY" → "FIRST-SHOT CANARY FAILED 2026-09-24".

### D7 #142 verdict — NOT YET READ
#142 must be read after D1-D6 are complete. Current independent evidence:
- o-v12p (the proposed control) is not yet proven — canary pending, camera not enumerated.
- The reconstruction base should be o-v9p (last proven broad repeated-capture), not o-v12p.
- A source bisect from o-v12p toward the first regression is the highest-value next action, targeting the 0x4e20 crash symbol.
- Later fixes safe to port: o-v12o's direct dispatch principle (once -108 divergence is understood), o-v12n's companion-ownership fix.
- Changes to NOT port: o-v12j/o-v12k LV policies (disproven by o-v12k clean A/B), o-v12h (unproven first-capture claim).
- Missing from #142's promotion ladder: the -108 companion transfer divergence (o-v12o), the 0x4e20 crash symbol analysis.

### D8 recommended plan — deferred until D7
See #143 for the full design template. No firmware candidate proposed.

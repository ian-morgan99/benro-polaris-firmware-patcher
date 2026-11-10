# Review of the polaris-v94 staged deletions — for the release owner

Reviewed 2026-11-09 against worktree `/home/ian/polaris-v94`, branch
`feature/astro-native-platesolve`. **Nothing here was committed or changed in that
worktree** — the staged state is yours, and this is a read-only review.

## What is staged

32 deletions and 20 modifications. The deletions fall into four groups:

| group | files |
|---|---|
| on-disk script + its tests | `container/astro/ondisk/polaris-astro-sync.sh`, `test_astro_inplace_update.sh` |
| WebUI reconcile/reporting tests | 4 files (`test_webui_exposure_reconcile.{js,sh}`, `test_webui_shutter_reporting.{js,sh}`) |
| release/qualification tooling | `scripts/camera-qualification-round.py`, `scripts/release/check-release-gates.py`, `scripts/resolve-release-inputs.sh`, `scripts/tail-polaris-logs.sh` |
| wifi/licence tests + docs | `test_setup_wifi_psk_not_in_argv.py`, `test_wifi_kit_packaging.py`, `test_wifi_licence_on_every_build_path.py`, `test_camera_qualification_round.py`, `tests/audit_astro_controls.py`, plus `docs/CAMERA-QUALIFICATION-ROUND.md`, `docs/WEBUI-MANUAL.md`, `docs/ISSUE-271-*`, `docs/release-change-summary-v99-wifi.json`, and the `k1ii-webui-20261107-camera-on/` evidence bundle |

## Mechanically it is clean — verified, not assumed

| check | result |
|---|---|
| `bash -n` on the staged `run_prerelease_gate.sh` | OK |
| deleted files referenced by the staged gate | none |
| `SKILL.md` still pointing at deleted tooling | no — updated consistently |
| dangling references anywhere in the tree | one only: a historical mention of `tail-polaris-logs.sh` inside `docs/evidence/liveview-crash-camera-offbus-20261103/SUMMARY.md`, which is a record of what was run at the time and is harmless |
| drift guard self-consistency | 33 suites listed in `PY_TESTS`, 33 `tests/test_*.py` in the index, zero drift either direction |

So this will not break the build or leave the gate inconsistent. That is worth stating
plainly because it is the part that can be checked offline and it passes.

## The one thing I would not ship without a decision

**`tests/test_setup_wifi_psk_not_in_argv.py` is the only behavioural guard for #290, and
nothing replaces it.**

Verified in the staged tree:

- `git grep -ln 'wpa_passphrase|psk.*argv|PSK' -- tests/** container/**test*` → **no
  results**. After the deletion no test asserts anything about how the passphrase is passed.
- `grep -c 'setup-wifi\|setup_wifi' <staged gate>` → **0**. `setup-wifi.sh` is not exercised
  by the gate at all, before or after.
- The fix itself survives — staged `setup-wifi.sh` still pipes the passphrase on stdin and
  strips `#psk=`. So the code is right; only the guard against it regressing is gone.

The deleted test's own docstring explains why it exists:

> "This is how #290 survived: the comment asserted argv-free handling and reviewers read…"

It asserts on what the child process actually received rather than trusting a comment —
which is precisely the failure mode that has cost time this week (#285's "explains ALL the
failures", my own wrong `gp_camera_set_config` attribution). Deleting the test that checks
behaviour instead of prose is the wrong direction regardless of how tidy the tree looks.

`test_wifi_licence_on_every_build_path.py` is the same shape but narrower to state, so here
is what it actually asserts, read from the file rather than guessed:

- `test_licence_generation_lives_in_the_shared_builder` / `test_generation_is_reachable_without_the_wrapper`
  — that licence generation is reachable on **every** build path, not just via the wrapper.
- The expected filenames are "taken from the gate, not invented", because an earlier
  abandoned fix wrote `SOURCE-OFFER.txt`, which satisfies LGPL but fails the gate in
  `build-astro-bundle.sh` — so a later "fix" would rename the wrong file.
- `test_generation_fails_closed_without_source` and `test_empty_notice_is_rejected`.
- `test_candidate_path_produces_the_sd_archives` and `..._asserts_on_the_archive_not_the_staging_dir`
  — the candidate path "made no archive at all", which is a real shipped-bundle bug class.

After the deletion the only staged test touching licensing is `tests/test_plate_solving_present.py`,
which gates the GSL BSD-3 shim and `docs/LICENSE-AUDIT.md` presence. That is a different
concern: it keeps the *patcher* MIT, and does not cover the LGPL source offer or whether the
candidate path produces SD archives at all.

## What I could not determine, and why that matters

- **No rationale is recorded anywhere.** `git diff --cached CHANGELOG.md` and
  `docs/RELEASE-VERSION-STATE.md` contain no added line mentioning removal, deletion,
  retirement or pruning. A 32-file deletion with no changelog entry is indistinguishable
  from an accidental `git rm -r`, and the tree gives no way to tell which it is.
- **The deletions are staged but not committed**, so they are one careless
  `git commit -a` away from being permanent with no review step in between.
- The worktree is `behind origin/main: 1, ahead: 0`, and all four spot-checked files exist
  in `origin/main`. So these are deletions of content that main still has — not a
  divergence artifact.

## Recommendation

Before this is committed:

1. Restore `tests/test_setup_wifi_psk_not_in_argv.py`, or move its assertions somewhere the
   gate runs. Losing the only #290 guard silently is the highest-cost outcome available here.
2. Add a CHANGELOG entry naming what was removed and why. If the reason is "superseded by
   X", say so per file; if it is "these were device-only tests that never ran in CI", that
   is a legitimate reason but needs to be written down, because the drift guard will happily
   stay green either way — it checks that listed suites exist, not that coverage was kept.
3. If `camera-qualification-round.py` is genuinely being retired, note what replaces it.
   It is currently the only harness that captures pids, the single-`:1F90` listener check and
   crash signatures per round (referenced in the #285 thread as `a69fad2`).

Nothing here blocks on correctness of the modifications themselves — I did not review those
20 files line by line, and that is a gap in this review, not a clean result.

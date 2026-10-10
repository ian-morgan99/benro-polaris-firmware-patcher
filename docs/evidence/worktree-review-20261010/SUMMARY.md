# Worktree / branch reconciliation review — TODO set (2026-10-10)

Prompt for this review: the number of concurrent worktrees and branches had grown
without a single place saying what each one is for and what evidence backs it.
This document is that place. Every claim below was re-checked against the
repository, the committed evidence, or a command re-run in this session — not
against another agent's summary.

Scope: `BenroPolarisPatcher` only. No device command was sent while producing
this review; nothing here changed the Polaris.

## 1. Inventory as observed (2026-10-10T01:10Z)

| # | Object | State | Verdict |
| --- | --- | --- | --- |
| A | `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher` @ `main` `f7a7bd9` | canonical delivery checkout; **ahead of `origin/main` by 11**; dirty: `.vscode/settings.json` only | Keep. Actions T1–T4. |
| B | `/tmp/bpp-187-linkstate` @ `diag/187-watcher-link-state` `34ad4ba` | 1 commit on top of `main`; clean; touches `scripts/watch-app-crash.sh` + `tests/test_watch_app_crash.py` only | Keep until T5–T8 close, then retire per AGENTS.md. |
| C | `origin/codex/pentax-capture-recovery` `7159bb4` (#188) | **already an ancestor of `main`** (`git merge-base --is-ancestor` → true); no local branch, no worktree | Delete remote ref (T9). |
| D | `origin/main` `bd5fbb5` | fully contained in local `main` | Push (T1). |
| E | `upstream/*` (`blaineam/...`) | read-only upstream, not ours | No action. |
| F | Two `stash@{…}` on `main` | `preserve pre-existing CURRENT-STATE backup before fw-version release`; `pre-rescue other-agent rollback and local VSCode settings 2026-09-23` | Disposition required (T3). |
| G | `/tmp/app-crash-watch.log`, `/tmp/187-fix.md` | untracked scratch outside any worktree | Reconcile (T6, T7). |

No worktree exists for the bulb-shutter (#186) work, so the other agent is not
working in this repository's tree. **Do not mutate A's working tree in place
while it is active** — that is the reason B was forked rather than edited here.

## 2. What was actually verified in this session

These are the facts the TODOs below are allowed to rely on.

1. **B's offline gate is genuinely green, re-run here.**
   `./tests/run_prerelease_gate.sh` in `/tmp/bpp-187-linkstate` at
   `2026-10-10T01:11:08Z` → `5 passed, 0 failed, 0 skipped`, `GATE: GREEN`,
   exit 0 (deterministic harness 19 passed; python suite 219 passed; agent
   sandbox/config checks; code-780 patch check). Transcript:
   `gate-diag-20261010.log` alongside this file. The commit message's
   "219 passed" is reproducible, not aspirational.
2. **B's watcher tests pass in isolation:** `pytest tests/test_watch_app_crash.py`
   → 10 passed. Coverage names include
   `test_transport_loss_is_attributed_not_recorded_as_camera_state`,
   `test_camera_is_not_polled_while_the_link_is_down`,
   `test_service_down_is_distinguished_from_data_path_loss`,
   `test_route_off_the_wifi_interface_is_link_loss_not_reachability`,
   `test_camera_is_reobserved_after_recovery`,
   `test_watcher_does_not_replay_diagnostics_by_default`.
3. **The "seven transport losses" claim is exactly true.**
   `grep -c ' -> ?' docs/evidence/benro-connect-crash-20261008/raw/app-crash-watch-20261009-authorized-attempt.txt`
   → **7** (six between 15:56:46Z and 17:12:53Z, one at 19:20:12Z).
   The same file contains **0** lines matching `IDENTITY|LINK_|iw dev|route`,
   which confirms the diagnosis: the old watcher had no link attribution at all,
   so every transport loss was written as a camera observation.
4. **`/tmp/app-crash-watch.log` is byte-identical to the committed evidence**
   (`sha256 91cecdef…10e0` for both, `cmp` → identical). It is a duplicate, not
   a second capture.
5. **The `.60` bulb-patch premise in #187's body is falsified, and I re-derived
   it independently of the scratch notes:** `--polestar-bulb-patch` is present in
   `scripts/build-release-candidate.sh` at `0e6edd03` (o-v16a → `.60`) **and** at
   `4be4a5f0` (o-v16b → `.61`), and absent at `c0c4797^`. `c0c4797`
   ("release: include verified firmware Bulb patch") is dated **2026-10-02**, i.e.
   before `.60` was built. So "the app worked against `.60`, therefore the bulb
   patch is the prime suspect" does not hold.
6. **Cross-references in B's commit message resolve correctly:** #170, #171, #68,
   #186 all exist and are OPEN with titles matching how the message cites them;
   `scripts/control-liveness.py` really does implement the refused/unreachable
   split it claims to reuse (lines 96–106).
7. **B does satisfy the 2026-10-09 handover requirement** ("snapshot native Mlog
   before its diagnostic replay and mark replay client traffic separately"):
   `snapshot_device "before diagnostic replay"` precedes the replay block, the
   replay is opt-in (`WATCH_REPLAY=1`), and the replay line is labelled
   `not native phone traffic`.

## 3. TODOs

Ordered so that nothing destructive depends on anything unproven.

- [ ] **T1 — Push `main` (A → origin).** 11 unpushed commits, `origin/main`
      fully contained, no divergence. Until this is done the only copy of the
      #187/#188 evidence trail is one laptop.
      `git push origin main` then `git rev-parse main origin/main` must agree.
      *Blocks:* nothing. *Risk:* low (fast-forward).
- [ ] **T2 — Decide `.vscode/settings.json`.** The working-tree diff adds
      `lmstudio.contextGuardrails.level`, `supervision.*`,
      `toolCalling.maxOutputTokens`, `conversationBranchAdvisor.enabled` and flips
      `preferBridgeCompaction` to `true`. AGENTS.md treats the two pre-existing
      lmstudio keys as behaviour-bearing and repo-owned, so this file is not
      "just local". Either commit it with a one-line reason or `git checkout --`
      it. Leaving it dirty is the one state that makes every future diff
      ambiguous. *Blocks:* T3.
- [ ] **T3 — Reconcile the two stashes (F).** `git stash show -p` each; the
      2026-09-23 one predates the rescue and is probably dead, the
      CURRENT-STATE one may already be in `docs/CURRENT-STATE.md`. Per AGENTS.md,
      preserve anything unique in PrivateResearch with a hash, then drop. Target:
      zero stashes.
- [ ] **T4 — Confirm no other agent owns A's working tree** before any of T1–T3
      touch files. The #186 bulb work has no worktree here; verify with the
      operator rather than assuming, because T2 in particular rewrites a file.
- [ ] **T5 — Capture the live transcript B's commit message asserts.** B claims
      "Live: identity check and a 3-poll watch against the connected Polaris
      behave as designed", but **no such transcript exists anywhere** — the newest
      watcher log on this host is the 2026-10-09 file, and nothing under
      `docs/evidence/` is newer than `2026-10-09 23:00`. Offline GREEN proves the
      script's logic against scripted fakes only; it does not prove `iw`/`ip`
      parsing on this adapter. Re-run with `WATCH_MAX_POLLS=3` into a **new**
      path, store it as
      `docs/evidence/benro-connect-crash-20261008/raw/app-crash-watch-<ts>-linkstate-selftest.txt`
      with a SHA-256, and quote the `IDENTITY …` line. *Until this is done, B is
      offline-verified only and must not be described as live-tested.*
- [ ] **T6 — Fix the default output path before the next real run.** B still
      defaults `OUT` to `/tmp/app-crash-watch.log`, the exact path that currently
      holds a byte-identical copy of committed operator evidence (fact 4). A
      default run silently clobbers it. Change the default to a timestamped path
      (or refuse to overwrite an existing file) as part of T5's run.
- [ ] **T7 — Commit the `.60` premise correction where it can be acted on.** The
      correction currently lives only in `/tmp/187-fix.md` (fact 5). #187's body
      still names the `polestar_app` bulb patch as "the prime suspect", and every
      later plan step was shaped by that. Post the `c0c4797` / `0e6edd03` /
      `4be4a5f0` table as a comment on #187 and correct the body's step 1 to
      compare the `.60`→`.61` **libgphoto2** delta (`f3a8ffe` → `678d0dc`) plus
      the #183 stage2 change. This is the highest-value item in the list: it
      removes a false lead that is still steering the investigation.
- [ ] **T8 — Re-label the seven `?` events as host-side until proven otherwise.**
      The committed SUMMARY records that, for the 19:20:12Z event, the host was
      found *disassociated with the route to 192.168.0.1 via Ethernet* — i.e. a
      plausible host-side cause — and explicitly says it "does not prove whether
      the Polaris AP/service failed or only the host left the AP". The other six
      have no follow-up at all. So B's new `LINK_LOSS_HOST` attribution is the
      honest label, and equally: **none of the seven may be cited as evidence for
      #171/#68 driver exhaustion.** Add that sentence to the 20261008 SUMMARY so
      the next reader cannot re-inflate them.
- [ ] **T9 — Retire the dead branch C.** `origin/codex/pentax-capture-recovery`
      is an ancestor of `main`; its content is delivered. `git push origin
      :codex/pentax-capture-recovery` after confirming #188's closure state.
      Do **not** delete B this way — B is not merged.
- [ ] **T10 — Decide B's disposition (merge or hold), after T5.** Two defensible
      outcomes, both fine, one required:
      - *Merge* into `main` once T5's transcript exists — the change is
        diagnostics-only, gate-green, and strictly improves attribution.
      - *Hold* as a documented active exception if we do not want a watcher change
        in the same window as #186: then record owner, purpose, exact SHA
        `34ad4ba`, and the convergence action in the handover, per AGENTS.md.
      What is **not** acceptable is B sitting in `/tmp` (volatile) with an
      unpushed branch and no entry in `docs/CURRENT-STATE.md`.
- [ ] **T11 — Minor hardening to fold into B before merge, not separate work.**
      (a) the Polaris BSSID prefix `48:e7:da:*` is hardcoded in `host_link_ok`
      while the interface is env-overridable — make the prefix a variable with
      the same default, since AGENTS.md pins BSSIDs as data; (b) add one test that
      a *missing* `iw` binary yields `LINK_LOSS_HOST` with a reason rather than a
      silent OK, so a host without `iw` cannot masquerade as a healthy link.
- [ ] **T12 — One-line pointer in `docs/CURRENT-STATE.md`.** Whatever T10
      concludes, the entry point must state how many worktrees exist and what
      each is for. That pointer is what makes the next agent's first action
      correct instead of a surprise.

## 4. Standing rule proposed from this review

A worktree is created with a named owner, a purpose, and a retirement condition
written into the commit or handover at creation time. `/tmp` is not a storage
location for anything we intend to keep: B's evidence survives only because its
commit is in the object database.

## 5. Verification commands

```sh
# inventory
git worktree list --porcelain && git branch -avv && git stash list && git status -sb
# A vs origin (T1)
git merge-base --is-ancestor origin/main main && git rev-list --count origin/main..main
# C is delivered (T9)
git merge-base --is-ancestor origin/codex/pentax-capture-recovery main && echo MERGED
# B's claims (T5)
cd /tmp/bpp-187-linkstate && python3 -m pytest tests/test_watch_app_crash.py -q \
  && ./tests/run_prerelease_gate.sh
# the seven events (T8)
grep -c ' -> ?' docs/evidence/benro-connect-crash-20261008/raw/app-crash-watch-20261009-authorized-attempt.txt
# the .60 premise (T7)
git show 0e6edd03:scripts/build-release-candidate.sh | grep -c -- --polestar-bulb-patch
git show 4be4a5f0:scripts/build-release-candidate.sh | grep -c -- --polestar-bulb-patch
git show -s --format='%h %ad %s' --date=short c0c4797
```

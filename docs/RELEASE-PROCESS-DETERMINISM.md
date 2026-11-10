# Release process determinism: what actually cost time, and what fixes it

Written after cutting `astro-v102` and `astro-v103` on 2026-11-09/10. Every item below is
something that **actually happened** in those two builds, with the evidence that proves it.
This is not a general checklist; it is an inventory of this cycle's failures and what now
prevents each one.

## Why it took so long

Two full candidate builds plus three failed publish attempts. The build itself is ~15
minutes and is not the problem. What cost hours were defects that could only be discovered
*by running the thing*, and one class of defect — a check that looks green but tests
nothing — that recurs throughout.

The recurring shape, in every case: **a check reported success over nothing.** A gate that
nobody calls. A `[ -f ]` guard that silently skips. A `bash -n` pass on a file that then
fails at runtime. A "15 passed" recollection when the log says 16. A version bound to a
commit that was never built. Each of these is worse than an absent check, because it
produces a green result that gets trusted.

## The ten failures, and what now stops each

| # | What happened | How it was caught | Now prevented by |
|---|---|---|---|
| 1 | `flatpak-spawn --host docker` shim recursion: the host resolves `docker` on its own PATH, finds our shim, cannot exec `flatpak-spawn`, dies rc=127 reading exactly like "docker is not installed". Present in six call sites. `build-doctor.sh`'s own failure hint told the operator to *create* that file in `~/.local/bin` — the tool diagnosing the failure was recommending its cause. | Only by running it. | `tools/host-docker.sh` resolves an absolute host path that cannot be one of our shims. One absolute-path shim in `out/.build-env/bin`, first on the child's PATH, inherited by every script the wrapper invokes — including ones not yet audited. Verified by execution, not `bash -n`. |
| 2 | A comment line in `build-astro-candidate.sh` lost its `#` and executed as a command. | Only by running it. **`bash -n` passes it** — a bare word is valid syntax. | Nothing yet. This is the strongest argument for CI: syntax checking cannot find it. |
| 3 | Patched `scripts/build-astro.sh`, which nothing executes. The live one is the *root* `build-astro.sh`. Two files, same name. | Only by running it. | Nothing yet. Needs the duplicate deleted or one renamed. |
| 4 | `--next` returned `.101`, which v101 had already been built as and never recorded — the duplicate-version failure #169 exists to prevent, live in the registry. | `--next` output vs the registry. | `.101` recorded retroactively against its real pins. The gap that let it happen remains: **the Astro path has no version-claim step**; `--display-fwver` is an argument and nothing writes back. |
| 5 | A commit claimed the Astro path recorded `build_doctor_status`. It did not — the variable was assigned on every branch and then dropped. | Re-read the code after writing the claim. | Now written into provenance; v103's `build-source-provenance.txt` contains `build_doctor_status=green`. |
| 6 | Bound `.102` to patcher `4fcd020` — the commit I was standing on when `--record` ran. The candidate was built from `2b8731a`, stated in its own provenance and manifest. A binding naming a tree that was never built is worse than no binding, because it will be trusted. | Diffed the binding against the candidate's own provenance. | `.103` bound to `18218b3ea489` read **out of the candidate's `build-source-provenance.txt`**, not from HEAD. The tool still cannot correct a wrong binding: `bind_display_fwver` is append-only and `--record` refuses an already-claimed version. |
| 7 | First publish rejected **GH001**: `astro-bundle.tar.gz` was 110.50 MB, over GitHub's 100 MB hard limit. Not new content — `COPY-TO-SD-CARD-ROOT/` stored every kit twice, once extracted (what the manifest covers and the README says to drag onto the card) and once zipped. Zipping already-compressed data saves nothing. | The push itself. | Tar excludes `./COPY-TO-SD-CARD-ROOT/*.zip`; bundle is 63.8 MiB with all 721 extracted entries intact. All three SD archives publish as siblings beside `FwPkt.zip`. **`astrometry-indexes.zip` had never been published at all** — the loop listed only astro and wifi. |
| 8 | Second publish died on a 900 s timeout: the script clones PrivateResearch (~26 GB) into `${TMPDIR:-/tmp}`, which has 8.9 GB free. The clone could not finish inside the window, or fit. | `pgrep` + `du` on the temp clone. | Publish through a persistent clean checkout via `--checkout`. **Doctor section 8 now warns about this before the build starts.** |
| 9 | **The #292 archive-level release gate was not on this branch at all.** `verify-published-astro-candidate.py` exists only on `fix/archive-level-release-gate-292`; `git merge-base --is-ancestor 7baefa9 HEAD` returns false. So `.102` was built *and published* without ever running the check whose purpose is to verify the archives a user receives rather than the build directory. | Ran the gate by hand against the published bytes. It failed immediately. | Cherry-picked and wired into **both** producers, after every archive exists so it cannot pass vacuously, aborting via `die` rather than printing a verdict that gets discarded. v103's build log shows it running at step [2/7]: 21 checks, 0 fail. |
| 10 | **Eight shipped scripts were non-executable.** `aa_rehearsal.sh`, `autofocus.sh`, `inject_test.sh`, `polaris-astro-hook.sh`, `polaris-frame-watch.sh`, `polaris-goto-solve.sh`, `polaris-goto-watch.sh`, `polaris-pointing-model.sh` are committed to `container/astro/ondisk` at mode 100644 while carrying a shebang, and the build faithfully preserves that into `polaris-astro.zip`. On the device this is not cosmetic: `polaris-goto-solve.sh` is guarded by `[ ! -x ] && exit 2`, so the goto solver aborts outright; frame-watch, goto-watch and pointing-model are guarded by `[ -x ]` and **silently disable instead** — features that quietly stop working while everything reports success. | The recovered #292 gate, run manually. | `chmod +x` on all eight (verified in shipped bytes: `unzip -Z` reports 0 non-executable `.sh` across all 26 members). Plus **doctor section 7**, which asserts against git's recorded mode — not the working tree, so a locally chmod'd file cannot hide a commit that still ships 100644. Mutation-tested: removing a bit fails it, restoring passes it; covers 26 scripts so it is not vacuous. Runs in milliseconds instead of ~15 minutes into a build. |

Also caught before it wasted a build: I passed v102's change-summary file to a v103 build,
which would have produced a manifest describing the wrong release. Stopped it at step [1/7]
rather than discovering a mis-described artifact at the end.

## Is there a clean repo to start with?

Yes, verified rather than assumed:

| Repo | dirty | worktrees | branch | ahead of upstream |
|---|---|---|---|---|
| `~/polaris-v101` (patcher, release branch) | 0 | 1 | `feature/astro-native-platesolve` | 0 |
| `~/Documents/VSCodeProjects/LibGphoto2/libgphoto2` | 0 | 1 | `main` = `origin/main` | 0 |
| `~/pr-publish` (publication checkout) | 0 | 1 | `main` = `origin/main` | 0 |

Removed: 8 stale patcher worktrees (`polaris-build-73`, `polaris-bundle-20261107`,
`regfix`, `wt-b99`, `wt-wifi-dhcp`, `/tmp/wt282`, `polaris-v94`, `/tmp/mergetest`), 9
superseded libgphoto2 clones (`lgp-72`, `lgp-73-src`, `lgp-74-src`, `lgp-75-src`,
`lgp-76-src`, `lgp-main-71`, `lgp-main-99`, `lgp-v97`, `lgp-v99-src`), libgphoto2's stale
`build/`, `_build/`, `build-asan/` and 5 untracked build stamps, and a redundant branch
whose tree was byte-identical to `main`.

**Nothing unique was destroyed.** Before removal every worktree was classified by whether
its commit was reachable from origin and whether it held uncommitted tracked changes. Two
held genuinely unique work: `/tmp/mergetest` (an unresolved merge conflict plus issue-297
evidence, on a commit reachable from **zero** remote branches) and `polaris-v94` (8053 lines
of staged edits). Both are preserved in `~/worktree-backups/` as tracked-file patches **and**
`git bundle` archives of their HEAD commits, with `git bundle verify` run from inside a repo
to confirm they are restorable.

One orphaned file was found this way and is now recovered rather than deleted:
`test_both_producers_invoke_the_gate`, an untracked test in `polaris-bundle-20261107` that
existed nowhere in git. It asserts both build producers call the #292 gate — exactly the gap
that let `.102` ship broken. Merged into the recovered test file; 17 tests pass.

## Not clean, and why

- **`~/polaris-build-71`, `-72`, `-73` (~9.2 GB)** contain root-owned files from container
  builds (880, 881 and 8738 entries). Their git registrations are gone; the directories
  cannot be deleted without `sudo`. Needs: `sudo rm -rf ~/polaris-build-7{1,2,3}`.
- **`~/Documents/VSCodeProjects/BenroPolarisPatcher`** is on `archive/wip-20261103-v94-audit`
  with untracked K-1 III connect-failure evidence and an older copy of
  `scripts/resolve-release-inputs.sh`. The release branch has the newer tracked version, so
  nothing unique is at risk; the evidence directory is not duplicated anywhere else and was
  left alone rather than committed into an archive branch.
- **`~/Documents/VSCodeProjects/PrivateResearch`** has 154 untracked files and 2 modified.
  Publishing never touches it — `publish-astro-candidate.sh` deliberately refuses a dirty
  checkout, which is correct design. Left as-is.
- **`~/.local/bin/ubireader_extract_files` is broken** (exit 1, wrong-interpreter traceback).
  The doctor reports it RED. `build-astro.sh` routes around it via `tools/ubireader-docker`,
  so builds succeed; the standalone doctor will keep reporting RED until it is repaired or
  removed.

## What would make this genuinely foolproof

Ordered by how much of this session's lost time each would have saved.

1. **CI that runs the build, not just the tests.** Three defects were invisible to every
   static check available: the missing `#` (valid syntax), the wrong-file edit (`scripts/`
   vs root), and the exec-bit bug (correct content, wrong mode). All three are only visible
   by executing. A CI job that builds a candidate and runs
   `verify-published-astro-candidate.py` over the result would have caught #2, #3 and #10
   without anyone remembering to. There is currently no CI at all.
2. **Merge `fix/archive-level-release-gate-292` into the release branch.** It is not an
   ancestor of it today. Until that happens the gate exists on one branch and the release
   path runs a different one — which is precisely how `.102` shipped broken. The recovered
   tests are now on this branch, but the upstream merge still needs doing so the two do not
   diverge again.
3. **A version-claim step inside `build-astro-candidate.sh`.** The Astro path takes
   `--display-fwver` as an argument and writes nothing back to the registry. That is how
   `.97`, `.98` and `.101` went unrecorded, and how `--next` handed back a version already
   consumed. Claiming should be part of the build, not a separate step someone remembers.
4. **Make `--record` read the candidate's provenance** instead of accepting
   `--patcher-commit` from whatever HEAD is checked out. The `.102` mis-binding was exactly
   this, and the tool cannot correct it afterwards because bindings are append-only.
5. **Delete or rename one of the two `build-astro.sh` files.** Two files with the same name,
   one of which nothing executes, is a trap that will be fallen into again.
6. **Publish by default through a persistent clean checkout.** The 26 GB clone into `/tmp`
   is both slow and space-limited; doctor section 8 now warns, but the script's default is
   still the path that fails here.
7. **A pre-push size guard** for PrivateResearch. GH001 is knowable locally: any staged blob
   over 100 MB should fail before the push, not after a 26 GB transfer.

## Standing rule this cycle established

Publishing to `ian-morgan99/PrivateResearch` happens in the same session as the build,
without asking — `AGENTS.md` has said so all along under `fwpkt-private-upload`. Asking
whether to publish is not a clarification, it is a failure to read the documented process.

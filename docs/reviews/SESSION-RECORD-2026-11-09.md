# Autonomous session record — 2026-11-09

Worked unattended. Every claim below was checked against a command's output; where I got
something wrong mid-session it is recorded as corrected rather than quietly dropped, because
that has been the recurring failure mode this week.

## Shipped (pushed)

| commit | what |
|---|---|
| `4ea2d72` | gate: removed stray bare commands `s`/`ped`, added `tests/test_shell_no_bare_fragments.sh` |
| `f476c5c` | review: `docs/reviews/polaris-v94-staged-deletions.md` |
| `81f8a6c` | diagnostic(#297): fixed the layer-4 client filter; session-trigger evidence |
| `8dc8098` (PR **#301**) | gate: registered `test_astro_regression.py`, restoring main to GREEN |

## 1. PR #298 review defect — fixed and proven

The TA found bare `s` and `ped` at lines 363/365 of `tests/run_prerelease_gate.sh`. Real,
mine, caused by pasting text already hard-wrapped at terminal width: the wrapped remainder of
"as" and "shipped" landed outside the comment as executable code.

Why nothing caught it: the gate runs `set -uo pipefail` **without `-e`**, so a missing command
returns 127 and execution continues. It passed `bash -n` (two valid commands), passed `--help`,
and printed a green summary. The TA's point that `bash -n`/`--help` are insufficient is
structural, not incidental.

Byte-level proof at the pushed head: `grep -c '^s$'` → 0, `grep -c '^ped$'` → 0.

Added a lint covering **every tracked `.sh`**, since any script can absorb a wrapped paste this
way. It treats a bare short line as legitimate only if it is a shell keyword/builtin or a
function defined in that same file — `purge` is called bare at line 65 of `polaris-autojoin.sh`
and defined at line 36, so a naive keyword list would have flagged a real call. Tracked files
only: `out/` holds copies and would double every finding. Non-vacuous — reintroducing the
fragments exits 1; current tree (117 files) exits 0.

Gate from corrected head: offline **15 passed / 0 failed / 2 skipped**; with `--build`
**22 passed / 0 failed / 3 skipped**. Transcripts committed under `docs/evidence/`.

## 2. Main was RED since #299 merged — fixed in PR #301

`tests/test_astro_regression.py` arrived with #299 but was never added to `PY_TESTS`, so the
drift guard failed main. Reproduced on a clean worktree at **exit 1**:

```
FAIL: python suites exist but are not run by this gate: tests/test_astro_regression.py
GATE: RED — do not stage/install the FwPkt until the failed checks pass.
```

One line added; now **38 suites, 615 passed** (was 612), so the three new tests actually run.
Suite is offline-safe: runs `astro_regression/runner.py --offline`, asserts on checked-in
fixtures, no socket, no device, 0.05 s.

I initially saw a *second* failure there — `test_plate_solving_present.py::
test_build_toolchain_prerequisites` — and it was **my artifact**: I had made the worktree under
`/tmp`, and `docker_available()` probes `flatpak-spawn --host docker info` with `cwd=ROOT`,
which fails outside `$HOME`. Recreated under `$HOME`; passes. Only the drift-guard failure is
real. Worth knowing because it would have been easy to report a phantom regression.

## 3. #297 — "nothing asked yet" is refuted; layer 3 is a real fault

Ran the TA's step 1: `GET :8080/?action=stream`, the exact request `polaris-httpd` makes
itself. pgphoto accepted and answered **HTTP 200, 22 bytes** — the MJPEG boundary
`--boundarydonotcross\r\n` — then produced no frame. While that connection was established:

```
established_to_8080=1
[FAIL] layer3-camlib -- a client is connected but no pentax.so/ptp2.so is mapped
usb_fds=0
```

Something asked, pgphoto took it, `gp_camera_init` still never loaded a camlib.

Ruled out with evidence: libgphoto2 + libgphoto2_port + **libltdl** all mapped; CAMLIBS/IOLIBS
correct on the live process and that dir holds `pentax.so`, `ptp2.so`, `camlibs.manifest`; both
camlibs export `camera_id` and `camera_abilities`; pgphoto runs uid 0 so the `drwxr-x---
1000:1000` ownership is not a blocker; no `CAMLIBDIR_PREFIX_ENV`, so `foreach_func`'s skip
filter is inactive.

**Bug found in my own diagnostic.** Layer 4 matched `:1F90` only in `/proc/net/tcp`'s remote
column, but pgphoto is the *server*, so established rows carry it in the local column. Against
a live stream request with two connections: `$3 ~ /:1F90$/` → 0, `($2 || $3)` → 2. Worse than a
wrong count — layer 3 defers its verdict on layer 4 (UNKNOWN while idle, FAIL once a client is
connected), so under-reporting pinned layer 3 at UNKNOWN permanently and hid the real state.

## 4. Hypotheses I raised and then refuted myself

Recorded because each looked convincing at the time:

- **`camlibs.manifest` format.** Ours contains SHA-256 lines (`build_ptp2.sh:375`) and I
  suspected it clobbered libgphoto2's manifest-of-names. Wrong: `gphoto2-abilities-list.c`
  never reads that file — it enumerates with `lt_dlforeachfile`.
- **`/tmp/gphoto-debug.log` as evidence.** It is gphoto2 CLI **2.5.27.1** with `CAMLIBS` lacking
  the version subdir, not pgphoto's **2.5.34**, and no `gphoto2` is on PATH now. Its
  `Failed to load '/app/lib/stage2/libgphoto2/2': file not found` line looks like a smoking gun
  and is fully explained by that wrong CAMLIBS:

  ```
  foreach_func: Found '/app/lib/stage2/libgphoto2/2'.
  unlocked_gp_abilities_list_load_dir: Found 1 camera drivers.
  ```

  With CAMLIBS pointing at the parent, `lt_dlforeachfile` enumerated the version **directory**
  `2.5.34` and ltdl treated `.5.34` as an extension, so it came back as `2`; the subsequent
  `lt_dlopenext("…/2")` then failed. One bogus "driver" that is really a directory. Our live
  process has the correct versioned CAMLIBS, so this path never applies to it.
- **Loader capture-guard refusing init.** `STAGE2_CAPTURE_GUARD` is *not* set in the process
  env, and `stage2_capture_guard_enabled()` requires it, so the guard is off.
- **"Loader printed nothing, therefore init didn't run."** Would have been wrong: Clog.txt is
  106 lines for a 171-minute process emitting IPC chatter every ~3 s, so it is continuously
  truncated. Absence of the `[stage2] init:` banner proves nothing.

Still open on #297: why `gp_camera_init` never dlopens a camlib despite all of the above being
correct. Needs `GP_DEBUG` from **pgphoto's own** libgphoto2, not the CLI. No strace/ltrace/gdb
on the device.

## 5. #285 — corrected a contradicted claim, and one I made in error

The body asserted the exit-139 crash "explains ALL the previously observed failures". The
archive contradicts that: `camera_connected_to_app connected:1` appears **459** times across 22
files, `set_config` in 36 bundles. A session reaching `connected:1` 459 times cannot have been
blocked by a crash-before-config-write. Body corrected; #275–#279 stay open individually.

Two errors of my own during that work, both fixed publicly rather than edited away:

- I wrote that the "Can't verify — pgphoto crashes before any config write" wording "has been
  corrected on each issue". It hadn't — that wording only ever existed in #285's body; #275–#279
  never carried it.
- In my #298 reply I wrote "my earlier 'fixed' reply was wrong". There was no such reply; I
  asserted it from memory without checking the thread.

**Symbolisation trap.** Resolving the crash LR `libgphoto2.so.6+0xeb34` against
`out/astro-v99-candidate/stage2-ondisk/libgphoto2.so.6` returns **`gp_camera_set_config`** —
confident and wrong. `.dynsym` lists only exports, and the nearest preceding exported function
spans `0xe8e0–0xef3c`, so a naive "contains the address" lookup hits it. `gp_context_progress_start`
is at `0x17fbc` in that build. **Symbolising a crash offset against a different build's binary is
invalid and fails silently** — you get a real function name, not an error. The dump records no
build-id to match against.

Also: the o-v16b bundle *does* carry a full handler dump (432 maps lines, PC/LR on every block),
resolving to one LR for all three crashes. My earlier "no bundle carries it" was wrong for
o-v16b specifically; correct for `pentax-shutter-crash-20260930-1443` (4 SIGSEGV blocks, no maps,
no LR).

## 6. polaris-v94 staged deletions — reviewed, nothing changed there

Read-only review of 32 deletions / 20 modifications. Mechanically clean and verified: `bash -n`
passes, no deleted file is referenced by the staged gate, `SKILL.md` updated consistently, only
dangling reference is a historical mention inside an evidence SUMMARY, drift guard self-consistent
(33 listed / 33 in index).

One thing not shippable without a decision: **`tests/test_setup_wifi_psk_not_in_argv.py` is the
only behavioural guard for #290 and nothing replaces it.** In the staged tree, grepping `tests/`
and `container/**test*` for `wpa_passphrase|psk|argv` returns nothing, and `setup-wifi.sh` appears
in the gate zero times. The fix itself survives (passphrase on stdin, `#psk=` stripped) — only the
guard against regressing it is gone. Its own docstring says #290 survived because a comment
asserted argv-free handling and reviewers read it; the test asserts on what the child process
received instead.

No rationale recorded anywhere: no added line in CHANGELOG or RELEASE-VERSION-STATE mentions
removal. Staged but uncommitted — one careless `git commit -a` from permanent with no review step.

## Not done / not claimed

- Device install-hash checks and the physical Benro Connect / Manual / Bulb regression have not
  run. Offline GREEN is not device-qualified.
- The 20 modified files in polaris-v94 were not reviewed line by line.
- #297 root cause still unknown; I did not guess it.
- Nothing was merged, closed, or deployed.

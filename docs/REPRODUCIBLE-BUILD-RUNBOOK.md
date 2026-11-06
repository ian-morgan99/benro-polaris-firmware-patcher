# Reproducible Polaris candidate build

This is the canonical procedure for producing a Benro Polaris firmware
candidate from the current patcher `main` and Pentax/libgphoto2 `main`. It
produces a candidate package and evidence; it does not by itself prove camera
operation or authorise installation.

## Required inputs

- a clean patcher checkout on `main`;
- a clean `ian-morgan99/libgphoto2` checkout on `main`;
- the exact stock Benro `FwPkt` folder or `FwPkt.zip`, retained unchanged;
- Docker, Python 3, Meson, and normal build dependencies;
- a unique candidate ID and an unused display firmware version.

Do not build from a dirty worktree, detached checkout, feature branch, stale
build directory, or appliance/runtime checkout. Do not use dirty-source or
dirty-patcher escape hatches for a release candidate.

The release builder enforces the repository identities as well as cleanliness:
the patcher must be on `main` with the `ian-morgan99/benro-polaris-firmware-patcher`
origin, and the libgphoto2 input must be on `main` with the
`ian-morgan99/libgphoto2` origin. It also rejects stock inputs without
`FwPkt/firmwareInfo`. A failure before Docker starts is intentional.

## Prepare the source checkouts

```sh
git clone https://github.com/ian-morgan99/benro-polaris-firmware-patcher.git patcher-build
git clone https://github.com/ian-morgan99/libgphoto2.git libgphoto2-build

cd patcher-build
git switch main
git pull --ff-only origin main
git status --porcelain

cd ../libgphoto2-build
git switch main
git pull --ff-only origin main
git status --porcelain
```

Both `git status --porcelain` commands must produce no output. The libgphoto2
checkout must not contain `build/`, `_build/`, or `build-asan/`; these are
ignored by Git but can be copied into Docker and reuse stale objects.

Record the source identities before building:

```sh
git -C patcher-build rev-parse HEAD
git -C libgphoto2-build rev-parse HEAD
sha256sum /absolute/path/to/stock/FwPkt.zip
```

## Build the next candidate

First prepare and commit a candidate-specific change summary using
`docs/templates/release-change-summary.json`. Replace every placeholder with
the previous published candidate's exact source SHAs, the intended fixes, and
the remaining qualification limits. The template itself is not a valid release
summary. Do not declare #251 fixed until its remaining acceptance gates pass.

For the normal user workflow, use the wrapper from the clean patcher `main`
worktree. On this workstation that is currently `/home/ian/polaris-build-73`;
the separate `BenroPolarisPatcher` checkout has Astro work and is not the
release source. Verify the branch and status each time.

```sh
CHANGE_SUMMARY=docs/release-summaries/your-reviewed-candidate.json \
./scripts/release/build-and-install.sh
```

It automatically resolves host Docker when launched from the VS Code sandbox,
clones a disposable clean libgphoto2 `main`, runs the complete build, and
prints the verified deployment command. To build and then deploy in one run:

```sh
CHANGE_SUMMARY=docs/release-summaries/your-reviewed-candidate.json \
./scripts/release/build-and-install.sh --install
```

The desktop icons call this same wrapper. They cannot supply a reviewed change
summary themselves: without `CHANGE_SUMMARY`, the wrapper stops before cloning
or building and records the reason in its log. Use the command above for a
reviewed release. The wrapper delegates display-version and build-ID selection
to the canonical builder using `auto`; it must never default to `.77` or any
other previously used version.

Deployment still stops at the normal preflight, install-manifest, identity, and
reboot gates. Hardware qualification remains separate.

For this workstation, the retained stock base is in PrivateResearch at:

```sh
STOCK_FWPKT=/home/ian/Documents/VSCodeProjects/PrivateResearch/openpolaris-research/BenroPolarisPatcher/firmware/FwPkt
LIBGPHOTO2=/home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main
```

That directory contains the nested `FwPkt/firmwareInfo` package and its
adjacent `SOURCE.md` record. It is the stock base input, not a previously
patched candidate from `PrivateResearch/firmware-packets/`. Do not substitute
the `.74`, `.75`, or `.76` candidate ZIPs as the source base for a new release.
Verify the input before building:

```sh
test -f "$STOCK_FWPKT/FwPkt/firmwareInfo"
git -C "$LIBGPHOTO2" branch --show-current  # must print main
git -C "$LIBGPHOTO2" status --porcelain
sha256sum "$STOCK_FWPKT/FwPkt/firmwareInfo"
```

From the patcher checkout:

```sh
./scripts/build-release-candidate.sh \
  o-main-your-unique-candidate \
  "$STOCK_FWPKT" \
  "$LIBGPHOTO2" \
  auto \
  auto \
  --change-summary docs/release-summaries/your-reviewed-candidate.json
```

The two `auto` values derive a valid unused display version and matching
build ID. `LibGphoto2-v86-main` is a historical folder name, not the source
version: the recorded commit is authoritative. The adjacent
`LibGphoto2/libgphoto2` worktree is currently a feature branch and is rejected
as a release input. The wrapper avoids that ambiguity by cloning remote `main`.

The script performs, in order:

1. source cleanliness, branch, and stale-build checks;
2. libgphoto2 deterministic regression tests;
3. the full `patch-polaris.sh` build using the mounted local libgphoto2 source;
4. package/display-version regression checks;
5. install-manifest generation;
6. the source-aware pre-release gate;
7. shipped-artifact differential checking;
8. version-to-commit binding and private artifact publication.

The authoritative output is `out/<candidate-id>/`. Retain its ZIP MD5/SHA-256,
`install-manifest.json`, `build-source-provenance.txt`, `gate-transcript.txt`,
exact source SHAs, stock FwPkt hash, and every recorded skip.

The build updates `docs/RELEASE-VERSION-STATE.md`. Review that diff, commit it
with the release documentation, and push it before treating provenance as
complete. A failed build or an output directory is not a release claim.

Do not substitute `patch-polaris.sh` for this command when producing a release
candidate. That lower-level command remains available for diagnostics and
development experiments, but it does not perform the complete source, test,
version, differential, or publication workflow.

## Astro plate-solving candidates

`scripts/release/build-and-install.sh` above builds the standard camera
candidate. It does not build an Astro candidate: it has no `--catalog-package`,
no focal range and no Astro bundle step. Astro candidates are built by
`scripts/build-astro.sh`.

```sh
scripts/build-astro.sh --version 98 \
  --summary docs/release-change-summary-v98-astro.json
```

One command, no arguments to remember. It derives the candidate id and display
version from `--version`, provisions what it can inside the repository, runs the
doctor, and verifies the artifacts afterwards. Nothing it does touches `$HOME`,
installs software, or contacts a camera.

If `--summary` is omitted it writes a template with obvious `REPLACE` markers and
stops. It never invents a change summary: that file is the release's honest
statement of what changed and what is not fixed, so it must be written by a
person.

Useful flags: `--pin` to override the driver commit (defaults to the canonical
libgphoto2 `origin/main`), `--slug` for the name in the candidate id, `--dry-run`
to provision and print the builder invocation without building, and
`--skip-doctor` if you have read a red doctor and disagree with it.

### Run the doctor first

```sh
scripts/build-doctor.sh
```

It takes seconds and exits non-zero if anything is broken. Its rule is that a
prerequisite must be **proven to work**, never merely seen to exist. Every one of
the six failures below passed an existence check and then failed anyway.

The most important check is the bind-mount probe: it writes a sentinel into a
`mktemp -d` directory, mounts it into a container through the same image the
build uses, and reads it back. A daemon that answers `docker info` perfectly can
still mount nothing at all.

### Failure modes: what the message says, and what it means

Building astro-v97 on 2026-11-06 failed six times. None of the six was a defect
in build logic; each was an environment prerequisite that looked satisfied and
was not. Every row below is a message that sent me looking at the wrong thing.

| Message you see | Real cause | Fix |
| --- | --- | --- |
| `docker not found. Install Docker Desktop / docker.` | Docker is installed. The shell is inside a Flatpak sandbox that does not expose `/var/run/docker.sock`, so `docker` is absent from PATH. | `flatpak override --user --filesystem=/var/run/docker.sock $FLATPAK_ID`, then fully quit and relaunch. `build-astro.sh` writes a `flatpak-spawn` shim automatically. |
| `[abort] /in/firmwareInfo not found -- mount your stock FwPkt at /in` | The stock packet is fine. `patch-polaris.sh` unpacks it with `mktemp -d`, which honours `TMPDIR`. Inside a sandbox `/tmp` is private to the sandbox while the daemon runs on the host, so the bind mount comes up **empty**. | `export TMPDIR=$HOME/.cache/polaris-build-tmp`. `build-astro.sh` sets this itself. |
| `[build] ERROR: local source directory must be a Git checkout` | The tree *is* git -- a linked **worktree**. Its `.git` is a one-line file pointing at `$MAIN/.git/worktrees/<name>`, and only `$LIBSRC` is mounted, so git inside the container cannot resolve the pointer. | Use a self-contained clone: `git clone --no-checkout --local <repo> <dir> && git -C <dir> checkout --detach <pin>`. |
| `baseline <sha> is not reachable from origin/main -- orphan or unmerged commit?` | The commit *is* on origin/main. A local clone copied a **stale** `refs/remotes/origin/main`, so the ancestor test ran against the wrong tip. | `git -C <src> fetch <repo> 'refs/remotes/origin/*:refs/remotes/origin/*'` and retry. |
| `could not extract appfs.ubifs (no functional ubireader)` | A wrapper existed and was executable but died at import -- its module was installed for a different interpreter. Existence proved nothing. | `export UBIREADER_EXTRACT_FILES=<repo>/tools/ubireader-docker`, which runs the patcher image's working ubireader against host paths. |
| `VERDICT=BROKEN ... missing=bwrap,slirp4netns` | Both are installed, under `~/.local/bin`, which a non-login shell does not have on PATH. The message says "install them". | `export PATH=$HOME/.local/bin:$PATH`. `build-astro.sh` appends it for the child process. |

Two rules follow from this table.

1. **Never trust an existence check.** `command -v`, `-x` and `-f` all passed on
   every one of these. Ask the thing to actually do its job.
2. **A message that names file X is not evidence that X is at fault.** Five of the
   six named the input file, the git tree or a missing package, and in every case
   the fault was elsewhere -- the mount, the ref, the interpreter or PATH.

The messages themselves now carry the diagnosis: `patch-polaris.sh` probes the
mount before the long build, `build_ptp2.sh` distinguishes a worktree from a
non-git tree and prints the `.gitfile` pointer, the manifest script names each
rejected ubireader candidate with its error, and the reachability check separates
a stale ref from a genuinely orphaned commit.

### Why the pin gates matter

`build-astro.sh` refuses to build unless the requested pin is a superset of the
v94 pin `43dccb81b` and contains `4fba11d81` (deferred Bulb cancellation, #251).
v95 was built from an ad-hoc tree with a hand-typed pin pointing at the tip of a
feature branch that had never taken nine commits main gained afterwards, four of
them shipped code. It went out without the guard it was meant to carry. The gate
is in the wrapper so it cannot be skipped by forgetting a flag.

### After a successful build

The wrapper prints `BUILD SUCCEEDED` only when both `FwPkt.zip` and
`astro-candidate-manifest.json` are non-empty. Exit code alone is not evidence:
a run can write `FwPkt.zip` at step [2/7] and fail at the [5/7] shared-camera
gate, which is what happened on 2026-11-06. A partial `FwPkt.zip` with no
manifest is never publishable.

It also refuses to delete a completed candidate -- keyed on the manifest, not the
zip -- because the builder's `--force` does `rm -rf` on the output directory.

Register the printed hashes in `docs/FWPKT-PROVENANCE-CONTRACT.md`, then qualify
on hardware. The wrapper never installs anything.

## Install only after build acceptance

If the rig may be asleep, establish the target and wake state first:

```sh
./scripts/polaris-preflight.sh --wake --wait 120 --scan 20
```

This is the only supported wake procedure. It verifies a held Bluetooth link
when possible, routes host tools correctly from a sandbox, and treats an empty
BLE scan as inconclusive. If the AP is already visible and identity/SSH checks
pass, Bluetooth wake is not required. If Bluetooth is unavailable, record that
as a host limitation rather than inferring a firmware or rig fault.

```sh
./scripts/release/release-fwpkt.sh out/<candidate-id>
```

This is the only supported installer. It stages the extracted `FwPkt/` tree to
`/app/sd/FwPkt/`, verifies device-side `firmwareInfo` hashes, proves a real
reboot through uptime reset, and verifies post-boot build identity and file
hashes.

Do not stage only `FwPkt.zip`; the watcher consumes the extracted tree, not the
ZIP. Do not copy files directly into `/app` for a release or qualification
claim. Keep the original stock FwPkt for rollback.

## Hardware qualification and handoff

After installation the candidate is only `installed-verified` until the
model-specific physical matrix passes. Record model, firmware, USB identity,
candidate identity, commands, files, lifecycle, recovery, and limitations in a
dated evidence directory and `docs/CURRENT-STATE.md`.

An installed package, green offline gate, successful reboot, or version string
is not camera qualification. If no camera is attached, state
`installed-verified; hardware qualification pending`.

## Failure rules

- Missing local libgphoto2 source: stop; never silently build vanilla source.
- Dirty or detached release source: stop; do not use an escape hatch.
- Any failed gate: stop and preserve the transcript.
- Any skip: record it as a prerequisite gap, not a pass.
- Any source, package, install, or runtime mismatch: quarantine the candidate.
- A prerequisite that merely *exists* is not satisfied. Prove it works: run
  `scripts/build-doctor.sh`, which exercises each one instead of looking for it.
- Never act on the file named in a build error until the cause is confirmed. Five
  of the six v97 failures named the wrong thing; see the failure-mode table above.
- A `FwPkt.zip` with no `astro-candidate-manifest.json` is a partial from a run
  that failed a later gate. It is never publishable and must not be installed.

## Related authoritative documents

- `docs/FWPKT-PROVENANCE-CONTRACT.md`
- `docs/FIRMWARE-SOURCE-VERIFICATION-AND-OFFSET-LEDGER.md`
- `docs/FIRMWARE-INSTALL-PROCESS.md`
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`
- `docs/RELEASE-VERSION-STATE.md`

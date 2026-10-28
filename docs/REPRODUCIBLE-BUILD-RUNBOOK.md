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

## Build a `.77` candidate

From the patcher checkout:

```sh
./scripts/build-release-candidate.sh \
  o-v18g-reproducible-20261028 \
  /absolute/path/to/stock/FwPkt.zip \
  /absolute/path/to/libgphoto2-build \
  auto \
  auto
```

The final `auto` values derive a valid unused display version and matching
build ID. If `.77` is specifically required, first verify it is not already
consumed in `docs/RELEASE-VERSION-STATE.md`, then pass the exact display version
only after the candidate identity has been agreed.

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

## Install only after build acceptance

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

## Related authoritative documents

- `docs/FWPKT-PROVENANCE-CONTRACT.md`
- `docs/FIRMWARE-SOURCE-VERIFICATION-AND-OFFSET-LEDGER.md`
- `docs/FIRMWARE-INSTALL-PROCESS.md`
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`
- `docs/RELEASE-VERSION-STATE.md`

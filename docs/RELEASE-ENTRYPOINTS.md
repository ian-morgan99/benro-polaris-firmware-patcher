# Release entrypoints — every operation, one command

**Status:** active, binding. If an operation is not in this table, **do not improvise
it** — add it here first, with the script that performs it.

This file exists because six months of release engineering accumulated as prose in
a dozen documents plus tribal knowledge of which of several same-named scripts is
the live one. That produced hand-rolled steps that silently skipped verification:
staging a kit with `scp` (which cannot work here at all), copying `polaris-astro/`
only and leaving `polaris-wifi/` stale, and flashing without re-installing the astro
kit so the device came back with the right version and port 8090 closed.

Rules that apply to every row:

- **Never hand-stage anything to the device.** Every transfer goes through the
  script in this table. `scp` does not work against this device: its sshd has no
  `sftp-server` subsystem, so `scp` dies with `scp: Connection closed` and legacy
  `scp -O` hangs. Scripts stream one tar archive over a single ssh session.
- **Never conclude success from an exit code or a version screen.** Each script
  below verifies installed state on the device and fails closed.
- **Read the receipt.** `out/<candidate>/install-receipt.txt` is the evidence.

## The release path

| Operation | Command | Verifies |
| --- | --- | --- |
| Prove the build host works before spending a build | `./scripts/build-doctor.sh` | Docker reachability and bind mounts, ubireader actually running, libgphoto2 pin reachable from origin, stock packet + catalogue present, gate prerequisites, patcher tree clean, exec bits, installer invariants, kit footprint, publication space |
| Build an Astro candidate (the normal path) | `./scripts/build-astro.sh --version N --slug NAME --summary docs/release-change-summary-vN-astro.json` | Runs the doctor first, provisions a private bin dir + host-visible TMPDIR + self-contained libgphoto2 clone at the pin, then verifies the artifacts, not just the exit code |
| Build a camera-only candidate | `./scripts/release/build-and-install.sh --install` with `CANDIDATE_ID` and `CHANGE_SUMMARY` set | Same builder path, optional verified deploy |
| Check release gates before publishing | `python3 scripts/release/check-release-gates.py --fwver V --patcher-commit SHA --libgphoto2-commit SHA --packet-dir DIR` | Version registry, exact source commits, packet contents; fails closed |
| Publish a candidate to PrivateResearch | `./scripts/publish-astro-candidate.sh --build out/<candidate>` | Publication archives, not the staging directory |
| Verify what a user would actually receive | `python3 scripts/verify-published-astro-candidate.py <archive>` | The shipped archives byte-for-byte against the candidate manifest |

## Installing on a device

| Operation | Command | Verifies |
| --- | --- | --- |
| **Flash firmware** (the only supported path) | `./scripts/release/release-fwpkt.sh out/<candidate>` | Six phases: gate (zip digest vs `install-manifest.json`, device identity, idle camera), stage the extracted `FwPkt/` tree, on-device MD5s vs `firmwareInfo`, reboot, `/proc/uptime` must have RESET, then exact `build_id` + both source commits + every mandatory file's SHA-256. **Phase 7 installs the astro kit** |
| Install/re-install the astro kit alone | `./scripts/release/install-astro-kit.sh out/<candidate> --no-indexes --reboot` | Stages via tar over ssh, verifies every staged byte against `ASTRO-MANIFEST.sha256`, runs `install_astro.sh`, requires the boot hook, `/app/astro/polaris-httpd`, and port 8090 actually serving |
| Confirm what is running right now | `./scripts/verify-installed-build.sh out/<candidate>` | `build_id`, both source commits, display version, mandatory installed file hashes |

**A flash deletes the astro kit.** Flashing replaces the whole `appfs` volume and
`/app/astro` lives on it, so every flash removes the plate solver *and* the boot hook
that starts it. `release-fwpkt.sh` does this as phase 7 by default; `--no-kit` exists
only for deliberate camera-only work and prints a warning naming the command to fix
it. See [FIRMWARE-INSTALL-PROCESS.md](FIRMWARE-INSTALL-PROCESS.md).

## Two files named `build-astro.sh`

This has cost time repeatedly. They are different scripts:

| Path | What it is |
| --- | --- |
| `scripts/build-astro.sh` | **The one to run.** One-command candidate build: doctor, provisioning, builder, artifact verification. |
| `build-astro.sh` (repo root) | Internal bundle builder invoked by `scripts/build-astro-candidate.sh` and `scripts/build-astro-bundle.sh`. Generates the shipped `astro-bundle/README.txt`. Not an entrypoint — do not run it directly. |

## What is deliberately not here

No operation in this project is performed by ad-hoc `ssh`, `scp`, `tar`, `dd`, or
`cp` against a device. If you find yourself typing one, the script is missing — write
it, add the row above, and add a test in `tests/test_release_entrypoints.py`.

`tests/test_release_entrypoints.py` asserts every command in this file exists and is
executable, and that every script in `scripts/release/` appears here. A new release
script that is not indexed fails the gate.

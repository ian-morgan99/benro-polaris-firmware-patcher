# Firmware install process — the one supported path

**Status:** active, binding for every agent and every release.
**Canonical installer:** `scripts/release/release-fwpkt.sh`
**Rule:** a candidate is installed by staging the extracted `FwPkt/` tree to
`/app/sd/FwPkt/` and rebooting. Nothing else. No direct copies into `/app`.

## Why this document exists

After ~72 releases, install was still tribal knowledge rather than a scripted,
deterministic step. Three scripts existed, only one of them correct, nothing in
the release pipeline referenced it, and there was no document saying which to use.
That produced real failures, all recorded below. This file plus the wiring in
`scripts/build-release-candidate.sh` is the fix: every build now prints the exact
install command for the candidate it just produced.

## Two routes: systematic and manual

There are two ways anything reaches a Polaris, and conflating them has caused real
failures. They differ in who can perform them, what they cover, and what proof they
produce. Pick by audience, not by convenience.

| | **Systematic** (agent / developer) | **Manual** (end user) |
|---|---|---|
| Who | Us, with a PC, SSH and this repo | Anyone, with the card plus one ssh command |
| Needs | Host tooling, SSH to the device, `git` checkout | The card, the camera, and one `ssh` command to run `install_astro.sh` |
| Firmware (`FwPkt`) | `scripts/release/release-fwpkt.sh` | Copy/extract `FwPkt/` to SD root, reboot |
| Astro + Wi-Fi kits | `scp`/rsync into `/app/sd/…`, or re-flash | Copy the zip to SD root, unzip there |
| Proof produced | MD5s on-device, uptime reset, `build_id`, both source commits, mandatory file SHA-256s | Version screen only — **no proof of a flash** |
| Failure mode | Fails closed at six phases | Silent: installs nothing and looks fine (#58) |

**The systematic route is the only supported one for firmware.** Everything below
this section describes it. The manual route is documented because users must have one
and because we keep writing instructions that assume SSH they do not have — but it
carries no verification, so a manual install is never evidence of an installed build.

### Why "copy the zip and reboot" is not enough for FwPkt

The on-boot watcher runs `SP_UpgradeCheckFw` against the **extracted tree** at
`/app/sd/FwPkt/`. A bare `FwPkt.zip` sitting there is ignored. This is issue #58 and
it has bitten repeatedly:

> `.67` first attempt staged `FwPkt.zip` and rebooted; the device came back on
> `.66` with the zip untouched and `--verify-only` returned `not-installed`.

Note what makes this dangerous rather than merely broken: nothing reports it. The
device boots normally, the version screen shows the old build, and if you are not
looking for the version you conclude the install worked.

### What a manual route user actually does

`FwPkt.zip` is rooted at `FwPkt/`, so extracting it at the SD root produces exactly
the tree the watcher wants — `/app/sd/FwPkt/camera/{config,uImage,rootfs.ubifs,
appfs.ubifs}`. The reboot alone is the trigger; no marker file or command is needed.

1. Copy `FwPkt.zip` to the SD root and **extract it there**, so the card ends up with
   a `FwPkt/` folder, not a zip. On Windows/macOS double-click works; the device also
   has `/usr/bin/unzip` (busybox) if they can reach it.
2. Copy `polaris-astro.zip` and `polaris-wifi.zip` to the SD root and extract each.
   Both are rooted at their own directory, so they expand to `polaris-astro/` and
   `polaris-wifi/`. Repeat every release. If the release also carries
   `astrometry-indexes.zip`, extract that once — it is ~44 MB and never changes.
3. Reboot. The watcher flashes from `/app/sd/FwPkt/`, then the boot hook installs the
   astro stack. Wi-Fi auto-join stays off until the user creates
   `/app/sd/polaris-wifi/autojoin`.

The card mounts `vfat` with `fmask=0022`, so extracted files land `755` and binaries
execute straight off the card — no helper on the user's computer is required.

Check the release directory before writing instructions for a specific candidate:
`astro-v99-wifi-20261108` ships its catalogue as `polaris-astro/catalogue-tiles.ptri`
*inside* `polaris-astro.zip` and publishes no `astrometry-indexes.zip`, whereas earlier
candidates published the indexes separately. Telling a user to fetch a file that is not
in their release is its own kind of silent failure.

### What the manual route cannot do, and what we must say instead

- **It cannot verify.** The device has `sha256sum`, `md5sum`, `cmp` and `unzip`, so a
  determined user could check digests against the release README — but that is not a
  supported step and nobody should be told their install "worked" without it.
- **It cannot prove the flash happened.** A link flap or a failed watcher looks
  identical to a successful boot from the outside. See the traps section below.
- **It cannot roll back.** There is no automatic fallback; recovery means re-flashing
  a known-good packet by the same route.

So when writing user-facing instructions, state the expected version string and tell
them to read it back on the app's info screen. That is the only check available to
them, and pretending otherwise has already produced false "installed" reports.

### What the published README now says, and why it changed

`scripts/publish-astro-candidate.sh` generates the candidate README. Before this
change it told readers to "unzip polaris-astro.zip and polaris-wifi.zip at the SD card
root" and said nothing about `FwPkt`, while its closing line pointed at the systematic
route. That left a user with instructions that install the astro stack and silently do
nothing about the firmware — the exact shape of #58, produced by documentation rather
than code.

The template now states both routes explicitly: Route A (SD card plus one ssh command) covers
extracting `FwPkt/`, the two kit archives, running `install_astro.sh`, rebooting, and
**reading the version back in the app**;
Route B gives the `release-fwpkt.sh` command. The version string is interpolated from
`$DISPLAY_FWVER`, so the check a user can actually perform is stated in the artifact they
hold.

Two caveats on Route A that we should not paper over:

- It is **not** independently tested end-to-end. The mechanism is verified — `FwPkt.zip`
  is rooted at `FwPkt/`, so extraction at the SD root yields the tree the watcher reads,
  and `/usr/bin/unzip` plus `fmask=0022` were confirmed on-device — but nobody has run
  the whole user sequence on a fresh card and confirmed the flash. Until that happens,
  Route A is documented as *what a user with no other option must do*, not as a supported
  install.
- It produces **no proof**. If a candidate needs verified installation, it requires
  Route B in a supervised window. The README's "do not install until…" gate still applies
  to both routes and has not been relaxed.

## The one command

```sh
./scripts/release/release-fwpkt.sh out/<candidate-id>
```

Run the current host-aware wake/preflight before this command when the rig may
be asleep:

```sh
./scripts/polaris-preflight.sh --wake --wait 120 --scan 20
```

This is the supported Bluetooth process. It may route host tools through
`flatpak-spawn --host`, verifies a held Bluetooth link rather than trusting a
zero exit from `bluetoothctl connect`, and treats an empty BLE scan as
inconclusive. If the AP is already visible and the identity/SSH checks pass,
deployment can proceed without Bluetooth wake. If Bluetooth is unavailable,
record that as a host wake limitation, not as evidence that the firmware is
dead or that the rig is asleep.

Options: `--skip-trigger` (stage + verify, no reboot), `--allow-busy` (only after
confirming no exposure is in flight), `--max-wait SECS`, `--host IP`.

It performs six phases and fails closed at each:

| # | Phase | Fails closed on |
|---|---|---|
| 0 | Gate | zip digest ≠ `install-manifest.json`; unrecognisable device `FwVer`; camera present (code 286 `state:1`); device already at target version |
| 1 | Pre-flight | SSH unreachable; low space on `/app/sd` |
| 2 | Stage | tar/stream failure; then removes stray `FwPkt.zip`/`.part` |
| 3 | Verify | any `firmwareInfo` MD5 mismatch on-device |
| 4 | Trigger | records `/proc/uptime` before rebooting |
| 5 | Wait | device not back within `--max-wait`; **uptime did not reset** |
| 6 | Confirm | `build_id`, both source commits, display version, or any mandatory file SHA-256 mismatch (`scripts/verify-installed-build.sh`) |

## Why the tree, not the zip (issue #58)

The on-boot watcher consumes the **extracted tree** at `/app/sd/FwPkt/`. Staging
only `FwPkt.zip` is silently ignored. This has repeatedly produced "install
succeeded" reports against a device that never changed:

> `.67` first attempt staged `FwPkt.zip` and rebooted; the device came back on
> `.66` with the zip untouched and `--verify-only` returned `not-installed`.
> — `docs/evidence/o-v17b-install-20261019/INSTALL-VERIFICATION.md`

`release-fwpkt.sh` is the only installer that stages the tree, which is why it is
canonical. The other two stage the zip and are deprecated:

| script | status | why |
|---|---|---|
| `scripts/release/release-fwpkt.sh` | **supported** | stages the tree; verifies MD5s; proves the boot |
| `scripts/o-v17a-autonomous-install.sh` | deprecated | stages `FwPkt.zip` only → ignored by the watcher (#58) |
| `scripts/attempt-fwpkt-install.sh` | deprecated | zip-only; expects a padded zip; fires 812 rather than `/sbin/reboot` |

Their useful gates (manifest digest, device identity, camera-idle check, uptime
proof) have been ported into `release-fwpkt.sh`, so nothing is lost by using it.

## Traps that produced false "installed" verdicts

**1. An AP-link flap is not a reboot.** During the `.67` install, SSH vanished
several times and each "went dark" looked like a flash. It was not: Mlog kept
writing fresh lines, Clog was empty, there were zero `FwPkt`/`upgrade`/`SYS_REBOOT`
lines, and `/proc/uptime` kept climbing past 27,000 s continuously since boot.
`/sbin/reboot` was killed mid-flap before it ran.

The installer now records `/proc/uptime` before rebooting and **requires it to be
lower afterwards**. If it is not, the script exits 5 and says plainly that nothing
was installed. Do not override this.

**2. Never compare `/app/FwVer` alone.** It does not contain the build_id. An older
script compared the wrong fields and turned a mismatch into a warning, which let a
test against `o-v15i` be reported as a test of a later candidate. Confirmation goes
through `scripts/verify-installed-build.sh`, which compares build_id, both source
commits, the display version, and every mandatory file's SHA-256.

**3. The wire port multiplexes telemetry onto any socket.** Querying code 286
(camera state) on port 9090 usually returns whatever is already buffered — the
device's continuous `284@mode:...` gimbal and `517@yaw:...` attitude frames — not a
camera answer. Reading the whole reply as camera state makes every install look
busy or unrecognisable. The installer splits the reply on `#`, takes only the frame
starting `286@`, and treats "no 286 frame" as idle (nothing answered the camera
query). Only an explicit `286@...state:1` blocks a reboot.

**4. `installed-verified` says nothing about the astro kit.** Upgrading the rig to
`.104` with `release-fwpkt.sh` printed `Install status: installed-verified`,
`build_id=v104`, `display_fwver=6.0.0.54.104` and `SP_EVENT_UPGRADE_SUCCESS` in
Mlog — all true, all about the firmware alone. Afterwards `/app/astro` was empty,
there was no boot hook, and port 8090 refused connections. The installer never
mentions `/app/astro`, so a green run reads as "the device is ready" when the plate
solver is gone entirely. See the next section.

## Flashing firmware removes the astro kit

Flashing replaces the whole `appfs` volume, and `/app/astro` lives on it. So every
firmware flash deletes the astro stack **and** the boot hook that starts it:

```
before .104:  /app/astro/polaris-httpd present, /app/network_telnetd.sh = astro boot hook
after  .104:  /app/astro absent, /app/network_telnetd.sh absent, port 8090 closed
```

`release-fwpkt.sh` now does this itself as phase 7: after a confirmed flash it
runs `scripts/release/install-astro-kit.sh`, which stages the kit, verifies every
staged byte against `ASTRO-MANIFEST.sha256`, runs `install_astro.sh`, reboots so
the new boot hook fires, and **fails closed unless port 8090 is actually
serving**. Pass `--no-kit` only when deliberately leaving the solver off, and the
script will say so. To run the step on its own:

```sh
./scripts/release/install-astro-kit.sh out/<candidate> --no-indexes --reboot
```

Route A step 4 and Route B still need `install_astro.sh` re-run after the flash,
on every release, not just the first. Confirm it took by opening
`http://<polaris ip>:8090` — a correct firmware version in the app is not evidence
that the kit came back.

**Stage with tar over ssh, never `scp`.** The device's sshd has no `sftp-server`
subsystem, so `scp` dies with `scp: Connection closed`, and legacy `scp -O` hangs.
This is why `release-fwpkt.sh` streams `FwPkt/` as one tar archive over a single
ssh session, and why the kit installer does the same:

```sh
tar czf - polaris-astro | ssh root@<ip> 'tar xzf - -C /app/sd && sync'
```

Hand staging has also tended to copy `polaris-astro/` only, leaving a stale
`polaris-wifi/` on the card. The installer stages both by default and skips only
the ~1 GB of astrometry indexes, which survive a flash because they live on the
card.

**`/app` is 68 MB and a flashed image uses most of it.** Measured on the rig after
the `.104` flash: `ubi1:ubifs 68.0M 68.0M 12.0K 100% /app`. `install_astro.sh`
copied the 20 MB catalogue into `/app/astro`, hit `cp: write error: No space left
on device`, and — because it runs under `set -e` and the catalogue copy sat *before*
the boot hook — died there. The binaries had already landed, so the device looked
installed while nothing could start. Two fixes:

- The boot hook is now installed immediately after the manifest check, while space
  is guaranteed, so a later failure costs optional data rather than autostart.
- The catalogue copies go through `copy_optional()`, which reports what did not fit
  and continues. Every consumer — `polaris-align.sh`, `polaris-guide.sh`,
  `polaris-frame-watch.sh`, `polaris-autosolve.sh`, `polaris-astro-boot.sh` — reads
  tiles from `/app/sd/polaris-astro/`, never from `/app/astro/`, so the mirror was
  dead weight. Removing it on the rig took `/app` from 100% to 83%.

Reproduced in `container/astro/test-install-enospc.sh`, which stubs `cp` to fail
only on the optional payloads. Against the pre-fix installer it fails exactly as the
device did — `polaris-httpd` installed, boot hook missing, exit 1.

**No shipped astro candidate had a manifest.** `install_astro.sh` compares bytes
against `polaris-astro.manifest`, and `build-astro-bundle.sh` has always generated
one and failed closed if empty. But production runs
`scripts/build-astro-candidate.sh`, which never created it — so every astro
candidate published to date shipped `polaris-astro.zip` without one, the installer
printed "installed files are unverified", and byte comparison silently never ran.
That is the #292 silent no-op returning through packaging rather than code.

Two bugs hid behind each other once it was fixed. `sha256sum` separates hash and
name with **two** spaces, so the existing `${line#* }` parse left a leading space on
every name and all 37 entries compared unequal; and scripts were copied *after*
verification even though the manifest lists `*.sh`, so shipping a manifest would have
made every install exit 1. Both are fixed, and `build-doctor.sh` section 8 now
asserts the ordering statically, before a build starts.

## Do not copy files into `/app` directly

`/app` is a writable UBIFS volume (`ubi1:ubifs on /app type ubifs (rw,relatime)`),
so `scp` into `/app/lib/stage2/` appears to work and the device reports the new
version. It is not an install:

- The NAND `appfs` image still holds the previous firmware, so the running system
  and the flashed image disagree. Any later full reflash silently reverts the
  change while the provenance file still claims the newer build.
- No `firmwareInfo` MD5 verification happens, so a truncated transfer boots.
- Nothing proves the boot was real, and no upgrade record is written.

**Do not use file ownership to tell a copy from a flash.** Both `.70` and a freshly
flashed `.71` show `/app/FwVer` and the camlibs owned by uid `1000`, because the
`appfs` image itself is built with that ownership. The reliable discriminators are:
the installer's uptime-reset proof, an `SP_EVENT_UPGRADE_SUCCESS` line in Mlog, and
`SP_DelUpgradeFiles` removing `/app/sd/FwPkt` after a successful flash.

**Evidence of the drift:** `.70` (`o-v17e-bulb-darkframe-poll-20261025`) runs on the
rig, and its only artifact directory `docs/evidence/o-v17e-flash-20261025/` contains
a single `byte-diff.txt` — no flash record, no MD5 verification output, no reboot
proof. Mlog has since rotated, so whether it was flashed or copied can no longer be
determined from the device. That ambiguity is exactly what this process removes:
`.71` has a complete record (see `docs/evidence/o-v18a-install-20261026/`).

Direct copies are acceptable **only** as a temporary diagnostic explicitly
authorised by the user, and they invalidate qualification evidence for that
candidate (see `AGENTS.md`). Record it in the candidate's `SUMMARY.md` when done.

## Release process wiring

`scripts/build-release-candidate.sh` now does two things so install cannot be
forgotten or improvised:

1. Prints the exact command for the candidate it just built:
   `== 6. install this candidate (the only supported path) ==`
2. Writes `install-status.txt` next to the candidate with `install_command` and
   `install_status=not-installed`. After phase 6 passes, the supported
   `release-fwpkt.sh` installer changes that status to `installed-verified` and
   writes `install-receipt.txt` with the target, device version, ZIP digest, and
   reboot evidence. A staged-only or fire-and-forget run never gets that status.

   It is a separate file on purpose. `build-source-provenance.txt` is written
   inside the patcher container and arrives owned by `nfsnobody`, so appending to
   it from the host fails with `EACCES`; under `set -e` that aborted the build
   *after* publishing, which is what happened on `.72`.

## Checklist for every install

1. Candidate has a registry row in `docs/FWPKT-PROVENANCE-CONTRACT.md` (zip MD5 +
   SHA-256, appfs MD5, both commit links). No row → do not stage.
2. `install-manifest.json` present and zip digest matches (the installer checks
   this; it must never be bypassed).
3. Camera idle, or `--allow-busy` only after confirming no exposure is in flight.
4. Run the installer. Do not interrupt the 5–10 min dark period.
5. Confirm phase 6 passed and uptime reset was reported.
6. Confirm the installer wrote `install_status=installed-verified` and
   `install-receipt.txt`; add the dated install record to `docs/CURRENT-STATE.md`,
   and save evidence under `docs/evidence/<candidate>-install-<date>/`.
7. If the candidate carries an astro kit, re-run `install_astro.sh` after the flash
   and confirm it printed both `boot hook installed` and `verified every manifest
   entry`. "installed files are unverified" means the card holds an older kit.
8. Open `http://<polaris ip>:8090`. The web UI is the only proof the kit survived
   the flash; `installed-verified` on its own does not cover it.

## Related

- `docs/FWPKT-PROVENANCE-CONTRACT.md` — artifact registry and handoff values
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` — building a candidate
- `scripts/verify-installed-build.sh` — the fail-closed identity comparison
- `docs/evidence/o-v17b-install-20261019/INSTALL-VERIFICATION.md` — both traps, in full
- `container/astro/test-install-enospc.sh` — reproduces the full-`/app` install failure
  and asserts the boot hook survives it (`NOSPACE=0` runs the happy path,
  `WITH_MANIFEST=1 TAMPER=1` asserts a stale binary is rejected)

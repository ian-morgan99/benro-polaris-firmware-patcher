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

## The one command

```sh
./scripts/release/release-fwpkt.sh out/<candidate-id>
```

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
   `install_status=not-installed`. A release is not finished until that status
   becomes `installed-verified` after phase 6 passes.

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
6. Set `install_status=installed-verified` in `out/<id>/install-status.txt`, add the
   dated install record to `docs/CURRENT-STATE.md`, and save evidence under
   `docs/evidence/<candidate>-install-<date>/`.

## Related

- `docs/FWPKT-PROVENANCE-CONTRACT.md` — artifact registry and handoff values
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` — building a candidate
- `scripts/verify-installed-build.sh` — the fail-closed identity comparison
- `docs/evidence/o-v17b-install-20261019/INSTALL-VERIFICATION.md` — both traps, in full

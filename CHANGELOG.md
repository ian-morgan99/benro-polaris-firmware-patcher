# Changelog

## Unreleased — Pentax capture memory budget (fixes #2)

libgphoto2's Pentax driver (`camlibs/ptp2/pentax-utils.c`) hard-codes a 2 GiB
single-capture cap (`PENTAX_CAPTURE_MAX_FILE_SIZE_DEFAULT`). On a desktop
workstation this is harmless. On the Polaris (512 MB – 1 GB userspace), a
single runaway tether request from a K-1 II / K-3 III would overcommit,
abort pgphoto mid-transfer, and leave the tether hung. The libgphoto2 fork
already reads the override env var `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`; we
expose it through the build chain with a safe 256 MiB default.

### Added
- **`--pentax-max-capture-size BYTES` / `-PentaxMaxCaptureSize BYTES`**
  flag on both `patch-polaris.sh` and `patch-polaris.ps1` (default
  `268435456` = 256 MiB).
- **`PENTAX_MAX_CAPTURE_SIZE`** container env var plumbed through both
  launchers alongside the existing `LIBGPHOTO2_VERSION` /
  `LIBGPHOTO2_PORT_VERSION`.
- **`container/ondisk/pgphoto.wrapper.in`** — added a third `sed`-able
  placeholder, `@PENTAX_MAX_CAPTURE_SIZE@`, that is substituted at build
  time and exported as `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`.
- **`container/ondisk/install_stage2.sh`** — added `PENTAX_MAX_CAPTURE_SIZE`
  env var with 256 MiB default in the documented-Inputs block.

### Changed
- **`container/patch.sh`** — wrapper-generation `sed` got a third
  substitution; the active value is now logged at startup
  (`Pentax capture cap: <bytes> bytes`).

### Verified (in-container pipeline)
- The sed substitution is exercised by the existing `libgphoto2` build step
  that already runs `pgphoto.wrapper` generation. A negative test with
  `--pentax-max-capture-size 1` would produce a wrapper that exports
  `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE=1`; the libgphoto2 fork's
  `pentax-utils.c` rejects anything below 1 MiB with `GP_LOG_E`. (Not
  auto-run in CI; requires on-device validation — see
  `docs/PENTAX-CAPTURE-BUDGET.md` §"Hardware evidence so far".)

### Docs
- New `docs/PENTAX-CAPTURE-BUDGET.md` documents the Polaris-RAM rationale,
  the chosen 256 MiB default, how to override, and the planned
  hardware-validation steps. Issue #2 closed against this work.

---

## Unreleased — Parameterise libgphoto2 path versions (fixes #1)

Any user passing `--libgphoto2 VER` to build a release other than the
default `2.5.34` was getting a silent mismatch: the patcher produced
fresh binaries with the right on-device layout but left the shipped
`pgphoto` wrapper pointing at hard-coded `2.5.34` / `0.12.2` paths. The
result was a 14-byte-patch-only noop against the stock 2.5.27 core — the
same symptom as issue #1's "vanilla build" reproducer.

### Added
- **`--libgphoto2-port VER` / `-Libgphoto2Port VER`** flag (default
  `0.12.2`) on both `patch-polaris.sh` and `patch-polaris.ps1`.
- **`LIBGPHOTO2_PORT_VERSION`** container env var (default `0.12.2`)
  plumbed through both launchers alongside the existing
  `LIBGPHOTO2_VERSION`.
- **`container/ondisk/pgphoto.wrapper.in`** — the on-device `pgphoto`
  wrapper is now generated from a `sed` template at build time, so the
  camlib/iolib paths it `dlopen`s match the staged
  `libgphoto2/<core>` / `libgphoto2_port/<port>` directories.

### Changed
- **`container/patch.sh`** — the six hard-coded `2.5.34` / `0.12.2`
  path literals (in-app install block + bundle assembly block) now
  read from `LIBGPHOTO2_VERSION` / `LIBGPHOTO2_PORT_VERSION`.
- **`container/ondisk/install_stage2.sh`** — same two env vars
  parameterise the `find_one` lookups and the `mkdir -p`/`cp` commands
  that populate `/app/lib/stage2`.
- **`.gitattributes`** — line-ending rule consolidated onto the
  `*.in` template; the old `pgphoto.wrapper` rule is gone (the file no
  longer exists; it is generated at build time).
- **`pgphoto.wrapper`** renamed to **`pgphoto.wrapper.in`** via `git mv`
  to preserve history; the template's `@CAMLIBS_VERSION@` /
  `@IOLIBS_VERSION@` placeholders are substituted at build time.

### Fixed
- Vanilla `--libgphoto2` builds now produce a working image
  (resolves the "no-op 14-byte patch" symptom in issue #1).
- Users building the Pentax development fork from a non-default
  release tag no longer need to hand-edit `pgphoto.wrapper` after
  the fact.

## Unreleased — FwPkt silent-reject fix (2026-08-27 combined build)

The Polaris on-board updater (`polestar_app → getFwInfo.sh → crcInfo`)
recomputes the MD5 and size of every component in `FwPkt.zip` and
string-compares both fields against `firmwareInfo`. A mismatch causes
a silent reboot with no user notification — the user sees the previous
firmware and no error.

The 2026-08-27 combined build (Pentax + HDMI 720p60) was rejected for
exactly this reason: the HDMI repack re-zipped `appfs.ubifs` but did
not re-run `gen_firmwareinfo.py`, so the shipped manifest still
advertised the Pentax-only `appfs` MD5 (`1775c7bc…`) while the
on-disk file was the HDMI-repacked one (`91629acf…`). One mismatched
line was enough to fail the whole update.

### Added
- **`container/verify_firmwareinfo.py`** — stdlib-only fail-closed
  offline re-MD5/size check. Re-runs the same algorithm the device
  runs. Exits 0 only on a perfect manifest↔file match; exits 1 with
  a per-line diff otherwise. Runnable on any existing build (stock,
  Pentax-only, combined, custom).
- **Build-time gate** in `container/patch.sh:386-396` — the
  verifier is invoked immediately after `gen_firmwareinfo.py` and
  the pipeline `die`s before the zip step on a mismatch. A layered
  repack that forgets to regenerate the manifest cannot leave the
  pipeline anymore.

### Fixed
- **`builds/2026-08-27-combined-720p60/FwPkt.zip`** repacked in place
  with a freshly regenerated `firmwareInfo`. The new manifest matches
  the shipped `appfs.ubifs` (`91629acf…`, 64,356,352 B). The on-board
  updater will now accept this packet.
  - SHA-256 fixed:   `ddc1aab69c97f9d2aea7492709c47f4ea3f1aca443fe5c08bf9ece41a2338e8e` (68,468,962 B)
  - SHA-256 broken:  `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf` (68,484,760 B)
  - The broken packet is preserved as `builds/2026-08-27-combined-720p60/FwPkt.zip.broken`
    for forensic reference; do not flash it.
  - A copy of the fixed zip is also on the SMB share at
    `smb://morganbackup.local/home/Projects/Pentax/BenroPolaris/2026-08-27_pentax-hdmi720p60-live_only/`.

### Verified
- The new gate was run against four targets and passed/failed as
  expected:
  - fixed zip → PASS 6/6
  - broken zip → FAIL 1/6 (the `appfs` mismatch described above)
  - fixed zip + 3-byte XOR mutation of `appfs.ubifs` → FAIL 1/6
  - stock `firmware/FwPkt/FwPkt/` → PASS 6/6

### Docs
- New `docs/silent-fwpkt-reject-postmortem.md` documents the
  mechanism, the layered-repack root cause, the fix, the fingerprints,
  and the recommended user flash order. Issues #19 and #20 are
  closed against this work.

---

## Unreleased — silent-gimbal-drop fix + finished-package structural validator (issue #21)

While exercising the clean-Pentax rebuild path (the full-stack local-fork
build), a **second, independent** silent-firmware-rejection surfaced. The
on-board `polestar_app` was still silently rebooting, but for a completely
different reason than the 2026-08-27 case.

### Symptom

A clean-Pentax build (`/libgphoto2-source-input` mounted) produced a
68,372,735 B zip containing **8** entries instead of the expected 10.
Both gimbal binaries (`polaris403_2.0.0.22.bin` and
`polaris413_2.0.0.22.bin`) were missing from the output. The on-board
updater would silently reboot (no NAND write, no UI signal, no log
entry), exactly as in the stale-`firmwareInfo` case.

The `verify_firmwareinfo.py` re-MD5/size gate from the previous section
**did not catch this** — because `firmwareInfo` is generated *from* the
on-disk state, the partial gimbal drop left the remaining gimbal line
correct and simply omitted the missing one. The bug is **structural**,
not content-based.

### Fixed
- **`container/patch.sh`** no longer swallows gimbal copy errors. The
  `2>/dev/null || true` that hid a missing `cp` is gone, and a
  pre-flight `ls`/`wc` check now `die`s with a clear "no /in/gimbal/*.bin
  found — refusing to ship a gimbal-less FwPkt (issue #21)" message
  before any output is assembled. See commit for the diff; the relevant
  section is the `8. Repack appfs … assemble` block in
  `container/patch.sh`.
- **`container/validate_fw_package.py`** (NEW, ~250 lines, stdlib-only) —
  the implementation of issue #21's spec. Walks the finished zip and
  rejects any of: wrong top-level layout, duplicate members, missing
  required files, stock-component drift (SHA-256 mismatch on any
  `camera/*` or `gimbal/*.bin` whose name matches a stock component),
  gimbal-dir empty. Always prints a concise manifest of every member and
  its on-disk size, then PASS/FAIL summary.
- The new validator runs **after** the zip is built and **before** the
  pipeline exits; a `die "refuse to ship"` on FAIL means a bad build
  cannot reach `builds/`, the SMB share, or an SD card.
- **Pentax-fork marker check is no longer a SIGPIPE false negative.**
  `container/patch.sh:166-170` had `strings | grep -Fq` under
  `set -euo pipefail`, which is a documented SIGPIPE footgun: grep
  exits 0 on match, `strings` keeps writing to the now-unread pipe, gets
  SIGPIPE (exit 141), `pipefail` propagates 141, and `set -e` turns that
  into a false "marker missing" abort. Replaced with `grep -Fc` (count
  mode, drains the pipe to EOF) and a string compare. See
  `docs/pentax-patcher-gate-bug.md` for the full analysis.

### Verified
- `validate_fw_package.py` run against six packages:
  - stock `firmware/FwPkt.zip` → PASS
  - fixed combined `builds/2026-08-27-combined-720p60/FwPkt.zip` → PASS
  - broken c2 build `/tmp/c2-rebuild/out/FwPkt.zip` → FAIL with 3 errors
    (missing `gimbal/*.bin`, missing `polaris403`, missing `polaris413`)
  - stock unzipped dir → PASS
  - wrong top-level folder (`WrongName/` instead of `FwPkt/`) → FAIL
  - true duplicate `FwPkt/firmwareInfo` member → FAIL
  - mutated `camera/config` (1-bit flip) → FAIL with exact
    expected-vs-actual SHA-256 diff

### Docs
- `docs/silent-fwpkt-reject-postmortem.md` addendum documents the
  silent-gimbal-drop root cause, why the firmwareInfo check is
  insufficient, and how the structural validator closes the gap. Issue
  #21 is closed against this work.
### Not tested
- Any camera other than the R5 Mark II; any firmware other than 4.0.0.32.

---

## Unreleased — Pentax + HDMI combined build (`builds/2026-08-27-combined-720p60/`)

A combined Pentax + HDMI patched FwPkt was produced on
2026-08-27 by layering the new HDMI geometry patcher over the
Pentax-only FwPkt at `builds/2026-08-23/`. This entry is
**informational** — it does NOT mark the combined build as a
release candidate.

### What was done

- Ported `hdmi_geometry_patch.py` from
  `agents/benro-polaris-firmware-docs` @ `5d0fc75` to
  `container/hdmi_geometry_patch.py` (the upstream version
  targeted a different `polestar_app` build).
- Re-patched the 5 LIVE HDMI sites in
  `bin/polestar_app` (md5 `067b8c3ba68f26141a7becc8d92c8ac0`).
- Re-packed `appfs.ubifs` with the patched `polestar_app`
  substituted in.
- Re-zipped the resulting bundle as
  `builds/2026-08-27-combined-720p60/FwPkt.zip` (md5
  `fd8147c91df44757d8a41c8bacc39519`, sha256
  `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf`,
  68,484,760 B).

### Release state

**Round-trip verified only.** The combined FwPkt is at the
second rung of the 7-rung release-state ladder documented in
[docs/CRITICAL-REVIEW.md](docs/CRITICAL-REVIEW.md) §0 — it
has NOT been validated on a Polaris device, a Pentax camera,
or an HDMI display, and the DEAD-site patches (8 sites in
the VENC / RTSP code paths) are deliberately excluded.

### Known limitations

- **Layered build.** The combined FwPkt was produced by
  patching the Pentax-only FwPkt's UBIFS rather than by a
  clean end-to-end rebuild from a current libgphoto2
  master. The embedded `libgphoto2.so` is at libgphoto2
  commit `da8c33482` (2026-08-26), not the current
  `ian-morgan99/libgphoto2` master. See
  [docs/CRITICAL-REVIEW.md](docs/CRITICAL-REVIEW.md) §8.5
  for the blocker plan that supersedes the layered build.
- **LGPL corresponding source is vanilla.** The tarball at
  `builds/2026-08-23/licenses/libgphoto2-2.5.34.tar.xz` is
  the upstream 2.5.34 release, not the Pentax-patched
  source. A real LGPL §6 archive must be regenerated from
  the exact `da8c33482` (or current master) checkout with
  Pentax patches applied.
- **No DEAD-site patches.** Sites 0x13c390, 0x13c394,
  0x13c398, 0x1629f0, 0x16ea90, 0x16eb30, 0x16eb70,
  0x16f080 (per `DEAD_SITES` in
  `container/hdmi_geometry_patch.py`) are not patched. The
  `--include-dead=0` flag is the default. Running with
  `--include-dead=1` is known to fail on the real
  firmware's `polestar_app` offsets.
- **No device / camera / HDMI validation.** See
  [docs/CRITICAL-REVIEW.md](docs/CRITICAL-REVIEW.md) §0
  for the 7-rung ladder and §8.5 for the path to a release
  candidate.

### References

- Operational record:
  [docs/RUN-JOURNAL.md](docs/RUN-JOURNAL.md)
- Critical review (with full gap list, 8.5 blocker plan,
  and the next-agent re-check list):
  [docs/CRITICAL-REVIEW.md](docs/CRITICAL-REVIEW.md)
- Final state of the build at the time of writing:
  [docs/FINAL-REPORT.md](docs/FINAL-REPORT.md)
- Docker image used to build / repack:
  [docker/README.md](docker/README.md) (image digest
  `sha256:b475ca01354845358d21e7adbf0eba9fffc3792e8f49a2d548cadf327cc27953`)
- Build provenance for the combined FwPkt:
  `builds/2026-08-27-combined-720p60/build-source-provenance.txt`
  (not committed; lives in `builds/` which is gitignored)

## v0.3.0-pentax-hdmi (tagged 2026-08-23 at commit `b3aa306`)

> **Note added 2026-08-27:** the `v0.3.0-pentax-hdmi` tag was
> created when only the patcher self-tests against a
> **synthesized stock buffer** had passed (13/13 LIVE sites
> matched against a Python re-encoding of the patcher output,
> not real firmware bytes). Verification against the real
> Benro Polaris firmware happened in subsequent commits
> (`4b8a3b7`, `4f1c5d3`, `58c166a`, and the four commits
> pushed as `0354a35` / `ef3c0be` / `fd0a21d` / `0c86436`).
> A reviewer running `git checkout v0.3.0-pentax-hdmi` lands
> on a tree that is **earlier than the actual verification
> work**. For the verified combined build see the
> `v0.3.0-pentax-hdmi-combined-720p60` tag (commit `0c86436`)
> and `builds/2026-08-27-combined-720p60/`. This note closes
> Gap 3.

## v0.3.0-pentax-hdmi-combined-720p60 (tagged 2026-08-27 at commit `0c86436`)

Annotated tag pointing at the verified combined-build state
described under the "Unreleased" section above. Tag
annotation records:

- Stock firmware md5
- Pentax base FwPkt md5
- Combined FwPkt md5 + size + sha256
- Docker image digest
- libgphoto2 commit (`da8c33482`)
- Build method (`combined_layered`)
- LIVE/DEAD site counts
- Release state (`round-trip verified (NOT device validated)`)

Inspect via `git cat-file -p v0.3.0-pentax-hdmi-combined-720p60`.

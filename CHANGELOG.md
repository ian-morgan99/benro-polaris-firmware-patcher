# Changelog

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
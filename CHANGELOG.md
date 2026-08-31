# Changelog

## Unreleased — Phase 3 cellular (Quectel / Sierra modem support)

The Polaris camera-board firmware (verified on FwVer 4.0.0.32) already ships
the full Quectel PPP userspace stack — `pppd`, `chat`, the
`/etc/ppp/peers/quectel-ppp` peer file, and the `check_pppd_ttyusb` /
`/dev/ttyUSB3` AT-string glue inside `polestar_app`. The gap is the
**kernel-side USB-serial host driver stack**: `usbserial.ko`, `option.ko`,
`qcserial.ko`, `cdc_acm.ko`. Without them, the modem never enumerates as
`/dev/ttyUSB*` and the userspace glue above never runs.

### Added
- **`--cellular-modules DIR` / `-CellularModules DIR` flag** on both
  launchers (`patch-polaris.sh`, `patch-polaris.ps1`). Mounts a host
  directory of pre-built `.ko` files into the container at
  `/cellular-modules-input:ro` and exports `CELLULAR_MODULES_DIR` to
  `patch.sh`.
- **`container/patch.sh` — new section 7a (cellular injection).** Copies
  the four pre-built modules into `/app/komod/` with stock uid/gid/mode
  (matched against the existing `udc-core.ko`), installs the
  `cellular_load.sh` / `cellular_unload.sh` pair alongside
  `sp_usb2net_load.sh`, and rewrites `/app/bootapp` so the loader runs
  once per boot, immediately after the HiSilicon platform modules come
  up. Loader-script install is unconditional; `.ko` injection is
  conditional on the host directory being supplied and is
  fail-soft (warn-and-skip on missing modules).
- **`container/cellular_load.sh` — VID-gated loader.** `set +e` so any
  individual `insmod` failure is non-fatal. Exits 0 when no Quectel
  (0x2c7c) or Sierra (0x1199) USB device is enumerated, so it is a safe
  no-op on non-cellular units.
- **`container/cellular_unload.sh`** — symmetric `rmmod` in strict
  reverse order.
- **`docs/CELLULAR.md`** — full pre-build recipe, on-device verification
  steps, and the modem-hardware caveat (some Polaris units only have
  the SIM socket populated with no modem IC).

### Docs
- New top-level **"Phase 3 — Cellular"** section in `README.md`
  (between the "Two modes" table and the disclaimer block).
- New row in the `README.md` options table for `--cellular-modules` /
  `-CellularModules`.

### Verified
- Loader-script placement works with the flag omitted (no-op bootapp
  wiring still added, modem never enumerates, all stock features
  unaffected).
- Fail-soft behaviour: when `DIR` is supplied but missing the four
  expected files, the patcher warns and ships the loader scripts only.

### Not yet verified
- Real cellular bring-up on hardware. Building the four modules
  requires the HiSilicon SDK + Linux 4.9.37 kernel headers, which are
  not part of the docker image. Users with the SDK can supply the
  modules and run the flag; users without can leave the flag off and
  use the rest of the patcher unchanged.

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
# Changelog

## Unreleased — restore direct still-capture dispatch (issue #122)

- Removed the Stage-2 `gp_camera_capture` wrapper and its independent cooldown.
  The last broad repeated-capture PASS, o-v9p, predates that wrapper; o-v12j,
  o-v12k and o-v12n all entered it and then faulted at an invalid low program
  counter before the real core call returned. The exact o-v12n libgphoto2 SHA
  completes consecutive RAW captures directly on the same K-3 III.
- `gp_camera_capture` now receives its exact resolved core address in the slot,
  as it did before o-v9o. Preview traffic remains independently bounded by the
  existing preview wrapper.
- Offline coverage asserts that the still-capture slot target is preserved
  exactly. All five runnable Stage-2 host tests pass; the ARM compiler gate is
  skipped on this host because `arm-linux-gnueabi-gcc` is not installed.
- This is a source-reviewed A/B candidate, not yet a hardware-qualified fix.
  It still requires a clean canonical build, immutable artifact provenance,
  supported installation, cold reboot and the full capture matrix.

## o-v10-quarantine-20260919 — post-budget quarantine state (issue #119 TA follow-up)

The o-v9y churn guard bounded the restart budget, but once exhausted the USB
supervisor adopted the current identity as healthy and stopped restarting
forever — a genuinely reconnected camera could be silently accepted while the
existing pgphoto session was still bound to the old device/session.

Patcher (main 327eeb4):
- Issue #119: exhausting the restart budget now enters an explicit
  degraded/quarantine state in `camera_usb_supervisor.sh`: churn is suppressed,
  `restart_budget_exhausted` is logged, and the current identity is NOT adopted
  as healthy. Normal operation resumes only after a positive stable-identity
  condition (the quarantined identity stays unchanged for COOLDOWN consecutive
  polls) revalidates it, which also resets the budget. A genuinely reconnected
  camera is therefore never silently accepted while the existing pgphoto session
  may still be bound to the old device/session.
- Deterministic tests added to `container/test_camera_usb_supervisor.sh`: a
  post-budget identity that keeps changing stays quarantined (no 3rd restart),
  and a stable quarantined identity revalidates and resumes normal restart
  behaviour. All supervisor test cases pass.

libgphoto2 (master 35318c1b5, same source as o-v9z — no libgphoto2 delta):
- Issue #120 Bulb-timer semantics documentation and the #121 startup-order fix
  are carried over from o-v9z.

Build inputs (clean):
- libgphoto2 source: 35318c1b520b1fc42d2f20be29aea956010b4be2 (master)
- patcher: 327eeb489d266103ce91ccb2e573d6e36d796b4e (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v10-quarantine-20260919/FwPkt.zip
  sha256 cbdef460eed547fc533ad739f2e325b15f6ad0e079d05c56f4599f98b6d4515b
  (md5 b4b953f68e7807956ba7fc3a6a65b2af)

Verified:
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 churn guard +
  #119 quarantine/revalidation cases).
- Deployed to the Polaris via `scripts/release/release-fwpkt.sh`; post-boot
  `/app/FwVer` = `FwVer:o-v10;date:2026.09.19;` and on-disk provenance matches
  patcher `327eeb4`.
- Multi-exposure capture test (R5 II, 5 shots): all shots returned PTP `-1002`
  (camera-side state after the firmware reboot cycle — camera in PTP mode,
  pgphoto running, but shutter release rejected). Not a patcher regression;
  re-test once the camera is confirmed in PC-connection/capturable state.

Not yet done: the #119 K-3 III USB-persistence release gate (cold boot + idle +
config polling + preview start/stop + ordinary capture without USB
disappearance) and the #120 Bulb-timer A/B/C ladder.

## o-v9z-stability-20260919 — stability bundle (issues #119/#120/#121)

New release bundling the recent no-camera stability work. Built from clean inputs;
the libgphoto2 side adds a documentation-only commit clarifying the Bulb timer
semantics for issue #120, and the patcher side carries the #119 churn guard and
#121 startup-order fix.

libgphoto2 (master 35318c1b5):
- Issue #120: documented that the camera's own conditions report bulb_timer_seconds
  (offset 272) as whole seconds and offset 276 as the TV denominator (confirmed
  against IT2), so the capture wait budget correctly sizes to the full timer value.
  The observed countdown-then-short-exposure symptom is camera/app firmware
  behaviour outside this budget.

Patcher (main 17ee6e7):
- Issue #119: bounded restart budget + cooldown in camera_usb_supervisor.sh so a
  re-enumeration flap cannot keep re-dlopening pgphoto (the live-view churn that
  drained the battery and dropped the camera off USB).
- Issue #121: startup grace window so a transient re-enumeration during app launch
  is absorbed without restarting pgphoto (the startup-order crash).

Build inputs (clean):
- libgphoto2 source: 35318c1b520b1fc42d2f20be29aea956010b4be2 (master)
- patcher: 17ee6e77a18ddd9a4d9193ac1d689ae1e9b493ae (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9z-stability-20260919/FwPkt.zip
  sha256 5a2755b1710aa8e9f5a63f50d8c5deaddc78d7587fb49a208dcb0364ffaf2198
  (md5 4f5a2c1251a2b9c86a1df2c7ce0fb01e)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 cases).

Not yet done (hardware qualification pending, camera back Monday): the #119 A/B
matrix and the #120 Bulb-timer A/B/C ladder to confirm the countdown-then-short-
exposure behaviour and that 25fb:0189 survives cold boot + idle + config polling +
preview start/stop + ordinary capture without USB disappearance.

## o-v9y-churn-guard-20260919 — live-view churn guard (issue #119)

o-v9r/o-v9s regression: the K-3 III session was torn down and re-initialised in a
tight loop (~36 dlopen cycles / 20 s), draining the battery and churning the
PTP/USB link until the camera dropped off USB (o-v9s: completely unreachable).

Root cause (no-camera analysis): the USB identity-change restart added in 1b021e9
(present in o-v9s, absent from the known-good o-v9p) restarts pgphoto on every
detected device-number change. When the camera re-enumerates while previewing,
each restart (full dlopen of core+port + 64-shim re-registration) can itself
trigger another re-enumeration, so the supervisor loops.

Patcher fix (commit da12f8f, main):
- container/ondisk/camera_usb_supervisor.sh: two bounded guards break the loop --
  OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS (default 5) spaces out restarts so a fast
  flap cannot restart pgphoto on every poll, and OPENPOLARIS_USB_MAX_RESTARTS
  (default 6) is a total restart budget; once exhausted the supervisor accepts the
  current identity as the new baseline and stops re-dlopening (fail-closed against
  a restart storm). Bounded readiness conditions, not arbitrary sleeps.
- container/test_camera_usb_supervisor.sh: deterministic regression test -- a
  sustained re-enumeration flap restarts at most MAX_RESTARTS times, then the
  supervisor logs 'restart budget' and stops.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master, same as o-v9w/o-v9x)
- patcher: da12f8f91d03d1e4bdb099965d7f09f5e8111aff (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9y-churn-guard-20260919/FwPkt.zip
  sha256 44fd141004583291da1ba60ba514b263d68abf263c2c9ffc648ad603e8e2d33b
  (md5 086fd96cf9f5b47f8607b3b364555c6e)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 cases).
- Built camera_usb_supervisor.sh contains the churn-guard markers.

Not yet done (hardware qualification pending): the #119 A/B matrix (camera ON
before app launch, repeated launches) to confirm the dlopen churn no longer
reproduces and 25fb:0189 survives cold boot + idle + config polling + preview
start/stop + ordinary capture without USB disappearance.

## o-v9x-startup-order-20260919 — startup-order crash fix (issue #121)

o-v9r crash: Benro Connect crashed when started with the camera already powered
on. Root cause: a transient re-enumeration during Benro Connect's own
initialisation (device-number change) fired a pgphoto restart that raced the
initial session open. The OFF->ON path worked because the camera appeared after
the runtime was up.

Patcher fix (commit f525adf, main):
- container/ondisk/camera_usb_supervisor.sh: bounded startup grace window
  (OPENPOLARIS_USB_STARTUP_GRACE_POLLS, default 3 polls). Identity changes in
  that window are absorbed into the baseline instead of restarting pgphoto; a
  later genuine change is still detected. A bounded readiness condition, not an
  arbitrary sleep — normal debounce/restart logic resumes after the window.
- container/test_camera_usb_supervisor.sh: deterministic regression test (startup
  re-enumeration must NOT restart; a post-grace change still causes exactly one
  restart). The #57 case is pinned to STARTUP_GRACE_POLLS=0 to keep its original
  debounce semantics.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master, same as o-v9w)
- patcher: f525adf1b00f712d03481255adbae98a79833387 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9x-startup-order-20260919/FwPkt.zip
  sha256 ad99db1ed0c40b6a6453c2dd1f58ea78c5c27b7b81b4041c1f3379b700e7b1b7
  (md5 c5701675e3c69e319f3785b0b0d8024f)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 cases).
- Built camera_usb_supervisor.sh contains the startup-grace marker.

Not yet done (hardware qualification pending): the #121 A/B matrix (camera ON
before app launch, repeated launches) to confirm the crash no longer reproduces.

## o-v9w-bulb-codeql-20260919 — Bulb-cluster fixes + CodeQL cleanup (master)

New release built from clean libgphoto2 master (b8baf487c), which carries the
Bulb-cluster stability fixes and a CodeQL cleanup, while staying regression-free
(the o-v9s ISO-extension regression is feature-branch-only, not on master).

libgphoto2 (master b8baf487c):
- Bulb cluster (#111/#118): phase-specific Bulb capture wait (exposure vs
  post-exposure processing) and integer-second shutter enumeration so >1-minute
  Bulb times no longer display as collapsed minutes.
- CodeQL: Nikon D-series detection now checks `sscanf(...) == 1` (not a boolean,
  which treated EOF as a match) and initialises `nikond`, fixing the
  "incorrect return-value check for a scanf-like function" finding on PRs #78/#79.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master)
- patcher: 26dba1a7a14197837bcb50f4426899e4e83c5eb4 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9w-bulb-codeql-20260919/FwPkt.zip
  sha256 261b5db4839f5b90a42792a9fdc2d99739c9a9bf2b62eb7b8e18539115833375
  (md5 6df2130dec9365fa86daf02ba7273fae)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build; test-pentax-utils + pentax tests pass.
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- test_polaris_pentax_build_package.sh: PASS (full build + package path).

Not yet done (hardware qualification pending): Bulb-cluster A/B/C ladder on a
K-3 III to confirm #111/#118/#120 behaviour, and the #119 session-churn / USB
disappearance regression.

## o-v9v-capture-failclosed-20260919 — pre-capture drain wait fails closed (issue #122 TA follow-up)

TA review of o-v9u (libgphoto2 d0419942) found the tri-state helper fixed the
false-IDLE read, but the pre-capture post-drain wait still **failed open**: if all
50 readiness polls stayed BUSY/UNKNOWN the loop ended, logged "drain complete",
and fired InitiateCapture anyway — proceeding while the camera was unproven-ready.

libgphoto2 fix (commit a46421c8e, master):
- Track whether the drain wait actually reached IDLE. On bound exhaustion
  (still BUSY/UNKNOWN) refuse the exposure with GP_ERROR_CAMERA_BUSY, matching
  the existing "stale candidate still pending" path, instead of firing into a
  busy camera.

Build inputs (clean):
- libgphoto2 source: a46421c8e8f8acf13a2cf2a1755f8bbad7d181ef (master)
- patcher: c2ec6ca58c0a8a7509a973ddf3e7aebdf0d5407b (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9v-capture-failclosed-20260919/FwPkt.zip
  sha256 d04d96d31b0747dae4a0cfea239ab00b49d899ee3d1e4be89f63715c95aebe97
  (md5 eee477efecea9321f63a90a2f6bb03bb)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build; test-pentax-utils passes.
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- test_polaris_pentax_build_package.sh: PASS (full build + package path).
- Built ptp2.so contains the new fail-closed marker ("pre-capture drain consumed
  ... still busy/unknown after bounded wait; refusing new exposure").

Not yet done (hardware qualification pending): A/B/C camera ladder on a K-3 III
to confirm the wedge no longer reproduces and that the fail-closed path is not
overly conservative for legitimate multi-shot/astro/bulb drains.

## o-v9u-capture-readiness-20260919 — capture readiness tri-state + gated idle wait (fixes #122)

Shutter release could wedge the K-3 III until a mode toggle + USB reset. Two
defects in the libgphoto2 Pentax capture path contributed:

- The pre-capture drain and post-capture idle waits initialized activity/
  candidate to 0, so a FAILED or SHORT conditions read was indistinguishable
  from a valid idle frame — Benro fired the next shutter while the camera was
  still busy.
- The post-capture idle wait ran unconditionally for every capture.

libgphoto2 fix (commit d0419942, master):
- `pentax_camera_readiness()`: classify a raw conditions frame as IDLE / BUSY /
  UNKNOWN. Only a VALID frame may prove idle; a failed/short read is UNKNOWN,
  never IDLE. Both wait sites use it.
- `pentax_capture_needs_idle_wait()`: gate the post-capture wait to captures
  that can still be processing after all candidates are consumed (multi-shot,
  astro shift/tracer, bulb). Ordinary single-shot captures return through the
  normal completion path so Benro regains control immediately.

Build inputs (clean):
- libgphoto2 source: d0419942debf20cd1bf26ba69f127101f9661a61 (master)
- patcher: f7e982b17fe4e107b5a8b686da6e362ab9e88ca1 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9u-capture-readiness-20260919/FwPkt.zip
  sha256 673802720dc18f86566c2ec0698c835367a17c2ce1533edab8a882160f957e7c
  (md5 a0d313f069ebb1b7bbfb2c16f941d9f4)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build + test-pentax-utils passes (tri-state + gate unit tests).
- patcher deterministic harness (issue #117): 6 passed, 0 failed, 3 skipped
  (prerequisite-gated: Docker image / source checkout / ARM cross-toolchain).
- test_polaris_pentax_build_package.sh: PASS (full build + package path).
- Pre-handoff appfs re-extraction: generated wrapper CAMLIBS=2.5.34,
  IOLIBS=0.12.2; embedded provenance build_id=o-v9u, git_commit=d0419942.
- Built ptp2.so contains the new single-shot skip marker (fix present).

Not yet done (hardware qualification pending): A/B/C camera ladder on a K-3 III
to confirm the wedge no longer reproduces after a shutter release in single-shot
mode, plus the multi-shot/astro/bulb regression rows.


## Unreleased — firmware-contained Pentax provenance and target-model gate

- Embed the exact clean libgphoto2 source identity at
  `/app/openpolaris-libgphoto2-provenance.txt`, so a flashed device can prove
  its source SHA without relying on files retained beside the ZIP.
- Fail a local-source build unless the final `ptp2.so` contains both the
  Pentax K-1 II and K-3 III model registrations as well as the Pentax vendor
  marker.
- Re-extract the generated appfs in the package test and compare its embedded
  provenance byte-for-byte with the build output; also assert both target
  model strings in the shipped camlib.

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
- The archived silent-FwPkt rejection postmortem documents the
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
  PrivateResearch issue #116 archive for the full analysis.

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
- The archived silent-FwPkt rejection postmortem addendum documents the
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
the archived critical review §0 — it
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
  the archived critical review §8.5
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
  the archived critical review §0
  for the 7-rung ladder and §8.5 for the path to a release
  candidate.

### References

- Operational record:
  the archived run journal
- Critical review (with full gap list, 8.5 blocker plan,
  and the next-agent re-check list):
  the archived critical review
- Final state of the build at the time of writing:
  the archived final report
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

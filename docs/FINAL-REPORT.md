# Pentax consolidation: final report

This is the consolidation final report. It records the
patcher/libgphoto2 provenance, the merge of upstream Pentax work into
the patcher, and the validation levels reached at end of consolidation.

## TL;DR

* Upstream Pentax work was **already present in libgphoto2 canonical
  `master` at `da8c33482e674692023fddcf32cb73d1dd4da05d`**. No Pentax
  code was ported across forks.
* The 4 `pentaxmodern/` divergent branches were evaluated, classified as
  work-toward-future-work, and **archived (left in place, not merged)**.
* Patcher compatibility is enforced by **7 fail-closed gates** plus 2
  invariants (Pentax markers) — see [docs/patcher-gates.md](patcher-gates.md).
* End-to-end patcher flow against a clean libgphoto2 checkout at
  `da8c33482` is validated in off-host emulation. The on-host qemu-arm
  pass covers all 2467 camera models plus the patcher's R5 II target
  `04a9:3314`.

## Provenance

| Item | Value | Source |
|------|-------|--------|
| libgphoto2 commit | `da8c33482e674692023fddcf32cb73d1dd4da05d` | [docs/canonical-pentax-source.md](canonical-pentax-source.md) §"Single SHA to build from" |
| libgphoto2 version tag | `2.5.34` (vendored, no v2.5.34 release) | `build_ptp2.sh:170` (`LIBGPHOTO2_VERSION` default) |
| Patcher SHA | this worktree HEAD (see git log below) | `git log --oneline -1` |
| Firmware model | Benro Polaris (cloud-linked gimbal) | `docs/HOW-IT-WORKS.md` |
| Build+package test | `container/test_polaris_pentax_build_package.sh` (formerly `test_polaris_pentax_e2e.sh`; renamed — see vetting issue #14) | a9b411a (this branch) |

### Reproduce the build-source provenance locally

```bash
# Inside a running patcher container with /libgphoto2-source-input mounted
cat /opt/patcher/build-source-provenance.txt
# expect:
#   source_kind=git-directory
#   requested_version=2.5.34
#   actual_version=2.5.34
#   git_commit=da8c33482e674692023fddcf32cb73d1dd4da05d
#   dirty_diff_hash=
```

The `dirty_diff_hash=` empty value is the proof of a clean local
source. The git_commit must match the canonical pointer in
[docs/canonical-pentax-source.md](canonical-pentax-source.md) — that
is the e2e test's gate at step 2.

## Git history on this branch

```
e89b55b Cross-link new docs (patcher-gates, canonical-pentax-source) from existing ones
b7b041e Document canonical Pentax source pointer and explain archived branches
fc52beb Document patcher compatibility gates and verify all are fail-closed
a9b411a Add end-to-end Pentax->Polaris regression test
7814a8d Point Polaris at authoritative Pentax matrix      ← Pentax consolidation pivot
2b505c7 Cross-compile complete stage2 loader in tests
ccde305 Gate compatibility shims to Canon R5 II
6210741 Fail closed for unverifiable candidate source
ab35781 Ship exact LGPL corresponding source
eeaab78 Bootstrap local source without dependency tracking
f7031f4 Build Polaris images from local libgphoto2 source
8a31a01 Add development plan and camera capabilities documentation for Pentax support in libgphoto2
```

The 3 commits tagged by `v0.2.0-pentax-consolidation` are
`fc52beb` → `b7b041e` → `e89b55b`. They are the audit, the canonical
pointer, and the cross-links.

## Branches evaluated and archived (not merged)

Four divergent libgphoto2 branches were evaluated as part of the
recon (see [docs/canonical-pentax-source.md](canonical-pentax-source.md)
§"Branches evaluated and **not** merged"):

| Branch | Tip SHA | Base SHA | Status |
|--------|---------|----------|--------|
| `c99-compliance-pentax` | `dbac81d2a` | `bfce85402` | archived |
| `copilot/add-failed-print-detection` | `cf6b97e7d` | `a5dede52` | archived |
| `fix-pentax-deps` | `f1c8e120f` | `bfce85402` | archived |
| `pentax-modern-integration` | `f1d50cf7f` | `bfce85402` | archived |

All four add a parallel `camlibs/pentaxmodern/` directory (~1786
lines) that does **not** exist in canonical master. The canonical
Pentax support is in the mature `camlibs/pentax/` (pslr-based) which
already has the desired behaviour. The `pentaxmodern/` branches
represent an alternate line of work and are not required for Polaris
compatibility.

The branches are **not deleted**; they remain in the libgphoto2
fork for archival. The patcher does not consult them.

## Pentax-related changes pulled from canonical master

The following Pentax matrix changes (already in canonical master at
`da8c33482`) are the upstream evidence that Pentax support is
canonical, not a fork feature:

* `ptp2/pentax-utils.c` — K-3 III Astro mode (0x9011), K-1 II smart
  storage, K-3 III vendor wedge recovery, K-1 II 4-capture DNG
  regression, K-3 III post-power-cycle wedge.
* `8ba60c3e7` — stale-session recovery (close + USB port reset + reopen).
* `106ae5f98` — durable vendor-state reconciliation.
* `1340d8bd1` — 0-byte DNG download fix (fs-cache refcount).

The 2467-model matrix the patcher advertises in `LIBGPHOTO2_CAMLIB_DIR`
is what the canonical ptp2 + camlibs/pentax build produces at HEAD.

## Patcher compatibility gates (7 fail-closed, 2 invariants)

Full per-gate audit with line citations: [docs/patcher-gates.md](patcher-gates.md).

| Gate | Default | Flipped by | Source |
|------|---------|------------|--------|
| `ALLOW_DIRTY_SOURCE` | `0` (fail-closed) | explicit `=1` | `build_ptp2.sh:55` |
| `FIX_R5M2_TYPO` | `1` (active) | explicit `=0` | `patch.sh:29` |
| `COLD_START_TIMEOUT_MS` | unset (no override) | `MODE=ptp2only` | `build_ptp2.sh:183` |
| `REMOVE_KEEP_DEVICE_ON` | `0` (kept) | `MODE=ptp2only` | `build_ptp2.sh:192` |
| `REMOVE_EXIT_REMOTEMODE` | `0` (kept) | `MODE=ptp2only` | `build_ptp2.sh` |
| `SELFTEST` | `0` (skip qemu dlopen) | `=1` opt-in | `patch.sh:267` |
| `SWAP_USB1` | `1` (active) | auto-disabled if on-device libusb missing | `patch.sh:41,100,43` |

Invariants (not gates — must always hold):

* `local-source Pentax candidate marker: present` in build log
* `Pentax profile assertion: K-01 model string present in ptp2.so`

## Validation matrix

The 12 test results called for in the plan's "Required Final Report"
table are the following — each row is a single `bash` invocation that
runs to completion in <60s on a normal workstation.

| # | Test | Result | Evidence |
|---|------|--------|----------|
| 1 | `test_source_input.sh` clean-checkout path | PASS | `source-input preflight tests: PASS` (run during this session) |
| 2 | `test_source_input.sh` dirty-rejection path | PASS | same run (covered in suite) |
| 3 | `test_source_input.sh` archive input path | PASS | same run (covered in suite) |
| 4 | `test_source_input.sh` unsafe-archive rejection | PASS | same run (covered in suite) |
| 5 | `test_polaris_pentax_build_package.sh` step 2 (provenance SHA = `da8c33482`) | PASS | prior session, `/tmp/pentax-e2e-debug3/build-source-provenance.txt` |
| 6 | `test_polaris_pentax_build_package.sh` step 3 (FwPkt.zip + camera/ + gimbal/ produced) | PASS | `/tmp/pentax-e2e-debug3/FwPkt.zip` (md5 991d0960…) |
| 7 | `test_polaris_pentax_build_package.sh` step 4a (Pentax candidate marker in build log) | PASS | `/tmp/pentax-e2e-debug3/build.log` line 1 |
| 8 | `test_polaris_pentax_build_package.sh` step 4b (K-01 model string in ptp2.so) | PASS | same build.log line 2 |
| 9 | `test_polaris_pentax_build_package.sh` step 5 (stage-2 on-disk bundle: install/restore/libpolaris_stage2.so) | PASS | `/tmp/pentax-e2e-debug3/stage2-ondisk/` |
| 10 | `test_polaris_pentax_build_package.sh` step 6 (ptp2.so contains `Pentax vendor mode enabled`) | PASS | grep -F over on-host `strings` of `/out/lib/ptp2.so` |
| 11 | `test_polaris_pentax_build_package.sh` step 7 (stage-2 cross-compile with image's `arm-linux-gnueabi-gcc`) | PASS | same e2e run; uses image-bundled `stage2_ondisk_table.h` and `stage2_policy.h` |
| 12 | Off-host qemu-arm dlopen of 2467 models | PASS | `docs/TESTED.md` "Verified (offline/in emulation)" table |

### Why "Verified (offline/in emulation)" not "Verified ON REAL HARDWARE"

The Polaris is a cloud-linked gimbal; flashing custom firmware
requires physical hardware access. The build pipeline and the
patcher's pgphoto + stage-2 loader are verified by:

* **On-host x86 native build** — `test_source_input.sh` invokes
  `build_ptp2.sh` against a clean libgphoto2 checkout and asserts the
  build artifacts (see [docs/TESTED.md](TESTED.md)).
* **Cross-compile to ARM EABI soft-float** — the e2e test at step 7
  re-runs the stage-2 loader's `arm-linux-gnueabi-gcc` inside the
  patcher image, asserting the bundled toolchain accepts the
  `stage2_ondisk_table.h` and `stage2_policy.h` headers.
* **Off-host qemu-arm dlopen** — `SELFTEST=1` runs qemu-arm and
  dlopens the freshly-cross-compiled `libpolaris_stage2.so` against
  the device's stock 2.5.27 core, asserting all 2467 models register
  and `04a9:3314` (R5 II) registers correctly.

What remains for "ON REAL HARDWARE" is the device-side flash of the
custom `appfs.ubifs` and the on-device `ondisk/install_stage2.sh`
step. This is documented in `docs/HOW-IT-WORKS.md` and is the
end-user's responsibility; it cannot be done in CI without the
physical gimbal.

## Files added or modified in this consolidation

| Path | Action | Commit |
|------|--------|--------|
| `docs/patcher-gates.md` | added (132 lines, 7-gate audit) | fc52beb |
| `docs/canonical-pentax-source.md` | added (single SHA + 4 archived branches) | b7b041e |
| `docs/TESTED.md` | appended "Related documentation" footer | e89b55b |
| `docs/HOW-IT-WORKS.md` | appended "Related documentation" footer | e89b55b |
| `README.md` | added 2-line cross-link | e89b55b |

## What is not in scope of this consolidation

* The on-device flash + on-device `ondisk/install_stage2.sh` step.
  This is the device-side work the user must perform; it is
  documented in `docs/HOW-IT-WORKS.md` and the patcher's flash
  warnings.
* Removing the 4 `pentaxmodern/` branches from the libgphoto2 fork.
  They are archived, not deleted; removal is the fork owner's call.
* Bumping libgphoto2 past `da8c33482`. Future Pentax matrix work
  happens upstream; the patcher tracks `master` at the most-recent
  Pentax-aware commit. See [docs/canonical-pentax-source.md](canonical-pentax-source.md)
  for the policy.

## HDMI geometry patcher (post-consolidation extension)

The Pentax consolidation ships the **patcher side** of the project's
goal: a Polaris firmware that is a Pentax-aware libgphoto2 stack
(Pentax matrix at the canonical upstream `da8c33482`). What the
consolidation does **not** touch is the **input side** of the gimbal:
the HDMI input chain hard-codes 1920x1080@30 in the device's
`polestar_app` binary.

An HDMI geometry patcher is shipped alongside the patcher as a
companion tool. It is a stand-alone Python script (no firmware
rebuild required) that rewrites the immediate operands at the sites
that hard-code width/height/fps so a build can target a different
static timing. The current scope is the static slice (5 live sites in
`SP_CreateHdmiTask` + `SP_VI_SetMipiAttr`); dynamic items (VI re-init
on `VideoChange`, VPSS deinterlace) are deliberately not started and
interlaced input is unsupported by design. Phase D (HDMI TX
enablement) is explicitly out of scope — it is the highest-brick-risk
item in the plan and is not started.

| Item | Value |
|------|-------|
| Patcher | `container/hdmi_geometry_patch.py` (146 lines) |
| Source commit | `5d0fc75` on `agents/benro-polaris-firmware-docs` |
| Live sites | 5 (always patched) |
| Dead sites | 10 (`--include-dead` only; in code paths not exercised by the LIVE flow, per static/signature analysis) |
| Default | 1920x1080@30 — byte-exact no-op against pristine stock |
| 720p60 build | changes exactly 5 words; verified against pristine stock |
| Idempotency | detects already-patched bytes; refuses in-place writes; aborts on unexpected bytes |
| Documentation | [docs/HDMI-IMPLEMENTATION-PLAN.md](HDMI-IMPLEMENTATION-PLAN.md), [docs/HDMI-INPUT-EXPLORATION.md](HDMI-INPUT-EXPLORATION.md) |

Combined end state: **Pentax libgphoto2 (canonical `da8c33482`) +
HDMI geometry (Phase E static slice) assembled into a single
build-verified candidate at
`builds/2026-08-27-combined-720p60/FwPkt.zip`.** The combined
Firmware Patcher tooling has been built and round-trip-verified; the
patcher + companion script path produces a candidate that satisfies
the goal "produce a single FwPkt containing both Pentax and HDMI
patches." The candidate is **not** yet a release: it has not been
emulation-verified, Polaris-boot-verified, camera-verified, or
HDMI-verified. See [CRITICAL-REVIEW.md](CRITICAL-REVIEW.md)
§"Release-state vocabulary" for the full ladder and the gates
required to advance. Device-side flashing of the candidate, if
attempted, is the end-user's responsibility and is at their own
risk; see [docs/HOW-IT-WORKS.md](HOW-IT-WORKS.md).

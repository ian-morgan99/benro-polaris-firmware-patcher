# Mandatory libgphoto2 upgrade and camera-regression process

Status: **normative** for every future libgphoto2 change consumed by this firmware patcher.

This document exists because a libgphoto2 build can work correctly when invoked directly with `gphoto2` and still fail when used through the Polaris `pgphoto` / Stage-2 runtime. The upstream `blaineam/benro-polaris-firmware-patcher` implementation already demonstrates this class of integration risk: its hardware-validated full mode treats libgphoto2 as a matched stack (core + port + camlib + iolib), redirects `pgphoto` through an on-disk Stage-2 trampoline, and deliberately installs camlib/iolib components into both Stage-2 and stock lookup locations.

A future upgrade is therefore **not** complete when the new `ptp2.so` builds, nor when direct `gphoto2` works. It is complete only when the complete packaged runtime is proven and the previously supported camera matrix has not regressed.

## 1. Scope

This process is mandatory for any change to:

- the libgphoto2 source SHA/tag;
- `libgphoto2.so.6`;
- `libgphoto2_port.so.12`;
- `ptp2.so` or another camera camlib;
- `usb1.so` or another iolib;
- Stage-2 loader/trampoline code;
- `pgphoto` wrapper, launcher, patch sites, environment or loader paths;
- `CAMLIBS`, `IOLIBS`, `LD_LIBRARY_PATH` or `LD_PRELOAD` handling;
- ABI, glibc ceiling, symbol-version or `DT_NEEDED` assumptions;
- model-gated compatibility shims;
- firmware install paths that can alter which library/camlib/iolib is actually loaded.

## 2. Non-negotiable architecture invariant

Treat the packaged camera stack as one compatibility unit:

```text
pgphoto wrapper / launcher
  -> pgphoto.stage2ondisk
  -> Stage-2 loader / trampoline
  -> libgphoto2.so.6
  -> libgphoto2_port.so.12
  -> libgphoto2/<version>/ptp2.so
  -> libgphoto2_port/<version>/usb1.so
  -> device libusb / kernel USB stack
  -> camera
```

Do not upgrade or replace one member and assume the others remain compatible.

The build must prove that the runtime loads the intended files, not merely that those files exist in the image.

## 3. Upgrade record: freeze inputs before coding

Create one upgrade/qualification issue before changing the packaged stack. Record:

```text
old libgphoto2 SHA/tag
new libgphoto2 SHA/tag
old libgphoto2_port ABI/version
new libgphoto2_port ABI/version
patcher base SHA
stock FwPkt SHA-256
Polaris firmware version
all currently qualified camera bodies + firmware versions
reason for upgrade
expected functional change
known generic PTP2 changes between old/new source
```

The candidate must use an immutable source SHA. `master`, `latest`, a moving branch, or an unrecorded dirty worktree is not a release input.

If a dirty source tree is deliberately used for investigation, it is diagnostic only unless its dirty hash is captured and the exact content is subsequently committed and rebuilt cleanly.

## 4. Build-time compatibility gates

Before any device install, fail the build if any of these are not proven.

### 4.1 Architecture and ABI

For every packaged ELF camera component record and assert:

- ARM architecture / EABI appropriate for Hi3559V200;
- expected ELF class/endian/float ABI;
- glibc symbol ceiling <= device glibc;
- `SONAME` and `DT_NEEDED` compatibility;
- versioned symbol requirements and providers;
- no unresolved libgphoto2/libgphoto2_port/libusb symbols;
- expected executable/shared-library type.

`libgphoto2.so.6` and `libgphoto2_port.so.12` must be built from a mutually compatible source/build configuration. Never accept a small or stripped-looking replacement merely because its filename/SONAME matches.

### 4.2 Runtime-path manifest

The build manifest must list SHA-256, size, architecture and intended runtime role for at least:

```text
/app/bin/pgphoto
/app/lib/stage2/pgphoto.stage2ondisk
/app/lib/stage2/libpolaris_stage2.so
/app/lib/stage2/libgphoto2.so.6
/app/lib/stage2/libgphoto2_port.so.12
/app/lib/stage2/libgphoto2/<camlib-version>/ptp2.so
/app/lib/stage2/libgphoto2_port/<iolib-version>/usb1.so
/app/lib/libgphoto2/<stock-path>/ptp2.so        (when intentionally replaced)
/app/lib/libgphoto2_port/<stock-path>/usb1.so   (when intentionally replaced)
```

If the running Polaris can load a component from more than one location, document all locations and either make them intentionally identical or prove which one wins.

### 4.3 Loader proof

Offline/QEMU tests must prove:

- Stage-2 core and port `dlopen` successfully;
- every expected trampoline/boundary symbol resolves;
- the intended camlib and iolib enumerate;
- model registration still contains every camera used in the regression matrix;
- model-gated shims remain fail-closed for non-target cameras.

QEMU/emulation is necessary but **not sufficient**. Blaine's upstream work records Polaris-kernel failures that did not reproduce in qemu-user.

## 5. Direct libgphoto2 baseline — prove source behavior first

Before installing the candidate firmware, test the new exact libgphoto2 SHA with each physically available regression camera directly attached to a host.

Minimum direct test per camera:

1. cold camera / fresh USB session;
2. `gphoto2 --version` plus proof of loaded library/camlib provenance;
3. `--auto-detect` and `--summary`;
4. config enumeration;
5. safe GET -> SET -> GET -> restore round trip for at least one supported setting;
6. preview/live-view start and valid non-zero JPEG;
7. capture and file integrity where supported;
8. repeated process exit/reconnect;
9. power-cycle/reconnect;
10. any model-specific capability previously qualified.

Record debug traces for failures and identify the **first failing PTP transaction**, not merely the final GP error.

A direct failure belongs to libgphoto2 investigation. A direct pass followed by Polaris failure is, by default, a patcher/runtime integration failure until disproved.

## 6. Clean firmware build only

Build the candidate from:

```text
known stock FwPkt hash
+ exact clean patcher SHA
+ exact clean libgphoto2 SHA
+ explicit build parameters
```

No runtime/library replacement over SSH counts as a fix or qualification run. SSH may be used for read-only diagnostics. After any direct runtime mutation, reinstall a canonical FwPkt before collecting qualifying evidence.

The patcher tree itself is also a release input. `patch-polaris.sh` must refuse
release builds when the patcher Git worktree is dirty. A diagnostic dirty build
may use the explicit `--allow-dirty-patcher` opt-in, but it is not releaseable;
its dirty-tree hash must be recorded and the resulting FwPkt must not be staged
or installed. Do not record only the libgphoto2 SHA: the generated wrapper,
Stage-2 loader, packaging scripts, and patcher-side appfs changes are part of
the artifact's provenance.

The output must include:

- FwPkt SHA-256;
- component manifest;
- source provenance;
- patcher SHA;
- libgphoto2 SHA;
- full build parameters;
- generated path/version values for CAMLIBS/IOLIBS;
- expected runtime hashes.

Before handoff, re-extract the produced appfs and assert the generated
`/app/bin/pgphoto` wrapper contains the exact CAMLIBS/IOLIBS and release preview
policy expected by the build. Source-template tests alone do not prove the
packaged appfs contains the intended wrapper.

## 7. On-device runtime-loader proof before camera claims

After installing the exact candidate and cold rebooting, prove the runtime before testing camera functionality.

Required checks:

```text
/app/bin/pgphoto exists and is executable
exactly one pgphoto runtime process owns the camera path
wrapper points to the intended Stage-2 executable
CAMLIBS/IOLIBS/LD_LIBRARY_PATH/LD_PRELOAD are the intended values
Stage-2 core/port hashes equal the build manifest
camlib/iolib hashes in every active lookup location equal the manifest
no "No iolibs found" / unresolved symbol / wrong ABI messages
pgphoto successfully initialises at least one known camera
preview port/process ownership is singular and stable
```

Capture `/proc/<pid>/maps`, process command line and relevant environment or equivalent loader evidence where available. File presence alone is not proof of use.

## 8. A/B/C camera qualification ladder

For each camera body, use the same camera firmware and intended USB mode.

### A — direct host

Exact new libgphoto2 SHA + camera directly attached.

### B — Polaris local

Exact packaged libgphoto2 SHA + firmware/runtime, with OpenPolaris absent. Exercise the operation through the Polaris-owned runtime/CLI/protocol boundary.

### C — OpenPolaris end to end

Exact OpenPolaris version + same firmware candidate + same camera.

Interpretation:

```text
A FAIL + B FAIL at same underlying PTP operation
  => libgphoto2 candidate defect.

A PASS + B FAIL
  => patcher / pgphoto / Stage-2 / loader / path / session defect.

A PASS + B PASS + C FAIL
  => OpenPolaris defect.

A FAIL + B PASS
  => libgphoto2 issue masked/compensated by appliance integration; investigate before release.
```

Compare the first divergent lower-level operation, not merely matching top-level error numbers.

## 9. Mandatory no-regression camera matrix

Every libgphoto2 upgrade must retest **all cameras previously claimed as physically supported**, not only the camera motivating the upgrade.

At minimum maintain rows for every physically qualified body. Current work should prioritise:

- Canon EOS R5 Mark II — upstream patcher reference regression camera;
- Pentax K-3 III;
- Pentax K-1 II;
- any other body subsequently promoted to hardware-qualified status.

For each body record PASS/FAIL/N/A for:

- cold detection;
- config read;
- safe config write/read-back/restore;
- preview start / first valid JPEG;
- preview stop/restart;
- normal capture;
- capture/download integrity;
- repeated capture soak;
- reconnect/process restart;
- USB unplug/replug;
- camera power-cycle;
- model-specific functions intentionally supported;
- rollback to the previous known-good candidate.

A camera previously marked PASS cannot silently become N/A or “not tested”. If hardware is unavailable, the upgrade remains **unqualified for release** with respect to that camera unless the owner explicitly accepts the regression risk.

## 10. Canon-specific and Pentax-specific containment

Any compatibility shim or workaround must have a model/capability gate and a negative regression test.

For each upgrade verify:

- R5 II shims still match only the intended Canon model spellings/capabilities;
- Pentax-specific behavior does not alter Canon/non-Pentax paths;
- generic PTP2 changes are either proven generic or vendor/model-gated;
- an unknown/unqualified camera cannot accidentally inherit a workaround.

## 11. Release decision and terminology

Use these states only:

```text
SOURCE-VALIDATED      direct libgphoto2 tests pass
BUILD-VALIDATED       static/ABI/QEMU/package gates pass
RUNTIME-VALIDATED     Polaris loader/process/path proof passes
CAMERA-VALIDATED      required physical camera matrix passes locally on Polaris
E2E-VALIDATED         OpenPolaris matrix passes
RELEASE-QUALIFIED     all required gates + rollback + provenance pass
```

Do not call a build “fixed”, “safe”, “shippable” or “release-qualified” based only on direct `gphoto2`, compilation, QEMU, image assembly, or one camera.

## 12. Required document updates for every upgrade

Before closing an upgrade issue, update all applicable records:

- `docs/canonical-pentax-source.md` — exact canonical libgphoto2 SHA and status;
- `docs/TESTED.md` — exact firmware/patcher/libgphoto2 provenance and per-camera matrix;
- `docs/HOW-IT-WORKS.md` — only if loader/path/stack behavior changed;
- `docs/patcher-gates.md` — any changed environment, model, ABI or build gate;
- the current candidate `docs/evidence/.../SUMMARY.md` — concise build/install/test evidence;
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` — if this process itself changes;
- README — supported/qualified camera and version claims;
- libgphoto2 fork hardware matrix (`#44` / canonical hardware log) — direct tests only;
- OpenPolaris E2E matrix (`#56` / `#63`) — application-level evidence only.

Do not copy an E2E PASS into the libgphoto2 direct-hardware record, and do not substitute a direct libgphoto2 PASS for Polaris/OpenPolaris qualification.

## 13. Required automated tests

The patcher should grow deterministic tests that fail when these invariants break:

1. **full-stack completeness** — core, port, ptp2, usb1, wrapper, Stage-2 loader and target executable are all packaged;
2. **version/path consistency** — generated CAMLIBS/IOLIBS match the packaged directory names;
3. **dual-lookup consistency** — where stock lookup paths remain active, staged and stock-path camlib/iolib copies have the expected hashes;
4. **ELF architecture gate** — x86/x86_64 binaries cannot enter an ARM FwPkt;
5. **symbol-version gate** — the core/port pair satisfy each other's versioned symbols;
6. **DT_NEEDED gate** — every dependency exists on the target image;
7. **launcher gate** — `/app/bin/pgphoto` is present, executable and references an existing target;
8. **model registration regression** — previously qualified camera IDs remain registered;
9. **shim containment** — model-specific shims return false/no-op for representative other vendors;
10. **manifest completeness** — all load-bearing camera-stack files have hashes and source provenance;
11. **no direct-SSH release path** — release tooling/docs may not deploy replacement camera binaries directly to `/app`;
12. **previous-candidate differential** — unexpected changes outside the declared camera-stack file set fail the build/review gate.

Physical tests remain mandatory; automation protects the integration contract but cannot replace real camera qualification.

## 14. Stop conditions

Stop the upgrade and do not flash/release if any of these occurs:

- source provenance cannot be proven;
- core/port ABI or versioned symbols are inconsistent;
- active camlib/iolib path is ambiguous;
- runtime loads a different file than the manifest expects;
- direct camera behavior regresses;
- a previously supported camera cannot be retested and owner has not accepted the risk;
- Stage-2 requires an undocumented device mutation to work;
- OpenPolaris is required to reproduce a source/runtime defect;
- a workaround changes generic behavior without containment evidence.

## 15. Current 2026-09-07 lesson

The K-3 III preview differential is the reference example for this process:

- exact libgphoto2 SHA can produce a valid preview with direct `gphoto2` on the Polaris;
- the packaged `pgphoto` / Stage-2 path fails;
- investigation found a Stage-2 `libgphoto2_port.so.12` / iolib lookup/packaging problem and a missing `/app/bin/pgphoto` launcher problem;
- Blaine's upstream hardware-validated architecture already treats the matching port library, iolib paths, wrapper and Stage-2 loader as load-bearing parts of the upgrade.

Therefore no further Pentax libgphoto2 change should be made to address that preview symptom until the packaged runtime is restored to this contract and retested through A/B/C.

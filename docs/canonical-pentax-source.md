# Canonical Pentax source — what to build, and how to upgrade it safely

This document identifies the libgphoto2 source that the Polaris patcher may consume. It is a provenance pointer, **not permission to move to a newer SHA without qualification**.

Normative upgrade process: [`LIBGPHOTO2-UPGRADE-PROCESS.md`](LIBGPHOTO2-UPGRADE-PROCESS.md).

## Current status — 2026-09-07

The most recent camera-functional Pentax commit used in the current physical investigation is:

| What | Value |
|---|---|
| libgphoto2 fork | `ian-morgan99/libgphoto2` |
| camera-functional SHA | `6aa3e4e66240d4b4d68a65b75631e0f6aadf308a` |
| commit | `ptp2/pentax: fix K-3 III capture and setting verification` |
| physical integration evidence | current Polaris candidate reports this exact embedded SHA |
| current libgphoto2 repository HEAD | may be newer due documentation-only commits; **do not substitute HEAD automatically** |

A documentation-only commit after `6aa3e4e66` adds stricter repository ownership/regression instructions but does not constitute a newly qualified camera binary. Firmware provenance must identify the exact source SHA actually built.

The older `da8c33482e674692023fddcf32cb73d1dd4da05d` pointer was a prior canonical point from the August consolidation. It is retained as historical evidence only and must not be described as the current candidate source.

## Critical packaging lesson

A canonical libgphoto2 SHA does not by itself define a valid Polaris camera stack.

Blaine's upstream hardware-validated full-mode architecture treats these as one compatibility unit:

```text
pgphoto wrapper / launcher
pgphoto.stage2ondisk
libpolaris_stage2.so
libgphoto2.so.6
libgphoto2_port.so.12
libgphoto2/<version>/ptp2.so
libgphoto2_port/<version>/usb1.so
active stock-path copies of ptp2.so / usb1.so where the runtime still looks there
```

The 2026-09-07 K-3 III investigation demonstrated why this matters: direct `gphoto2` using the embedded `6aa3e4e66` code can return a valid preview, while the packaged `pgphoto` / Stage-2 route fails. That differential is integration evidence against the package/runtime, not evidence that the Pentax source needs another change.

Therefore the source pointer in this file may be changed only as part of a complete matched-stack upgrade and regression cycle.

## Mandatory process for moving this pointer

Before replacing the current camera-functional SHA:

1. Open one patcher upgrade/qualification issue naming old SHA, new SHA, reason and affected generic/vendor code.
2. Review the libgphoto2 diff, especially generic PTP2, port/session, filesystem, config and transfer paths.
3. Run the direct libgphoto2 hardware matrix at the new exact SHA.
4. Build a complete matched Polaris stack from a clean source input.
5. Pass architecture, ABI, symbol-version, `DT_NEEDED`, manifest and loader-path gates.
6. Install only through a canonical FwPkt; no release-qualified direct SSH replacement.
7. Cold-boot and prove which core, port, camlib and iolib the running `pgphoto` actually loads.
8. Rerun every previously qualified camera, including non-Pentax regression bodies.
9. Run OpenPolaris E2E only after the Polaris-local path passes.
10. Update this file only when the candidate's exact SHA and qualification state are known.

Full requirements and stop conditions are in [`LIBGPHOTO2-UPGRADE-PROCESS.md`](LIBGPHOTO2-UPGRADE-PROCESS.md).

## How the patcher picks the source

The patcher's build path accepts one of three source forms, in priority order:

1. `/libgphoto2-source-input` mounted as a Git checkout;
2. `/libgphoto2-source-input` mounted as a source archive with SHA-256 captured;
3. a downloaded upstream release tarball.

For a development/fork candidate, prefer an immutable archive or clean checkout of the exact SHA. `master`, `latest`, or an unrecorded dirty tree is not a release-qualified input.

If a dirty checkout is explicitly allowed for investigation, the dirty hash must be recorded and the resulting image is diagnostic until the same content is committed and rebuilt cleanly.

## Source provenance required in every candidate

`build-source-provenance.txt` or its successor must make it possible to answer without inference:

```text
repository/source kind
requested ref
actual Git SHA
clean/dirty state
source/archive SHA-256 where applicable
libgphoto2 core version
libgphoto2_port ABI/version/path
camlib version/path
exact patcher SHA
```

The firmware manifest must additionally record hashes/sizes/architecture for all load-bearing camera-stack files. See the upgrade process document.

## Archived branches — do not build from them

The historical `pentaxmodern` branches were exploratory and are not canonical:

- `archive/c99-compliance-pentax`
- `archive/fix-pentax-deps`
- `archive/pentax-modern-integration`
- other pre-consolidation/backup branches

Do not build a firmware candidate from an archived branch merely because it contains additional Pentax-looking code. Any revival is a new libgphoto2 change and must pass the complete direct-hardware plus consumer regression process.

## If previously archived Pentax work is reconsidered

1. identify one exact source branch/SHA;
2. rebase or selectively port onto current canonical code;
3. explain generic PTP2 impact file-by-file;
4. add deterministic source-repo tests;
5. run the complete direct Pentax hardware matrix;
6. prove non-Pentax/generic behavior is not regressed;
7. then run the entire patcher upgrade process before moving this pointer.

## Evidence separation

Keep these records distinct:

- **libgphoto2 direct hardware evidence** — proves source/library behavior;
- **Polaris-local evidence** — proves the packaged pgphoto/Stage-2/runtime integration;
- **OpenPolaris E2E evidence** — proves the client/protocol/application path.

A PASS at one layer must never be copied into another layer's qualification column.

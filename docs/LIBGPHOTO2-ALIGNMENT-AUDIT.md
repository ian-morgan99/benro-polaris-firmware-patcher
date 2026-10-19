# libgphoto2 alignment audit — patcher assumptions vs upstream source

Date: 2026-10-19
Upstream reference: `8e06d39aea9ff22be9a59a5962263bdf41fc76e7` (2026-10-19), the commit
`o-v17c` (`.68`) was built from.
Patcher reference: `49b547c`.

## Why this exists

Every release so far has verified the *output* — hashes, manifests, on-device behaviour.
None of it verified the *assumptions*: that the versions, sonames, module directories,
configure flags, struct layouts and `sed` anchors the patcher hard-codes still describe
the upstream tree it is pointed at. This document checks each one against source, and
records the result either way, so the next upgrade starts from evidence rather than hope.

Method: read the upstream file, read the patcher file, compare. Where an assumption is
executable (an anchor, a struct size, a symbol), it was executed rather than eyeballed.

## Verdict

**All twelve load-bearing assumptions hold.** Nothing in the current build is wrong, and
`.68`'s artifacts are unaffected. Three structural gaps were found that are not defects
today but will bite on the next version bump or the next upstream rebase; they are
listed under Divergences and filed as an issue for the coding agent.

## Aligned — verified

| # | Patcher assumption | Upstream fact | How verified |
|---|---|---|---|
| 1 | libgphoto2 `2.5.34` | `meson.build:2` `version : '2.5.34'`; `configure.ac:10` `[2.5.34]` — the two build systems agree | read both |
| 2 | port `0.12.2` | `meson.build:42` `libgphoto2_port_version = '0.12.2'` | read |
| 3 | `libgphoto2.so.6` | `meson.build:36-39` `age=4`, `current=10` → `current − age = 6` | arithmetic |
| 4 | `libgphoto2_port.so.12` | `meson.build:44-47` `age=2`, `current=14` → `12` | arithmetic |
| 5 | module dirs `libgphoto2/2.5.34`, `libgphoto2_port/0.12.2` | `meson.build:217` `camlibs_dir_suffix = project_name / project_version`; `:214` `iolibs_dir_suffix = port_name / port_version` — exactly the scheme the loader and manifest assume | read |
| 6 | camlibs `ptp2,pentax` exist and are selectable | both present under `camlibs/`; `--with-camlibs` is a real option (`configure --help` line 111) | read + `configure --help` |
| 7 | `--without-libcurl --without-libxml-2.0 --without-jpeg` is safe for `ptp2,pentax` | shipped `pentax.so`: **0** undefined `curl`/`xml` symbols, no `NEEDED` entry for either; `camlibs/pentax/*.c` contains **0** curl references | `nm -D --undefined-only`, `readelf -d`, grep |
| 8 | `--with-libusb-1.0=no --with-libusb=no` are real flags | they are options of the **port subconfigure** (`libgphoto2_port/configure.ac:368` `GP_CHECK_LIBRARY([LIBUSB1]…)`, `:417` `GP_CHECK_LIBRARY([LIBUSB]…)`), reached because the top level does `AC_CONFIG_SUBDIRS([libgphoto2_port])` (`configure.ac:659`). They do not appear in the top-level `--help`, which is why a naive check reports them missing — they are valid | read + `usb1.so` is in fact produced and shipped |
| 9 | `--no-suite no-ci` skips exactly one hardware-dependent test | upstream declares **one** suite in the whole tree, `no-ci` (`libgphoto2_port/tests/meson.build:15`), containing exactly `test-gp-port`. The gate's documented SKIP is precise, not a blanket suppression | grep across all `meson.build` |
| 10 | `_Camera` pad to 4140 B | `gphoto2/gphoto2-camera.h:333` `struct _Camera {` … `:344` `};` — the `awk` anchor matches; struct is 5 pointers = **20 B** on the shipped target (confirmed `ELF32 ARM`), so `20 + 4120 = 4140` is correct | anchor test executed; `readelf -h` |
| 11 | "the new core exports `gp_filesystem_set_info_dirty`, so no trampoline shim is needed" | declared `gphoto2/gphoto2-filesys.h:245`, defined `libgphoto2/gphoto2-filesys.c:2353` | read |
| 12 | loader ABI constants: `GP_WIDGET_TEXT == 2`; `CameraAbilities` starts with `char model[128]` | `gphoto2-widget.h:55-59` order is `WINDOW=0, SECTION=1, TEXT=2`; `gphoto2-abilities-list.h:121` `char model [128];` is the first member | read |

### Out-of-tree `sed` patches — all three anchors still match

| patch | anchor | upstream location |
|---|---|---|
| R5m2 model-name typo | `"Canon:EOS 5Rm2"` | `camlibs/ptp2/library.c:2593` |
| cold-start endpoint window | `#define USB_CANON_START_TIMEOUT 1500` | `camlibs/ptp2/library.c:57` |
| keepdeviceon removal | `CR (camera_keep_device_on (camera));` (3 sites) | `camlibs/ptp2/library.c` ×3 |

Note the asymmetry in failure mode: the R5m2 patch is `sed … || true` and the
keepdeviceon patch is a global `sed` — if an anchor ever moves, the build keeps going
and silently ships unpatched behaviour. Only the timeout patch reports anything, and it
reports success unconditionally. See Divergence D3.

### Guards that already work (keep these)

- `container/build_ptp2.sh:104-108` reads the source version out of `configure.ac` and
  **fails the build** if it does not match the requested version. This is the single
  most valuable guard in the pipeline; it is what makes the pinned version self-checking.
- `container/build_ptp2.sh:307` fails if a selected camlib was not actually produced —
  "selected but silently dropped" is impossible.
- `scripts/generate-fwpkt-manifest.py:148-152` fails if `lib/stage2` exists but a
  mandatory file is absent, so the hard-coded paths in `:58-60` cannot silently ship a
  stale tree.
- `container/stage2_loader.c:110-114` uses `#ifndef` guards, so the module directories
  are overridable at compile time rather than truly fixed.

## Divergences

### D1 — the gate and the ship build are different configurations

`scripts/build-release-candidate.sh:50` runs upstream's tests with **meson**:

```
meson setup "$TEST_BUILD" "$SRC" --buildtype=debugoptimized -Dcamlibs=ptp2,pentax,directory
meson test -C "$TEST_BUILD" --no-suite no-ci --print-errorlogs
```

The libraries that actually ship come from **autotools** (`container/build_ptp2.sh:273`):

```
--with-camlibs="ptp2,pentax" --without-libxml-2.0 --without-jpeg --without-libcurl
```

Same commit, different build system, different dependency graph. Upstream's meson build
links `pentax` against libcurl and libxml (`camlibs/pentax/meson.build:22`, gated at
`meson.build:67`); the shipped build links neither. So the 21 upstream tests never run
against the configuration that ships.

This is *currently benign* — the symbol check in row 7 proves the shipped `pentax.so`
needs neither library — but it is unverified by construction, and it is the reason the
gate needs host packages the build image does not. Cheapest fix: assert the shipped
`pentax.so`/`ptp2.so` have no unmet `NEEDED`/undefined symbols as a gate step, which
tests the artifact rather than the build system.

### D2 — a version bump needs coordinated edits in ≥4 places, and that is undocumented

| file | line | what must change |
|---|---|---|
| `container/patch.sh` | 38 | `LIBGPHOTO2_VERSION` default |
| `container/stage2_loader.c` | 111, 114 | `STAGE2_CAMLIBS_DIR`, `STAGE2_IOLIBS_DIR` |
| `scripts/generate-fwpkt-manifest.py` | 58-60 | mandatory install paths |
| `container/stage2_loader.c` | 326, 1181 | ABI comments/constants tied to 2.5.34 layout |

The version guard (row 1 of the guards above) catches the *first* one only. If the
source is bumped and the loader's `STAGE2_CAMLIBS_DIR` is not, the build succeeds, the
gate passes, and the device silently dlopens a directory that no longer exists — caught
only at the on-device stage. `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` describes the upgrade
*process* thoroughly but never enumerates this surface.

### D3 — silent-anchor risk on the three `sed` patches

All three anchors match today. Two of the three fail silently if they stop matching.
A grep-and-fail assertion per anchor costs almost nothing and converts a silent
behavioural regression into a build error.

### D4 — `directory` appears in the gate's camlib set but not the ship set

Deliberate (upstream's tests need it) and harmless, but undocumented, so it reads like
an oversight. One sentence in the gate script is enough.

## What this does *not* cover

- Runtime behaviour on other bodies (K-1 II remains untested for the relaxed
  `_pentax_prop_get` branch — see the `.68` qualification caveats).
- Anything about the correctness of the patcher's own feature work; this is an
  assumptions audit, not a design review.

## Reproducing

```sh
UP=../LibGphoto2/libgphoto2          # at 8e06d39ae
# version + soname + module-dir scheme
sed -n '1,3p;36,47p;214,218p' $UP/meson.build
# the only test suite upstream declares
grep -rn "suite:" $UP --include=meson.build
# shipped artifacts carry no unmet deps
nm -D --undefined-only out/<candidate>/stage2-ondisk/libgphoto2/2.5.34/pentax.so | grep -icE 'curl|xml'
readelf -d out/<candidate>/stage2-ondisk/libgphoto2/2.5.34/pentax.so | grep -E 'NEEDED|SONAME'
# sed anchors still present
grep -n 'define USB_CANON_START_TIMEOUT 1500\|"Canon:EOS 5Rm2"' $UP/camlibs/ptp2/library.c
grep -c 'CR (camera_keep_device_on (camera));' $UP/camlibs/ptp2/library.c
# _Camera pad anchor
awk '/struct[ \t]+_Camera[ \t]*\{/{f=NR} f && /^};/{print f"->"NR; exit}' $UP/gphoto2/gphoto2-camera.h
```

## Ownership

Findings D1–D4 are build-pipeline work, filed for the coding agent. This document is
the checking/validation record; it changes no behaviour.

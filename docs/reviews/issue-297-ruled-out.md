# #297 layer 3 — hypotheses tested and refuted

Every item below was checked against a command's output on the exact artifact the device runs
(`libgphoto2.so.6` sha256 `cefa7b39…`, identical locally and on the device). None of these is a
guess, and none of them is the cause.

| hypothesis | how it was tested | result |
|---|---|---|
| lazy init — nothing asked yet | `GET :8080/?action=stream`; then read opcode 292 from httpd's `/api/link` | **refuted twice.** pgphoto answered HTTP 200 with the MJPEG boundary and no frame; `preview-state = state:1` (count 453) |
| wrong libgphoto2 loaded | full paths in `/proc/10026/maps` | **refuted.** `/app/lib/stage2/libgphoto2.so.6`, ours |
| CAMLIBS/IOLIBS wrong | `/proc/10026/environ` | **refuted.** both correct and versioned |
| camlib dir unreadable | process is uid 0; dir is `drwxr-x--- 1000:1000` | **refuted.** root bypasses those bits |
| `CAMLIBDIR_PREFIX_ENV` skip filter | env dump | **refuted.** not set, so `foreach_func`'s filter is inactive |
| camlibs lack `camera_id`/`camera_abilities` | `nm -D --defined-only` on both | **refuted.** both export both |
| `camlibs.manifest` clobbered libgphoto2's list-of-names | read `gphoto2-abilities-list.c` in the exact 2.5.34 source | **refuted.** that file never reads `camlibs.manifest`; it enumerates with `lt_dlforeachfile` |
| capture guard refusing init | env dump + `stage2_capture_guard_enabled()` | **refuted.** `STAGE2_CAPTURE_GUARD` unset, guard off |
| camlib `DT_NEEDED` unsatisfiable | `readelf -d` on pentax/ptp2 vs shipped libs | **refuted.** all four/five needs are present and mapped |
| ELF version-node mismatch (`gp_log@LIBGPHOTO2_5_0`) | `readelf -V` requirement vs definitions | **refuted.** `libgphoto2_port.so.12` defines `LIBGPHOTO2_5_0`; the requirement is met |
| undefined symbols unresolvable | `nm -D --undefined-only` diffed against both libs' exports | **refuted.** remainder is libc/libm/loader only (`sprintf`, `stderr`, `iconv`, …) |
| atime shows ltdl never opened them | `stat -c %X` on the camlibs | **void, not evidence** — see below |

## The atime trap

All four files showed `atime == mtime`, which looks like "never read since install". It is worth
nothing: `/app` is `ubi1:ubifs`, and a direct control — record `atime`, `cat` the file, re-read
`atime` — left it unchanged (`1793940974` before and after, with `date +%s` at `1794200645`).
Access times do not update on this mount. Had I reported the first reading as evidence, it would
have looked decisive and been meaningless.

## What is actually established

- pgphoto (PID 10026) owns :8080 — confirmed by socket-inode match, not assumption.
- `libgphoto2.so.6`, `libgphoto2_port.so.12` and **`libltdl.so.7`** are all mapped. ltdl is the
  thing that would dlopen a camlib, so the machinery is present.
- Nothing libgphoto2 dlopens at runtime is mapped: no `pentax.so`, no `ptp2.so`, and also no
  `usb1.so`/`usbscsi.so`. In `gp_camera_init`'s auto-detect path those two loads are adjacent
  (`gphoto2-camera.c:707` then `:709`), so their joint absence points at the abilities-list load
  itself rather than a later USB step.
- `camera-info` publishes `manufacturer:none;model:none;state:-110;storage:0` every 30 s (count 456).

## Why it cannot be taken further read-only

Our shipped libgphoto2 has logging compiled out — no `GP_DEBUG` string anywhere in the `.so`, and
`nm -D` lists 195 exports with zero `gp_log*` symbols. Setting `GP_DEBUG` therefore produces
silence indistinguishable from "init was never reached", which is the exact ambiguity to resolve.
No `strace`, `ltrace` or `gdb` on the device, and no qemu/binfmt ARM execution locally, so an
offline `dlopen` reproduction is not available either.

The next step is the one-line probe already committed (`7396bd1`): `STAGE2_TRACE_INIT_ENTRY=1`
prints whether the `gp_camera_init` shim is entered, whether the real core symbol resolved, and
what it returned. It needs a rebuild plus a deliberate restart, so it has not been run.

## Two things that would mislead anyone continuing this

- **Symbolising a crash offset against a different build's binary is invalid and fails silently.**
  Resolving LR `libgphoto2.so.6+0xeb34` against the v99 `.so` returns `gp_camera_set_config` —
  confident and wrong, because `.dynsym` lists only exports and the nearest preceding export spans
  that address. `gp_context_progress_start` sits at `0x17fbc` in that build. The dump carries no
  build-id to match against.
- **`/tmp/gphoto-debug.log` is not ours.** gphoto2 CLI 2.5.27.1 with a `CAMLIBS` lacking the
  version subdir; its `Failed to load '…/libgphoto2/2'` is fully explained by ltdl enumerating the
  directory `2.5.34` and treating `.5.34` as an extension.

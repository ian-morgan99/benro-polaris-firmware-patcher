# Changelog

## Unreleased — full-libgphoto2 stack swap is now the DEFAULT (hardware-verified)

- Added `--libgphoto2-source` / `-Libgphoto2Source` so an in-development local
  checkout (including the Pentax fork) can be mounted read-only, copied into the
  container build workspace, bootstrapped with Autotools, and packaged.
- Removed the obsolete duplicate `DEVELOPMENT_PLAN.md`; the canonical Pentax
  plan and live progress ledger are maintained in the libgphoto2 repository.
- Package the exact post-transformation libgphoto2 corresponding source in both
  modes, including local-fork builds, instead of relying on an upstream link.
- Fail closed for dirty local source without explicit opt-in, incompatible
  source versions, missing Pentax candidate markers, unsafe archives, and
  candidate ptp2-only QEMU self-test failures; emit exact source provenance.

The patcher now replaces the **entire** libgphoto2 stack by default — core + port
+ ptp2 camlib + usb1 iolib, all fresh 2.5.34 — instead of only the ptp2 camlib +
usb1 iolib. The old camlib/iolib-only swap becomes the opt-in **fallback**.

### Changed
- **Default mode is now `full`.** No mode flag = full-libgphoto2 swap. The
  conservative legacy swap (keep the stock 2.5.27 core; swap only ptp2 + usb1 +
  the 14-byte `pgphoto` patch) is now **`--ptp2-only` / `-Ptp2Only`**.
- Docs lead with full mode as the default and the hardware-verified path;
  ptp2-only is documented as the fallback.

### Added — full mode
- **On-disk trampoline core swap.** `pgphoto` (non-PIE `ET_EXEC`) has the 64
  libgphoto2 boundary functions it calls (`gp_*`/`gp_port_*`) rewritten in the
  file to an absolute indirect jump through a pointer slot; a fresh-2.5.34 core is
  `dlopen`ed and each slot filled at startup. **No runtime `.text` mprotect, no
  `/proc/self/mem`** (three earlier runtime-patching loaders were crashed/refused
  by the Hi3559V200 kernel). The trampolined binary is byte-count-identical to
  stock (only 719 `.text` bytes differ; entry point unchanged).
- **Loader `libpolaris_stage2.so`** (`container/stage2_loader.c`): mmaps a fresh
  `MAP_FIXED` slot page at `0x30000000` (with a `/proc/self/maps` overlap
  pre-check), fail-closed `abort_stub` baseline for all slots, `dlopen`s core+port
  by absolute path (env-less), `SIGSEGV` pinpoint handler + checkpoints.
- **`container/stage2_patch.py`** — generic on-disk trampoline patcher (fail-closed
  on any undersized/unresolved/out-of-segment boundary entry; derives the
  reliability-patch sites from the stock↔base diff and refuses if a trampoline
  would clobber one).
- **`container/build_fullstack.sh`** (+ `FULLSTACK=1` and `POLARIS_DBG=1` in
  `build_ptp2.sh`) builds `libgphoto2.so.6` + `libgphoto2_port.so.12` alongside
  ptp2/usb1, with `struct _Camera` padded to 4140 bytes (Benro-tail ABI parity; an
  interop size constant, ABI-inert, nothing proprietary), and skips the ptp2
  trampoline shim (the fresh core exports `gp_filesystem_set_info_dirty` natively).
- **`container/dbg_patch.py`** (POLARIS_DBG, shippable, **no tracing**) makes the
  Canon EOS init-time drains non-fatal (`config.c` check_eos_events ×13; `library.c`
  keep_device_on ×3 + check_eos_events ×1) so `camera_init` completes as the real
  Canon driver instead of falling back to the generic PTP class driver. A documented
  LGPL source modification (see `NOTICE`). `trace_patch.py` remains a dev-only
  `TRACE=1` diagnostic that is never shipped.
- **Loader shims** in `stage2_loader.c` (both on via the wrapper): `STAGE2_STORAGE_SHIM`
  writes the Benro `_Camera` storage-type so the app shows a card (**no "no card"
  warning**); `STAGE2_TETHER_CAPTURE` forces Canon `capturetarget` to "Internal RAM"
  via `gp_camera_set_config` + `gp_camera_set_single_config` (the Polaris drives
  configs via `set_single_config`, so that hook is the one that fires). Internal-RAM
  capture uses the `ObjectTransfer` path (card-mode `ObjectAddedEx` is not delivered
  through the fresh core), so a shot completes and **both JPEG and RAW** download.
- **Self-driving wrapper** (9-line, no logging) installed as `/app/bin/pgphoto`
  (exports CAMLIBS/IOLIBS/LD_LIBRARY_PATH/LD_PRELOAD + the two shim toggles, execs
  the trampolined binary from `/app/lib/stage2`).
- **Stock-path camlib/iolib placement.** The fresh `ptp2.so`/`usb1.so` are written
  to the stock on-disk paths (`/app/lib/libgphoto2/2.5.27.1/ptp2.so`,
  `/app/lib/libgphoto2_port/0.12.0/usb1.so`) **as well as** the `stage2/` tree — the
  swapped core loads its camlib/iolib from the stock paths at runtime, not from the
  exported `CAMLIBS`. Stock perms preserved (camlib `0750`). Every other appfs file
  (other iolibs, kernel, rootfs, gimbal, U-Boot env) stays byte-identical.
- **Reversible on-device bundle** `out/stage2-ondisk/` (`install_stage2.sh` /
  `restore_stock.sh`) to test before flashing, and `out/licenses/` (libgphoto2
  `COPYING` LGPL-2.1 + source offer). New top-level `NOTICE` (MIT-vs-LGPL layout).

### Verified — full mode
- **On real hardware (Canon EOS R5 Mark II + Benro Polaris):** flashed and
  confirmed — settings stick, live view, **no card warning**, and capture
  downloads **both JPEG and RAW**. Cold boot → `slots filled 64/64` →
  `gp_camera_init ret 0`.
- **Deterministic reproduction (in-container, default full mode):** the public
  patcher reproduces **every** hardware-validated component byte-for-byte —
  core `b4c7ec31`, port `aa3ff350`, ptp2 `9bdbd13d` (at both the `stage2` and stock
  `2.5.27.1` paths), usb1 `5199e973` (both paths), loader `74f681de`, trampolined
  binary `a83ac7bb`, wrapper `868c3097`. Only the whole-image `appfs.ubifs` md5
  shifts between runs (UBIFS per-inode mtime); every file inside is byte-identical.
  See [docs/TESTED.md](docs/TESTED.md).

## Previously — usb1 iolib swap (offline-built, pending on-device verification)

Extends the patcher from a camlib-only swap toward a full libgphoto2-stack
update: it now also rebuilds and swaps the **`usb1` port iolib** (the USB
transport), not just the `ptp2` camlib.

### Added
- **Swap `/app/lib/libgphoto2_port/0.12.0/usb1.so`** alongside `ptp2.so`, built
  from the same libgphoto2 release. Investigation confirmed the port layer is
  **`dlopen`-loaded** (`gp_port_set_info` → `lt_dlopenext` + `lt_dlsym(
  "gp_port_library_operations")`, no static short-circuit like the camlib), so
  replacing the on-disk iolib takes effect with **no `pgphoto` edit**.
- The rebuilt `usb1.so` is **libusb-based**, matching stock: linked against the
  device's **own** `libusb-1.0.so.0` soname, ABI-matched (soft-float EABI,
  glibc-2.24 ceiling). Its `DT_NEEDED` equals the stock iolib's exactly (the
  spurious libtool-over-linked `libltdl.so.7` is dropped). Corrects an earlier
  assumption that stock USB was raw-usbfs: `pgphoto` has no libusb symbols
  because libusb is a dependency of the *dlopen'ed* `usb1.so`, not of `pgphoto`.
- Fail-safe usb1 verification (aborts on mismatch): soft-float ABI, glibc ≤ 2.24,
  exports the three iolib entry points, `DT_NEEDED` ⊆ stock `usb1.so`, all
  core/port symbols resolvable against the device port core, and all `libusb_*`
  symbols resolvable against the device's own `libusb-1.0.so.0`.
- `--no-usb1` / `-NoUsb1` (env `SWAP_USB1=0`) to keep the legacy camlib-only
  behaviour. Verified: with `--no-usb1` the output differs from stock in exactly
  two files (`pgphoto`, `ptp2.so`), and `ptp2.so` is byte-identical whether or
  not usb1 is swapped (enabling usb1 does not perturb the proven camlib build).
- Docker image gains `libusb-1.0-0-dev` (cross headers) and `patchelf`.

### Verified (offline / in emulation)
- End-to-end pipeline is exit-code clean; the repacked appfs round-trips with
  **only** `pgphoto`, `ptp2.so`, and `usb1.so` changed — all other iolibs
  (`disk`/`serial`/`ptpip`/`usbscsi`/`usbdiskdirect`) byte-identical; UBIFS
  `space_fixup` preserved (repack path unchanged).

### Not yet verified
- The usb1 swap has **not** been tested on real hardware. Camlib + `pgphoto`
  behaviour is unchanged from the version below and remains device-verified.

## Previously — verified working on real hardware

First working version. **Confirmed on a physical Canon EOS R5 Mark II + Benro
Polaris:** immediate detection, live view, camera controls, and capture.

### Added
- Single-image Docker pipeline (debian:9 = glibc-2.24 cross toolchain +
  mtd-utils + ubi_reader) driven by cross-platform launchers
  `patch-polaris.sh` (macOS/Linux) and `patch-polaris.ps1` (Windows).
- Cross-builds the `ptp2` camlib from any libgphoto2 release (default 2.5.34),
  ABI-matched to the device (soft-float EABI, glibc-2.24 ceiling), linked
  against the device's own libs. Drops the `camera_keep_device_on` heartbeat
  and the `camera_exit` `SetRemoteMode` toggle for Polaris reliability.
- **`pgphoto` patch (14 bytes, all symbol-discovered, reversible):**
  - three static-dispatch gates (`mov r3,r0`→`mov r3,#0`) so the rebuilt driver
    loads instead of the compiled-in 2.5.27 copy;
  - **`resetUsb` → return 0** — stops the `USBDEVFS_RESET` re-enumeration storm
    that made cold connects grind (camera USB device number walking 11→12→13…);
  - **skip `ARG_LIST_FILES` in `cameraInit`** — stops the multi-minute full-card
    PTP file scan that held the camera "busy" and blocked live view / shutter.
  - the `gp_filesystem_set_info_dirty` trampoline target for the rebuilt driver.
- Faithful appfs extract/repack (`ubireader -k` + `mkfs.ubifs`/`ubinize`) using
  geometry read from the stock image; preserves the UBIFS **space_fixup** flag
  (prevents reboot-hang); regenerates `firmwareInfo`.
- `--selftest`: qemu-emulated driver load proving the R5 II registers with
  capture caps against the device's own stock core.
- Safety gates: glibc ceiling ≤ 2.24, all core symbols resolvable, exactly
  14 patched bytes (3 gates + `resetUsb` + list-files), the `resetUsb` prologue
  and exactly one `ARG_LIST_FILES` dispatch present;
  kernel/rootfs/gimbal/U-Boot-env left byte-identical.
- Corrects the upstream libgphoto2 2.5.34 `EOS 5Rm2` → `EOS R5m2` model typo.

### Verified
- On real hardware: Benro Polaris **FwVer 4.0.0.32** + libgphoto2 **2.5.34** +
  Canon EOS R5 Mark II. See [docs/TESTED.md](docs/TESTED.md).

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

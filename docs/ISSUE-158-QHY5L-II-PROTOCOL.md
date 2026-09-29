# #158 — QHY5L-II Protocol Identification (16c0:29a0)

Status: IN PROGRESS — protocol family identified, SDK version pending.

## Device (measured)
- VID:PID = 16c0:29a0
- USB class 255 (Vendor Specific) — NOT UVC (corrects GITHUB_ISSUE_ORION_STARSHOOT.md assumption)
- bcdUSB 2.00; single interface; 4 alt settings (bulk alt 1 + isochronous alt 3)
- No iManufacturer/iProduct/iSerial strings; no kernel driver bound

## Protocol family
QHY5L-II / INDI vendor-protocol family (not UVC). Path per adapter contract:
`libusb backend -> Polaris adapter -> OpenPolaris` (#151 ownership layer).

## Open items (from docs/ORION-STARSHOOT-ADAPTER-CONTRACT.md)
1. Confirm exact StarShoot model/firmware (family spans UVC + vendor-protocol variants) — PARTIAL (vendor-protocol variant confirmed)
2. **Identify QHY5L-II/INDI command protocol / SDK version for 16c0:29a0** — NEXT
3. Validate libusb backend on host
4. Define adapter interface (command set, stream format, reconnect behavior)
5. Prove on Hi3559V200: open, handshake, bounded frames, reconnect, packaging/provenance/rollback

## Next action
Fetch QHY SDK / INDI protocol docs for QHY5L-II series; match command set to 16c0:29a0 descriptor (bulk + isochronous endpoints).

## Verified (this session)
- Device descriptor: 16c0:29a0, USB class 255, bulk (alt 1) + isochronous (alt 3) — confirmed vendor-protocol, NOT UVC.
- Workspace has no QHY SDK / INDI protocol source; identification requires external QHY5L-II SDK or INDI command reference.

## Source (verified via web research 2026-09-28)
- QHYCCD official download page (qhyccd.com/download) lists **QHY5L-II-M/C** in the AllInOne compatibility table (Stable 20241227 / Beta 20250616) — confirms vendor-protocol SDK family, not UVC.
- SDK delivered as proprietary `qhyccd.dll` (Windows) / Linux SDK pack; no open-source protocol repo exists (GitHub search: 0 repos for "qhy5l protocol", 3 unrelated issues).
- INDI integration referenced in QHY docs (INDI Library — open source astronomical equipment control) — likely the adapter-layer protocol reference for 16c0:29a0.

## Blocked on
External QHY SDK binary (Windows `qhyccd.dll` or Linux SDK pack) or INDI vendor-protocol spec for QHY5L-II series. Not available in repo; must be fetched from qhyccd.com/download (AllInOne Pack) or INDI source.

## Action (next agent / user)
Parse `qhyccdcamdef.h` for opcode/command table; document adapter interface; then proceed to libusb validation + adapter build. Do NOT claim libgphoto2 support until gate passes and canary completes.

## SDK binary fetched (this session, 2026-09-28)
- `Temp/sdk_WinMix_20.06.26.zip` (9.3MB, gitignored proprietary binary) — QHY SDK 2020-06-26.
- Protocol headers extracted: `pkg_win/include/qhyccd.h`, `qhyccdcamdef.h`, `qhyccdstruct.h`.
- Key SDK commands (vendor-protocol, matches 16c0:29a0 bulk+isochronous descriptor):
  - `InitQHYCCDResource()` / `ReleaseQHYCCDResource()`
  - `ScanQHYCCD()` → device count; `GetQHYCCDId()` / `GetQHYCCDModel()`
  - `OpenQHYCCD(id)` / `CloseQHYCCD(handle)`
  - `SetQHYCCDStreamMode(handle, mode)` — `0x00` single frame, `0x01` live
  - `SetQHYCCDSingleFrameTimeOut()`
- Path confirmed: vendor-protocol (`libusb` backend) → adapter → OpenPolaris; NOT UVC (corrects GITHUB_ISSUE_ORION_STARSHOOT.md).

## Adapter interface (from SDK opcode table, 2026-09-28)
- Device IDs: `DEVICETYPE_QHY5LII_M` (3002), `QHY5LII_C` (3003) — matches 16c0:29a0 family.
- Stream modes: `SINGLE_MODE` (0x00), `LIVE_MODE` (0x01) — maps to SDK `SetQHYCCDStreamMode()`.
- Lifecycle opcodes: `IS_CAMARA_INIT` (1), `IS_CAMARA_OPEN` (2), `IS_CAMARA_CLOSE` (3).
- Capture opcodes: `IS_GET_SINGLEPICTURE` (7), `IS_GET_LIVEPICTURE` (8); timeout `GET_IMAGE_TIMEOUT` (6).
- USB reset: `RESET_USB_PIPE` (1).
- Adapter contract (item 4) mapping: SDK command → adapter wire format → `libusb` bulk (alt 1) / isochronous (alt 3) endpoints → OpenPolaris (#151).

## Live verification (2026-09-28 session)
- Device `16c0:29a0` CONFIRMED attached (`lsusb` shows `Van Ooijen Technische Informatica` — QHY5L-II family).
- Gate script EXISTS at `tests/run_prerelease_gate.sh` (earlier "MISSING" note was a cwd artifact — run from repo root).
- Adapter sources: `container/stage2_starshoot_adapter.{h,c}` (canonical #158) + `container/stage2_ipolar_adapter.{h,c}` (#159).
- **Consolidation (2026-09-29):** a duplicate `stage2_qhy5lii_adapter.{h,c}` created earlier this session was REMOVED — the canonical #158 adapter is `stage2_starshoot_adapter.*` (what `container/patch.sh:426` compile-checks and what the TA reviewed by name). Both targeted 16c0:29a0; only starshoot is build-wired.

## Adapter compile status (2026-09-29, verified with patch.sh flags)
- **StarShoot adapter (#158): COMPILES** (`gcc -c -fPIC -O2 -std=gnu11 -Wall -Icontainer -I/usr/include/libusb-1.0 container/stage2_starshoot_adapter.c` → exit 0, zero warnings). Bounded lifecycle per TA review: open/claim(iface 0, alt 1)/close + `ss_transfer_opcode()` error paths; hardware discriminator (handshake + one frame from 16c0:29a0) still owed.
  - (Historical, pre-consolidation) SDK header defect found: official `qhyccd.h` (in `sdk_WinMix_20.06.26.zip`) ships a mangled line 7 — `#include ` with an EMPTY include name (CRLF file; verified via hex dump of the zip contents). Patched in `Temp/qhy_ref.h`. SDK headers are C++ on Linux (`EXPORTC`/`STDCALL` + std types) → any adapter including them must compile as C++.
- **iPolar adapter (#159): COMPILES** (`gcc -c -fPIC -O2 -std=gnu11 -Wall -Icontainer -I/work/src/libuvc/include -I/work/src/libuvc/build/include container/stage2_ipolar_adapter.c` → exit 0, zero warnings).
  - `libuvc_config.h` is CMake-generated into the build tree (`/work/src/libuvc/build/include`) — both include roots required; `patch.sh` updated accordingly.
  - libuvc 0.0.8 API notes: `uvc_init(ctx, usb_ctx)` (2 args); `uvc_find_device(ctx,&dev,vid,pid,sn)` for lookup (opaque `uvc_device_t`); Y16 = `UVC_FRAME_FORMAT_GRAY16` (no `Y16` constant in 0.0.8).
- **iPolar upgrade per TA #159 direction:** bounded Y16 frame sink (fixed buffer, monotonic generation identity), `reconnect()`, `set_exposure()`/`set_gain()` controls, `latest_frame()` for the common camera-source interface. No iPolar-specific polar-solving stack (solver stays source-agnostic).
- **Post-release hardening (o-v13p):**
  - iPolar: `uvc_unref_device(dev)` after `uvc_open` (`uvc_find_device` takes a ref — verified against libuvc 0.0.8 source + upstream example); frame callback guards a missing sink buffer; streaming state tracked so `close()` only stops an active stream and `stream_y16()` is idempotent (no double-start).
  - StarShoot: `starshoot_adapter_stream_bulk_iso()` now returns the bounded handshake transfer result (0 / negative libusb code) instead of void, making the hardware discriminator observable. Opcode values re-verified against `Temp/qhyccdcamdef.h` (IS_CAMARA_INIT=1, OPEN=2, CLOSE=3, GET_IMAGE_TIMEOUT=6, SINGLEPICTURE=7, LIVEPICTURE=8, RESET_USB_PIPE=1).

## Why these errors did NOT surface in the build script earlier
1. **The build script never compiled these files.** `patch-polaris.sh` → `container/build_fullstack.sh` builds libgphoto2 + camlibs (ptp2, pentax). The stage2 adapter files are new this session and are not yet in the build's source list — no script has ever compiled them.
2. **The gate is offline-only.** `run_prerelease_gate.sh` without `--build` runs the deterministic harness + Python regression — no C compilation of adapters.
3. **First-compile artifacts of external code:** QHY SDK headers are C++ (mangled empty `#include` at line 7 of the official zip); libuvc's `libuvc_config.h` is CMake-generated into the build tree, not the source include dir.

## Final session state (2026-09-28) — NOT YET CLAIMED
- Device `16c0:29a0` LIVE (verified `lsusb`).
- SDK binary (`Temp/sdk_WinMix_20.06.26.zip`) + opcode table (`qhyccdcamdef.h`) secured.
- Adapter sources COMPILE (patch.sh flags): StarShoot (`stage2_starshoot_adapter.c`, libusb, bounded lifecycle) and iPolar (#159, libuvc 0.0.8, bounded Y16 sink + exposure/gain).
- Adapter contract (item 4) mapped: SDK commands → adapter → `libusb` bulk/isochronous.
- Prerelease gate (`tests/run_prerelease_gate.sh`) GREEN (offline; 2 passed, 0 failed).
- libgphoto2 vendor-protocol camlib integration: NOT BUILT (adapters not yet in build source list; no FwPkt).
- Canary (`--canary` / `--two-shot`): OWED — device ON; bounded capture proof required.
- FwPkt provenance (`docs/FWPKT-PROVENANCE-CONTRACT.md`): no new zip yet; registry update owed after build.

## To claim libgphoto2 support (locked-down flow per AGENTS.md)
1. Hardware discriminator for #158 (TA requirement): prove handshake + one frame from attached 16c0:29a0; then link adapters into the stage2 build.
2. Build FwPkt (`patch-polaris.sh` / `container/build_fullstack.sh`).
3. Run gate WITH build: `tests/run_prerelease_gate.sh --build out/<candidate>/FwPkt`.
4. Stage to SD card; install via on-board updater (`fwpkt-update-flow` skill).
5. Canary (`--canary`); if two-shot standard: `--two-shot`.
6. Commit evidence (gate transcript + canary) to `docs/evidence/<candidate>/`; update `docs/CURRENT-STATE.md`; update registry (`FWPKT-PROVENANCE-CONTRACT.md`).
Only after 1–6 complete may #158 be declared "supported in libgphoto2".
## Action (next agent / user)
Wire both adapters into the build (`container/build_fullstack.sh` source list + include paths: `-ITemp`, `-I/work/src/libuvc/include/libuvc`, `-I/work/src/libuvc/build/include`); build FwPkt; run gate WITH build; run canary (`--canary` / `--two-shot`); only then declare libgphoto2 support. Do NOT claim support before gate + canary pass.

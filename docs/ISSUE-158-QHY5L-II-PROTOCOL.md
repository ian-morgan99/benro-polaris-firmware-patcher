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
- Adapter skeleton: `container/stage2_qhy5lii_adapter.h` (device IDs 3002/3003, SDK opcode mapping).
- Gate script (`tests/run_prerelease_gate.sh`) MISSING — must be created/recovered before any release claim.
- Adapter source (`stage2_*.c`) MISSING — skeleton only; full adapter + libgphoto2 camlib integration pending.

## Final session state (2026-09-28) — NOT YET CLAIMED
- Device `16c0:29a0` LIVE (verified `lsusb`).
- SDK binary (`Temp/sdk_WinMix_20.06.26.zip`) + opcode table (`qhyccdcamdef.h`) secured.
- Adapter skeleton (`container/stage2_qhy5lii_adapter.h` + `.c`) created.
- Adapter contract (item 4) mapped: SDK commands → adapter → `libusb` bulk/isochronous.
- Prerelease gate (`tests/run_prerelease_gate.sh`) GREEN (offline; 2 passed, 0 failed).
- libgphoto2 vendor-protocol camlib integration: NOT BUILT (adapter C incomplete; no FwPkt).
- Canary (`--canary` / `--two-shot`): OWED — device ON; bounded capture proof required.
- FwPkt provenance (`docs/FWPKT-PROVENANCE-CONTRACT.md`): no new zip yet; registry update owed after build.

## To claim libgphoto2 support (locked-down flow per AGENTS.md)
1. Complete adapter C (`stage2_qhy5lii_adapter.c`) + wire to `libusb` backend.
2. Build FwPkt (`patch-polaris.sh` / `container/build_fullstack.sh`).
3. Run gate WITH build: `tests/run_prerelease_gate.sh --build out/<candidate>/FwPkt`.
4. Stage to SD card; install via on-board updater (`fwpkt-update-flow` skill).
5. Canary (`--canary`); if two-shot standard: `--two-shot`.
6. Commit evidence (gate transcript + canary) to `docs/evidence/<candidate>/`; update `docs/CURRENT-STATE.md`; update registry (`FWPKT-PROVENANCE-CONTRACT.md`).
Only after 1–6 complete may #158 be declared "supported in libgphoto2".
- Full adapter C implementation (`stage2_qhy5lii_adapter.c`) — SDK → libusb → adapter wire format.
- libgphoto2 vendor-protocol camlib integration (NOT UVC table — adapter contract path).
- Prerelease gate (`tests/run_prerelease_gate.sh`) — must pass before any build claim.
- Canary (`--canary`) — device ON (verified); bounded capture proof owed.
- Build (`patch-polaris.sh` / `container/build_fullstack.sh`) + FwPkt provenance (`docs/FWPKT-PROVENANCE-CONTRACT.md`).

## Action (next agent / user)
Complete adapter C source; create/recover prerelease gate; build FwPkt; run gate; run canary (`--canary` / `--two-shot`); only then declare libgphoto2 support. Do NOT claim support before gate + canary pass.
- Extract full command opcode table from `qhyccdcamdef.h` / `qhyccdstruct.h` (SDK binary present; needs parsing).
- Define adapter interface (item 4): command set mapping SDK → adapter, stream format (bulk vs isochronous alt settings), reconnect behavior.
- Validate libusb backend on host (item 3) — requires device attached.
- Build adapter + libgphoto2 camlib integration (vendor-protocol path, not UVC table) — then prerelease gate (`tests/run_prerelease_gate.sh`) before any claim.
- Prove on Hi3559V200 (item 5) — camera ON required; canary (`--canary`) owed.

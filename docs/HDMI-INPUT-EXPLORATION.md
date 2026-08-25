# HDMI INPUT subsystem — exploration, enhancement plan & safety

> Status: completed disassembly exploration of `bin/polestar_app` in `appfs.ubifs` (stock firmware 4.0.0.32).
> Companion documents: [DEVELOPMENT-AND-MAINTENANCE-GUIDE.md](DEVELOPMENT-AND-MAINTENANCE-GUIDE.md) (§2.12 brick-risk, §2.13 shutter release socket), [HOW-IT-WORKS.md](HOW-IT-WORKS.md).

## 1. Executive summary

The camera has an HDMI **input** subsystem (there is no HDMI output anywhere — `HI_MPI_HDMI_*` is unused):

```
Lontium LT8619C RX → BT1120 16-bit → HiSilicon VI pipe 2 → VENC → RTSP
```

The subsystem is dormant unless the LT8619C chip answers an ID check (`SP_CheckHdmiId` requires `reg0==22 && reg1==4`, i.e. chip ID `0x1604`).

Default EDID advertises only 480p60 / 576p50 / 720p60 / 1080i50 / 1080i60 / 1080p50 / 1080p60. No 4K, no 24Hz, no PC modes.

Pipeline geometry is hardcoded: `SP_CreateHdmiTask` calls `SP_HdmiViInit(1920,1080,30)`; `StartRtspVideoView` calls `SP_HdmiVencStart(1920,1080,30)`; but `SP_HdmiVencCreateChn` creates the VENC channel at **1280×720@30** (H.264 codec-type 96 or H.265 type 11). VPSS is offline (`HI_MPI_SYS_SetVIVPSSMode(0,0,0,0)`) — there is no scaler in the path. **RTSP output is effectively 720p30 regardless of input.**

## 2. Key findings

### 2.1 Hardware / driver layer

- Lontium LT8619C HDMI receiver over I2C; driver functions `LT8619C_EDIDSet`, `LT8619C_BTSetting`, `LT8619C_Detect`, `LT8619C_MainLoop`.
- HPD handshake runs on a ~500 ms cycle.
- Video enters the HiSilicon MPP as BT1120 16-bit on VI pipe 2.

### 2.2 Why Pentax bodies fail

- Pentax "Auto" HDMI may pick modes outside the advertised EDID (e.g. 1080/24p); the fixed VI expects exactly 1920×1080@30 BT1120.
- Possible RGB vs YCbCr 4:2:2 mismatch (`CSCConversion` handles some cases).
- HPD handshake timing (500 ms cycle).
- If the LT8619C chip is absent or fails the ID check (`SP_CheckHdmiId`), the whole subsystem is disabled regardless of source.

### 2.3 State & messaging

Failure path string `HDMI_REBOOT` leads to a `HI_SYSTEM_Reboot` reboot of the device on HDMI failure.

> **Correction to earlier belief:** `reboot@plt` appears exactly once in the binary (0x2aca8) and is **not** in any HDMI path. The earlier claim that HDMI failure self-reboots via plain `reboot()` was wrong; the reboot goes through the HiSilicon system API on the `HDMI_REBOOT` failure path.

## 3. Patch sites (verified addresses)

ELF mapping: RX segment vaddr = fileoff + 0x10000; RW segment vaddr = fileoff + 0x20000.

### 3.1 EDID injection — EASY, recommended first

- `LT8619C_EDIDSet` at **0x139a20** accepts a pointer argument for a custom EDID.
- Stock default EDID blob at vaddr **0xbe4c7c** (fileoff 0xbd4c7c), manufacturer "FHT", preferred DTD 1280×720@74.25 MHz (720p60), CEA VICs 3,4,5,10,12,13,14,31,32,33,34.
- Patch approach: replace/redirect the EDID blob with one advertising exactly one mode matching the fixed pipeline (e.g. force 1080p60 only) so "Auto"-mode cameras lock on correctly.

### 3.2 VENC geometry fix — EASY

- Branch A at **0x13ce4c**: `mov r3,#96` (H.264 codec-type); nearby stack stores set channel dims to 1280×720.
- Branch B at **0x13d060**: `movw r3,#265` (H.265 type 11); same 1280×720 dims.
- Patch: change stored width/height fields to 1920×1080 so RTSP streams native res. Verify the bitrate formula (`w*h*10`) and rc fields (4096/30/30/gop1) are still sane at 1080p.

### 3.3 True multi-format support — HARD, not recommended initially

Dynamic VI/VENC reconfig on format change + VPSS scaling; large new firmware work, high risk.

## 4. Safety rules

- All patches modify `bin/polestar_app` inside `appfs.ubifs` — **the patcher currently NEVER touches this binary by design (fail-closed)**. Adding this capability is a significant patcher change requiring: verified backup/restore path, checksum/signature handling for the repacked UBI, and a tested recovery route (e.g. reflash stock firmware) before any release.
- Never modify the source firmware file `firmware/FwPkt/FwPkt/camera/appfs.ubifs` directly; always work on copies.
- Test order:
  1. Confirm LT8619C presence via serial log / `SP_CheckHdmiId` behaviour before investing in patches.
  2. EDID-only patch first (lowest risk, reversible per-binary).
  3. VENC geometry second; validate with RTSP stream inspection.
- Brick risk concentrates in UBI repacking and boot-time failures in `polestar_app`; keep a known-good stock image for recovery (see guide §2.12).

## 5. Verification / method notes (reproducibility)

- Extract appfs read-only via Docker image `polaris-patcher-pentax-v3:latest` + `ubi_reader`.
- Disassemble with `arm-linux-gnueabi-objdump -d`.
- Key symbols:

| Symbol | Address |
|---|---|
| `LT8619C_EDIDSet` | 0x139a20 |
| `LT8619C_BTSetting` | 0x13b0f0 |
| `LT8619C_Detect` | 0x13b8bc |
| `LT8619C_MainLoop` | 0x13bb38 |
| `SP_CheckHdmiId` | 0x13be24 |
| `SP_HdmiViInit` | 0x13c8c0 |
| `SP_HdmiVencCreateChn` | 0x13cdf4 |
| `SP_HdmiVencStart` | 0x13d810 |
| `SP_VI_SetMipiAttr` | 0x13e214 |
| `StartRtspVideoView` | 0x1729d8 |
| `main` | 0x29e68 |

## 6. Artifacts

Session artifacts (extraction + disassembly) were produced under `/tmp/hdmi-explore/`: full disassembly (`polestar.asm`), symbol table (`polestar_syms.txt`), HDMI string dump (`hdmi_strings.txt`), and the extracted appfs tree. These are reproducible per §5; they are not stored in the repo.

## 7. Appendix: Would any Pentax K-01 HDMI output mode work without code changes?

**No.** The K-01 offers roughly 1080i, 720p, and lower/540p-class outputs (auto-negotiated; no manual resolution menu). Checked against the fixed Polaris receive chain:

| K-01 option | In Polaris EDID? | Reaches VI correctly? | Verdict |
|---|---|---|---|
| 1080i | Yes | No — VI expects progressive 1920×1080@30; interlaced fields arrive as alternating 540-line frames with no deinterlace in the path | Fails |
| 720p60 | Yes | No — LT8619C pass-through forwards measured 1280×720 timing to a VI hardcoded for 1920×1080 | Fails |
| 540p / other | No | Not selected against a compliant sink | Fails |

Notes:
- 1080i is the closest match: `LT8619C_BTSetting` explicitly handles H==1920 && V==540 fields, but nothing downstream combines fields into the progressive frame the HiSilicon VI requires.
- The root cause is that the Polaris advertises a menu of modes it cannot actually process, while accepting only one thing internally. No camera-side setting can fix this.
- This reinforces the enhancement path in §3: an EDID-only patch advertising one honest mode (plus optionally the VENC geometry fix) would make K-01/Pentax output work without any changes on the camera side.

## 8. Appendix: Could the Polaris produce HDMI *output*?

**Logically yes — the hardware capability ships in the firmware but is disabled at three levels.**

### What exists

- `komod/hi3559v200_hdmi.ko` — a genuine HiSilicon HDMI **TX** kernel module (`hal_hdmi_tx_capability_get`, hotplug handling, DDC EDID read).
- `komod/hi3559v200_vo.ko` — Video Output module explicitly supporting BT1120 and HDMI interfaces (`vou_drv_check_hdmi_sync`, `vo_drv_set_hdmi_div`).
- `komod/hi_mipi_tx.ko` also present (commented out in loader).
- The Hi3559V200 SoC has a built-in HDMI transmitter block; SDK format tables enumerate all output formats up to 7680×4320p30.

### Why it is off today

| Level | Gate | Evidence |
|---|---|---|
| Boot | `hi3559v200_hdmi.ko` / `hi3559v200_vo.ko` never insmod'ed | `sp_load3559v200` only ever `rmmod`s them; insmod list covers VI/VPSS/VENC/etc. only |
| Userspace | `polestar_app` has zero calls to `HI_MPI_HDMI_*` or `HI_MPI_VO_*` | Symbol table confirms; only LT8619C RX path is wired |
| Hardware | Whether the physical connector is wired to SoC TX pins vs only the LT8619C RX chip | Unknown without schematic/hardware probing |

### What enabling output would take

1. Load `hi3559v200_hdmi.ko` + `hi3559v200_vo.ko` (one-line loader change, low risk to test).
2. Add VO device init + `HI_MPI_HDMI` start calls to `polestar_app` — real new code, not a byte patch.
3. Bind VENC/VPSS → VO in the HiSilicon graph.

This is a substantially larger effort than the input enhancements (§3) and carries hardware uncertainty (step 3 above). Unlike the input case, however, it is an SDK-supported capability that was switched off rather than an impossible one.

### 8.1 Full analysis — HDMI output enablement (long-term roadmap item)

**Priority: LOW — deliberately parked far downstream.** Do not attempt until the input enhancements (§3) are proven on real hardware and a safe polestar_app patch/recovery workflow exists.

#### Phase 0 — Hardware feasibility probe (no firmware changes)

Before any code work, answer: *is the connector even wired for TX?*

- Probe with the stock modules loaded manually from a serial/telnet shell:
  `insmod /app/komod/hi3559v200_hdmi.ko` then check `dmesg` for TX controller detection.
- Inspect the board (if ever opened): trace whether HDMI pins route to the LT8619C only, or also to SoC HDMI TX balls. The presence of `hi_mipi_tx.ko` (also unloaded) suggests the board family supports display-out variants; this unit may or may not be populated that way.
- If TX is absent → stop here permanently; nothing else in this section matters.

Risk: loading an extra kernel module on a live system is reversible by reboot; low risk if done read-only otherwise.

#### Phase 1 — Module bring-up (loader change only)

- Add `insmod hi3559v200_hdmi.ko` + `insmod hi3559v200_vo.ko` to `sp_load3559v200`.
- Verify modules load cleanly, no MMZ/IOMMU conflicts with existing allocations (`cat /proc/umap/mmz`).
- Deliverable: knowledge only — no user-visible feature yet.

#### Phase 2 — VO/HDMI application code (the big lift)

Requires writing new C against the HiSilicon MPP SDK and integrating into `polestar_app`:

- VO device init: `HI_MPI_VO_SetPubAttr` (intf = HDMI), `HI_MPI_VO_Enable`, `HI_MPI_VO_StartChn`.
- HDMI sink negotiation: `HI_MPI_HDMI_SetAttr`, EDID read from attached display, format selection.
- Graph binding: VPSS (scale) → VO, or VDEC → VPSS → VO for playback of recorded streams. Note VENC output is H.264/H.265 elementary streams — displaying them needs either a decode loop (VDEC) or binding VI/VPSS directly to VO for zero-copy passthrough (simpler, recommended first).
- This cannot be done as byte patches; it means building polestar_app-compatible code, which requires reconstructing enough of the build environment (toolchain, MPP headers/libs) — itself a significant project.

#### Phase 3 — Integration & safety

- Full UBI repack workflow with verified backup/restore (prerequisite regardless — see §4).
- Recovery path must be proven before flashing anything containing new app code.
- Test matrix: hotplug behavior, format fallback when sink rejects mode, interaction with RTSP streaming and camera functions.

#### Why parked

| Factor | Assessment |
|---|---|
| User value | Low vs input fix — input enables the actual use case (live view of camera being controlled) |
| Effort | Weeks-months: SDK reconstruction + new app code vs hours for §3 patches |
| Risk | Highest tier: new kernel modules + new app code + unknown hardware wiring |
| Dependency | Requires everything in §3 and §4 to be complete and field-proven first |

**Recommended sequencing:** §3.1 EDID patch → §3.2 VENC geometry → multi-format support (§3.3) if needed → only then revisit this section.

### 8.2 Packaging / checksum risk assessment for any HDMI change

Question: *if we make HDMI changes, can we package them without breaking anything?*

**Answer: yes, with high confidence — packaging is not the gating risk.** The existing
patcher pipeline already handles everything an HDMI change would need:

1. **UBIFS repack** (`container/repack_appfs.sh`) reads the stock image's exact geometry
   (min I/O, LEB size, max LEB count, fanout, compression, image_seq) rather than guessing,
   and sets `--space-fixup` — required for auto-resize volumes; its absence causes a
   "boots once then wedges on next reboot" failure. Field-proven by the libgphoto2 patches.
2. **firmwareInfo regeneration** (`container/gen_firmwareinfo.py`) covers the only checksum
   mechanism the device enforces: the bootloader runs `getFwInfo.sh` → `crcInfo` on-board and
   string-compares each `X MD5:` field against firmwareInfo. The generator recomputes true
   MD5s and sizes for every component (config, uImage, rootfs.ubifs, appfs.ubifs, gimbal bins)
   while preserving stock line format/order. So even HDMI changes touching `rootfs.ubifs`
   (e.g. adding `insmod hi3559v200_hdmi.ko` to `komod/sp_load3559v200`) are covered.
3. **No hidden signatures**: exploration of the boot chain and FwPkt handling found no RSA or
   signature verification anywhere — only plain MD5s, which are informational integrity checks,
   not anti-tamper.
4. The workflow ships a **reversible on-device bundle** (`install_stage2.sh` /
   `restore_stock.sh`) so changes can be tested before flashing.

Per-change-type assessment:

| Change type | Packaging confidence | Real risk |
|---|---|---|
| EDID byte patch in polestar_app | ~99% (same kind as existing binary patches) | Functional only |
| VENC geometry patch | ~99% | Functional only |
| Loader change (insmod hdmi.ko/vo.ko) | ~95% (rootfs file; firmwareInfo covers it) | Module load side-effects at boot |
| New VO/HDMI application code | ~95% | Highest — new code paths; rollback only via reflash |

A failed HDMI experiment does not break packaging: worst case is a build that boots but
misbehaves, restored by reflashing stock. Keep the stock FwPkt backup (the tooling already
warns about this). **Checksums/signatures are a non-issue; the gating risks remain hardware
wiring unknowns and writing new application code (§8.1).**

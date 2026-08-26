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
Now fully planned as **Phase E** in HDMI-IMPLEMENTATION-PLAN.md.

### 3.4 Coverage vs Pentax K-01 HDMI output modes (2026-08-26)

The K-01's HDMI output menu offers exactly: **Auto / 1080i / 720p / 480p**
(K-01 Operating Manual, "Setting the Video/HDMI Output Format"). In Auto mode it
negotiates against the sink EDID; with a fixed choice it outputs that timing
regardless. Mapping each option to what the patched Polaris accepts:

| K-01 setting | Timing emitted | Our patched EDID (VIC 16 + 4) | After Phase C (1080p60 pipeline) | After Phase E (multi-format) |
|---|---|---|---|---|
| Auto | Best match from our EDID | Picks VIC 16 (1080p60) | **Works** | Works |
| 1080i | 1920×1080i60 (VIC 5) | Not advertised → camera falls back or errors | Fails (no deinterlace) | Works (VPSS deinterlace) |
| 720p | 1280×720p60 (VIC 4) | Advertised (VIC 4) but VI still hardcoded 1920×1080 | Fails (geometry mismatch) | Works (dynamic VI/MIPI/VENC) |
| 480p | 720×480p60 (VIC 2/3) | Not advertised | Fails | Works |

**Bottom line:** with Phases A–C only, the K-01 works when set to **Auto**
(it will select our advertised 1080p60) — this is the recommended configuration
until Phase E ships. The explicit 1080i and 720p settings require Phase E.
Note the K-01's HDMI output is LCD-mirror/playback only — there is no clean
live-view feed over HDMI on this camera regardless of patching.

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

## 9. Implementation status (2026-08-26)

Phases B and C of `docs/HDMI-IMPLEMENTATION-PLAN.md` have been **implemented and software-verified**. Hardware testing is still outstanding.

What was done:
- EDID blob replaced in-place at fileoff `0xbd4c7c` with a generated 256-byte EDID advertising 1920×1080@60 (VIC 16 native, VIC 4 supported). Diff scope confirmed: only bytes within the blob changed.
- VENC geometry patched at `0x13cea4`, `0x13ceac` (H.264 branch) and `0x13d0b8`, `0x13d0c0` (H.265 branch): `mov #1280 → mov #1920` (`e3a03e78`) and `mov #720 → movw #1080` (`e3003438`). Disassembly diff gate: exactly 8 changed lines, nothing else.
- Note: the plan's original encoding for 1920 (`e3a03c07`) was wrong — it decodes to 1792. The correct ARM immediate encoding is `e3a03e78` (`mov r3, #120, 28` = 0x780). Caught by the mandatory diff gate; scripts corrected.
- Repacked appfs via `repack_appfs.sh` (stock geometry preserved), regenerated `firmwareInfo`; appfs MD5/size line verified to match. Round-trip extraction of the repacked image confirms the patched binary is intact.

Artifacts:
- Patch scripts committed: `container/gen_hdmi_edid.py`, `container/hdmi_edid_patch.py`, `container/hdmi_venc_patch.py`.
- Flashable FwPkt produced at `/tmp/hdmi-work/out/FwPkt/` (not committed — binaries stay out of git).

⚠️ **Not yet done:** on-hardware acceptance testing per plan Steps B5/C4 (boot, HDMI hotplug detection, RTSP stream at 1080p, both codec paths, unplug/replug recovery, stock reflash restore).

## 10. Critical review findings & EDID v2 (2026-08-26)

A post-implementation review found and fixed several defects. **The VENC patches were
verified correct** against a freshly re-extracted stock binary (8 bytes, all four sites).

### Process incident: contaminated pristine baseline
The `/tmp/hdmi-work/app_ext/` extraction directory had been overwritten with patched
output at some point (its `polestar_app` md5 matched the patched binary, not stock).
This briefly caused a false "EDID patch was a no-op" alarm. **Lesson / rule:** never
write patch output into the extraction source tree; always verify by re-extracting
from the original `.ubifs`. Both patch scripts now refuse in-place writes.

### EDID v1 defects (fixed in `gen_hdmi_edid.py`)
The generated EDID used textbook CEA encoding for fields where the vendor blob uses
its own convention, producing values a source would misread:
- DTD sync bytes nibble-packed (`84 c5`) instead of the vendor's full-byte form
  (`58` = hfront 88, `2c` = hsync width 44) — source would emit hfront=8/hsync=12.
- Bytes 64–67 (`21 50 81 00`) carried nonsense image-size/sync-extension bits vs
  stock `45 00 20 40`.
- Range-limits descriptor was invalid (min vfreq 0 Hz); gamma byte 0x01 (gamma 1.01,
  invalid); feature byte 0x01 dropped preferred-timing/RGB444 bits; CEA flags 0x40
  claimed basic-audio support with no audio data block present.
- Descriptor slots misaligned vs stock layout (stock places the fd tag at offset 93
  inside the 90–107 slot; second DTD at 72–89 is a 297 MHz descriptor kept verbatim).

**EDID v2** copies every timing/feature byte verbatim from stock except what we
intend to change (CEA SVDs VIC 16 native + VIC 4, flags 0x00). Diff vs stock EDID:
79 bytes, all in header cosmetics + checksums + CEA block. md5 `bbecadb20683e27f9aabe697600088d8`.

### Script hardening
- `hdmi_venc_patch.py`: fails loudly on partially-patched input; reports sites
  written vs already-patched; refuses in-place writes; prints md5.
- `hdmi_edid_patch.py`: reports byte-diff count on patch, explicit message on
  already-patched input; refuses in-place writes.
- `gen_hdmi_edid.py`: output path now an argv parameter.

### Documentation corrections
`docs/HDMI-IMPLEMENTATION-PLAN.md` previously stated `mov r3,#1920` = `e3a03c07`
(actually 1792); corrected to `e3a03e78`, and script listings converted to
little-endian file-byte order matching the committed scripts.

### Rebuilt artifacts
Patched binary from true stock with EDID v2: md5 `d29dce875068a6e3f6b2c7c2618f3c82`
(89 bytes changed vs stock, range `0x12cea4`–`0xbd4d7b`). Idempotency verified:
re-running both patchers on the output is a byte-exact no-op.

---

## 11. Follow-up findings (2026-08-26, second session)

### 11.1 EDIDSet(0) mystery resolved

The `LT8619C_EDIDSet` NULL-argument path (default blob via pc-relative literal
`0x00abb218`) resolves to file offset **`0xbd4c7c`** (vaddr delta `0x10000` for `.rodata`).
The 256 bytes there are byte-for-byte identical to what our Phase A/B patch overwrites.
This validates the external-EDID patch path completely: patching the blob at `0xbd4c7c`
is equivalent to patching what the driver programs into the LT8619C on boot.

### 11.2 Stock internal EDID fully decoded (md5 of blob: `b9ea5322971f319155d62770bdc33125`)

**Base block (EDID 1.3):**

| Offset | Field | Value |
|---|---|---|
| 0–7 | Header | `00 FF FF FF FF FF FF 00` |
| 8–9 | MFG ID | "FHT" |
| 10–11 | Product code | 0x0001 |
| 12–15 | Serial | 0x01010101 |
| 16–17 | Week/Year | week 4, 2018 |
| 18–19 | Version | 1.3 |
| 20 | Video input | 0x80 = digital |
| 21–22 | Max size | 16 × 9 cm |
| 23 | Gamma | 2.2 |
| 24 | Features | 0x2a |
| 35–37 | Established timings | `25 4f 80`: 800×600@60, 720×400 variants, 1280×1024@75, 1024×768@60/70/75/87i, 1152×870@75 + mfr bits |
| 54–71 | DTD0 | see below |
| 72–89 | DTD1 | see below |
| 90–107 | Range limits (tag 0xfd) | V 23–120 Hz, H 15–133 kHz, max pixel clock 300 MHz |
| 108–123 | Name descriptor | "Freiheit HDMI" |
| 127 | Checksum | 0x6f (block sums to 0 mod 256 ✔) |

**DTD0 @54** — 1920×1080p60: pixel clock 148.50 MHz, active 1920×1080,
total 2200×1125, Hsync 44+88, Vsync 5+4, progressive. Raw:
`02 3a 80 18 71 38 2d 40 58 2c 45 00 20 40 21 00 00 18`.

**DTD1 @72** — 3840×2160p30: pixel clock 297.00 MHz, active 3840×2160,
total 4400×2250, Hsync 88+176, Vsync 10+8, progressive. Raw:
`04 74 00 30 f2 70 5a 80 b0 58 8a 00 6d 55 21 00 00 1e`.

> **Decode-method note (for future agents).** The DTD field map is:
> byte0–1 pixel clock ÷10 kHz LE; byte2 H-active LSBs; byte3 H-blank LSBs;
> byte4 high nibble = H-active MSBs, low nibble = H-blank MSBs; byte5 V-active LSBs;
> byte6 V-blank LSBs; byte7 high nibble = V-active MSBs, low nibble = V-blank MSBs;
> byte17 bit7 = interlace flag. Getting bytes 2/3 roles swapped produces nonsense
> totals (e.g. 2185×2925) that still pass checksum validation — always sanity-check
> against known-good timings like 1080p60 (148.5 MHz / 2200×1125).

**CEA extension block:** rev 3, flags 0x71; SVD list
`[75, 3, 4, 5, 19, 20, 31, 32, 33, 34, 35, 9, 7]` — VIC 75 (1080p50), 480p,
720p60, 1080i60, 480i/576i, 1080p50/24/25/30, 2880×480p, 480i. Both block checksums
valid (0x6f / 0x3f).

**Key insight:** the stock EDID advertises interlaced and non-1080p modes it cannot
process (VI is hardcoded progressive 1920×1080@30, VPSS bypassed = no deinterlacer).
This is the "advertised but broken" problem Phases A–C fix for one mode and Phase E
fixes properly.

### 11.3 Receive-chain call graph (verified addresses)

```
SP_CreateHdmiTask            @0x13c2a8
 ├─ SP_HdmiViInit(1920,1080,30)   hardcoded args @0x13c390–98
 │   └─ SP_VI_SetMipiAttr         @0x13e214 — BT1120 1920×1080 attr,
 │                                  ioctl cmd 0x40c86d01, struct size 168,
 │                                  dims hardcoded @0x13e2a4–ac
 ├─ SP_VI_SetParam                @0x13e61c — passes all-zero VIVPSS struct
 │                                  (@0x13e628–50) ⇒ VPSS bypassed, deinterlace OFF
 └─ SP_HdmiVencCreateChn          @0x13cdf4
     ├─ branch A dims             @0x13cea4 (1280) / 0x13ceac (720)
     └─ branch B dims             @0x13d0b8 / 0x13d0c0
LT8619CLoopTask              @0x13c020 — polls link status
LT8619C_BTSetting            @0x13b0f0 — RX-side timing special cases:
                                          1920×540 fields (1080i), 1440×240/288 (NTSC/PAL i)
LT8619C_EDIDSet              @0x139a20 — writes 256 B to I2C 0x90; default blob @fileoff 0xbd4c7c
```

Address-mapping quirks when re-verifying: vaddr↔fileoff delta is `0x10000` for
`.text`/`.rodata`, `0x20000` for `.data.rel.ro`/`.data`. ARM literal pools use
pc-base = add-instruction address + 8.

### 11.4 What Phase E must change (summary)

Dynamic VI re-init from detected timing (`0x13c390–98` + MIPI `0x13e2a4–ac`),
VPSS deinterlace enable (populate the zeroed VIVPSS struct), dynamic VENC geometry
(`HI_MPI_VENC_SetChnAttr` or re-create), and an honest revised SVD list. Full plan in
HDMI-IMPLEMENTATION-PLAN.md Phase E.

---

## 12. Phase E implementation (2026-08-26, third session)

### 12.1 Scope decision: static-per-build parameterization

Full dynamic multi-format support (E2 items 2–5 of the plan) requires control-flow
changes (trampolines, VPSS deinterlace enable) that cannot be validated without
hardware. Phase E as implemented therefore takes the **static-per-build** slice:
the operator picks the target timing at patch time and the patcher rewrites every
hardcoded immediate consistently. This makes e.g. a 1280×720@60 build possible
today with zero control-flow risk; interlaced input remains **unsupported**
(no deinterlace path — see §11.2 "advertised but broken").

### 12.2 Dead-code proof (caller-count sweep)

Every HDMI entry point was swept for callers using symbol-annotated grep on the
full disassembly (`grep "<addr> <SymbolName>" polestar.asm`; plain `bl\t<addr>`
greps return empty because objdump annotates direct calls):

| Function | Callers | Verdict |
|---|---|---|
| `SP_CreateHdmiTask` @0x13c2a8 | main @0x2a284; DumpYuvTask @0x13c524 | LIVE |
| `RTSP_Init` @0x173494 | main @0x2a298 only | LIVE but stream tree dead |
| `SP_CreateHdmiDumpYuvTask` @0x13c7d8 | test-msg dispatch @0x42830 only (case 2 of `cmp r3,#9` table @0x42784) | debug path |
| `SP_HdmiViInit` @0x13c8c0 | SP_CreateHdmiTask @0x13c39c only | LIVE |
| `SP_VI_StartVi` @0x13e93c | ViInit @0x13c8ec only | LIVE |
| `SP_HdmiVencStart` @0x13d810 | StartRtspVideoView @0x1729f8 only | **DEAD** |
| `RtspVideoDataProc` @0x1724c8 | SP_GetVencStreamProc @0x13d6fc only | **DEAD** |
| `SP_GetVencStreamProc` @0x13d34c | **zero callers** | **DEAD ROOT** |
| `LT8619CLoopTask` @0x13c020 | none via `bl` — pthread entry via literal pool (bytes `20 c0 13 00`) | LIVE (thread) |

Consequence: the entire RTSP/VENC output tree (`SP_GetVencStreamProc` →
`RtspVideoDataProc` → `StartRtspVideoView` → VencStart/CreateChn/Stop →
`RTSP_StartAVCTrackSource` → `HI_VTrack_Source_*` → `RTSP_InitTrackSource`)
is unreachable in stock firmware. Patching its geometry is harmless but pointless;
the patcher gates those sites behind `--include-dead`.

### 12.3 New patcher: `container/hdmi_geometry_patch.py`

Parameterized static geometry patcher following the hardened SITES pattern of
`hdmi_venc_patch.py`. It embeds ARM immediate encoders (verified against stock
encodings for 1920/1280/720/30 rotated-immediate and 1080 MOVW forms):

- **Live sites (always):** `0x13c390/94/98` (fps/h/w args to SP_HdmiViInit),
  `0x13e2a4/ac` (MIPI BT1120 w/h).
- **Dead sites (`--include-dead`):** VENC branches A/B `0x13cea4/ac`,
  `0x13d0b8/c0`; StartRtspVideoView `0x1729ec/f0/f4` (already 1080p in stock);
  RTSP_Init `0x1734dc/f4/fc`.
- Refuses in-place writes; fails loudly on unexpected bytes; idempotent;
  prints md5.

### 12.4 Verification transcript

All runs against true pristine stock (`md5 f1af6203f35848ca42b24f825dfc6ada`),
all 15 site bytes pre-verified to match expected stock encodings:

- Default run (1920×1080@30): 0 written / 5 already patched; output byte-identical
  to stock — correct, since stock already targets this timing.
- 1280×720@60 build: exactly 5 words changed (`0x12c390/94/98`, `0x12e2a4/ac`);
  decoded as `mov r2,#60`, `movw r1,#720`, `mov r0,#1280`, `mov r3,#1280`,
  `mov r3,#720`. Idempotent double-run byte-exact.
- `--include-dead` 1080p build: 6 written / 9 already patched (= 15 sites total;
  the 9 already-patched are sites whose target equals stock). Idempotent.
- End-to-end 1080p artifact (EDID v2 + geometry no-op): 79 bytes changed vs stock,
  all within `0xbd4c86–0xbd4d7b` (EDID blob region). md5 `5dad6b5e459b4c38ae86c7ed55333897`.
- Negative test: corrupted site byte → patcher refuses with exit 1.

⚠️ **Not yet done:** hardware validation of any Phase E build before flashing.
The 720p build changes VI/MIPI timing never exercised by stock — treat as
experimental until proven on hardware.

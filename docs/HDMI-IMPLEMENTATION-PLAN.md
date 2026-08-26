# HDMI Input Enhancement — Detailed Implementation Plan

**Audience:** a junior agent executing this with no prior context.
**Read first:** `docs/HDMI-INPUT-EXPLORATION.md` (background, addresses, safety rules §4, packaging assessment §8.2).
**Golden rule:** never modify anything under `firmware/FwPkt/` in the main repo. All work happens on copies inside Docker.

---

## 0. Environment & prerequisites

| Item | Value |
|---|---|
| Docker image | `polaris-patcher-pentax-v3:latest` (provides `ubi_reader`, `mkfs.ubifs`, `ubinize`, `arm-linux-gnueabi-objdump`) |
| Stock firmware input | A **copy** of `FwPkt/` (contains `firmwareInfo`, `camera/appfs.ubifs`, `camera/config`, `camera/uImage`, `camera/rootfs.ubifs`, `gimbal/*.bin`) mounted read-only at `/in`; output written to `/out` |
| Patcher entry point | `container/patch.sh` (extract → modify tree → repack → regenerate firmwareInfo) |
| Key repo scripts | `container/repack_appfs.sh`, `container/gen_firmwareinfo.py`, `container/ubi_geometry.py` |

Verify your environment first:

```bash
docker run --rm polaris-patcher-pentax-v3:latest which ubireader_extract_files mkfs.ubifs ubinize arm-linux-gnueabi-objdump
```

All four must resolve. If not, rebuild the image per `docker/`.

---

## 1. Phase A — Extract and locate (read-only, zero risk)

1. Copy stock FwPkt to a scratch dir: `cp -r /path/to/FwPkt /tmp/hdmi-work/FwPkt`
2. Extract appfs:
   ```bash
   docker run --rm -v /tmp/hdmi-work:/work polaris-patcher-pentax-v3:latest \
     ubireader_extract_files -k -o /work/app_ext /work/FwPkt/camera/appfs.ubifs
   ```
3. Locate the binary: `find /tmp/hdmi-work/app_ext -name polestar_app`
   Expected path: `.../ubifs/bin/polestar_app`.
4. Disassemble once and keep it:
   ```bash
   arm-linux-gnueabi-objdump -d bin/polestar_app > polestar.asm
   ```
5. Sanity-check the three verified patch sites exist at the expected file offsets
   (ELF mapping: RX segment vaddr = fileoff + 0x10000):
   - EDID blob: vaddr `0xbe4c7c` → fileoff `0xbd4c7c`. Confirm bytes there decode as an EDID starting `00 FF FF FF FF FF FF 00` followed by manufacturer "FHT".
   - VENC branch A: vaddr `0x13ce4c` contains `mov r3,#96`.
   - VENC branch B: vaddr `0x13d060` contains `movw r3,#265`.
   
   **If any of these do not match, STOP.** The firmware is not the analyzed revision; do not guess offsets.

---

## 2. Phase B — Patch 1: EDID injection (do this first, alone)

**Goal:** make the LT8619C advertise a single clean mode so "Auto"-HDMI cameras lock on reliably.

### B1. Build the replacement EDID

Write a 128-byte EDID advertising exactly one preferred DTD of 1920×1080@60
(pixel clock 148.5 MHz), keeping CEA extension minimal or absent. Requirements:

- Header `00 FF FF FF FF FF FF 00`, checksum byte at offset 127 such that the sum of all 128 bytes ≡ 0 mod 256.
- If you include a CEA-861 extension block (recommended for HDMI devices), it needs its own checksum at its byte 127, and VIC 16 (1080p60) set in the first DTD slot.

Generate it programmatically (don't hand-assemble hex). Validate by re-parsing with any EDID parser before use.

### B2. Apply the patch

Two options, in order of preference:

- **Option 1 (in-place blob swap):** overwrite the 128 bytes at fileoff `0xbd4c7c` with the new EDID. Simplest; works because `LT8619C_EDIDSet` (vaddr `0x139a20`) reads this default blob when no custom pointer is passed.
- **Option 2 (pointer redirect):** only if Option 1 is proven insufficient (e.g. blob is larger than 128 bytes and includes the CEA ext). Requires writing a new code stub — do NOT attempt in Phase B.

Record before/after MD5s of `polestar_app`.

### B3. Package and test

```bash
# from container/patch.sh's flow: after modifying the extracted tree,
# repack + regenerate firmwareInfo (these handle ALL checksums):
/opt/patcher/repack_appfs.sh "$STOCK_APPFS" "$APP" "$W/out/appfs.ubifs"
python3 /opt/patcher/gen_firmwareinfo.py /in/firmwareInfo /out/FwPkt > /out/FwPkt/firmwareInfo
```

You do not need to touch checksums manually — see exploration doc §8.2.

### B4. Acceptance criteria

- [ ] Device boots normally (no boot loop) — test on hardware with serial console attached if possible.
- [ ] With a camera set to HDMI Auto connected, device log shows `SP_CheckHdmiId` success (reg0==22 && reg1==4) and EDID negotiation completing.
- [ ] RTSP stream appears (`StartRtspVideoView` path).
- [ ] Stock restore verified: reflash stock FwPkt, confirm original behavior returns.

If EDID negotiation fails on hardware, capture the serial log and stop — do not proceed to Phase C until Phase B works.

---

## 3. Phase C — Patch 2: VENC geometry fix

**Goal:** RTSP stream at native 1920×1080 instead of downscaled 1280×720.

### C1. Identify every dimension store

The channel is created at 1280×720@30 in two branches of `SP_HdmiVencCreateChn` (base vaddr `0x13cdf4`):

- Branch A at `0x13ce4c`: H.264 path (`mov r3,#96`). Nearby stack stores hold width=1280 (`0x500`), height=720 (`0x2d0`).
- Branch B at `0x13d060`: H.265 path (`movw r3,#265`). Same dims nearby.

Disassemble both branches fully and list **every** instruction that materializes 1280 or 720 (immediates like `movw/movt rX,#0x500/#0`, `str` offsets into the channel-config struct). Also check `SP_HdmiViInit` (vaddr `0x13c8c0`) — VI is already initialized at 1920×1080×30, which is why the mismatch exists.

### C2. Encode new immediates

For each site, replace width 1280 → 1920 (`0x780`) and height 720 → 1080 (`0x438`).

ARM Thumb/ARM immediate encodings differ per instruction form:
- `movw rX,#imm16`: direct 16-bit field, straightforward rewrite.
- `mov rX,#imm` ARM modified-immediate: verify `0x780`/`0x438` are encodable; if not, add a literal-pool load (`ldr rX,=const`) — this changes code size, so prefer sites where movw is used, or find spare registers.

Also audit the bitrate formula noted in exploration doc §3.2 (`w*h*10`) and rc fields (4096/30/30/gop1): at 1080p the computed bitrate roughly doubles — confirm the resulting value fits the rc struct field widths and stays within VENC channel limits. Adjust the constant if needed and document the change.

### C3. Verify before packaging

```bash
arm-linux-gnueabi-objdump -d patched_polestar_app | diff - polestar.asm
```
The diff must show ONLY your intended instruction changes. Any other diff line = mistake; redo.

### C4. Package, flash, acceptance criteria

Same repack flow as B3. On hardware:

- [ ] Boots cleanly.
- [ ] RTSP stream resolution is 1920×1080@30 (inspect SDP / stream properties).
- [ ] Both H.264 and H.265 paths tested if selectable.
- [ ] No frame drops/artifacts indicating encoder overload (bitrate headroom check).
- [ ] Stock restore still verified.

---

## 4. Phase D — Optional: loader change for TX modules (ONLY after A–C are field-proven)

This is the "long way downstream" item (exploration doc §8.1). Do not start it unless explicitly instructed AND Phases A–C have shipped successfully.

1. Extract `rootfs.ubifs` the same way as appfs.
2. Locate `komod/sp_load3559v200`; add lines to insmod `hi3559v200_hdmi.ko` and `hi3559v200_vo.ko` (both already present in komod).
3. Repack rootfs; `gen_firmwareinfo.py` picks up the changed rootfs MD5 automatically.
4. First boot MUST be observed over serial: watch for MMZ/IOMMU allocation conflicts (`cat /proc/umap/mmz`) and module load errors. Any wedge → reflash stock immediately.

---

## 5. Hard stops & escalation rules (junior agent: obey literally)

1. **Offset mismatch in Phase A step 5** → STOP, report. Never "search nearby" for plausible values.
2. **Any diff outside intended instructions in C3** → STOP, redo from clean extraction.
3. **Boot failure or boot loop on hardware** → STOP, reflash stock FwPkt, report serial log.
4. **Never edit files under `firmware/FwPkt/` in the repository.**
5. **Never run two patches at once.** One change → package → test → commit → next change.
6. **Every phase ends with a git commit** containing: the patch script (idempotent, takes input/output paths), a README note of before/after MD5s, and updated docs. Binary artifacts go in build output, not committed.
7. If asked to skip verification steps "to save time" → refuse and escalate.

## 6. Deliverables checklist

- [ ] `container/hdmi_edid_patch.py` (or equivalent) — applies Phase B patch idempotently
- [ ] `container/hdmi_venc_patch.py` — applies Phase C patch idempotently
- [ ] `patch.sh` integration: optional `--hdmi-edid` / `--hdmi-venc` flags invoking the above between extract and repack
- [ ] Updated `docs/HDMI-INPUT-EXPLORATION.md` status column per phase
- [ ] Test evidence notes (serial logs, RTSP stream captures) referenced in docs

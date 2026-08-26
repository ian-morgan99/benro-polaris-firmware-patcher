# HDMI Input Enhancement — Detailed Implementation Plan

**Audience:** a junior agent ("the implementer") executing this with no prior context. Every step includes the exact command, the expected output, and a checkpoint a teaching assistant can verify independently.
**Companion docs:** `docs/HDMI-INPUT-EXPLORATION.md` (background & safety rules §4, packaging assessment §8.2).
**Status of facts in this plan:** every address and byte sequence below was re-verified against the stock binary on 2026-08-26 (see Appendix A for verification transcript).

---

## 0. Ground rules (read before anything else)

1. **Never modify anything under `firmware/FwPkt/` in any repo checkout.** All work happens on copies under `/tmp/hdmi-work/`.
2. **One patch at a time.** Phase B fully tested on hardware before Phase C starts. Never combine.
3. **Every phase ends with:** a git commit containing an idempotent patch script + updated docs, and a filled-in acceptance checklist.
4. If any "expected output" below does not match what you see, **STOP and report**. Do not improvise offsets or values.
5. Reference firmware: stock `appfs.ubifs` MD5 must be `47f2ae680be3a5f5d69aa20e20a2397b`. Stock `polestar_app` MD5 after extraction must be `f1af6203f35848ca42b24f825dfc6ada`.

### Environment prerequisites

| Item | Value | How to check |
|---|---|---|
| Docker image | `polaris-patcher-pentax-v3:latest` | `docker images \| grep polaris-patcher-pentax-v3` |
| Tools inside image | `ubireader_extract_files`, `mkfs.ubifs`, `ubinize`, `arm-linux-gnueabi-objdump`, `python3` | `docker run --rm --entrypoint bash polaris-patcher-pentax-v3:latest -c 'which ubireader_extract_files mkfs.ubifs ubinize arm-linux-gnueabi-objdump'` |
| Stock FwPkt | copy of repo's `firmware/FwPkt/FwPkt/` | see step A1 |

Hardware testing requires: the Polaris device, its power supply, network access for RTSP, a serial console if available, and the camera under test. Hardware steps are marked ⚠️ — they cannot be done by software alone.

---

## Phase A — Extract, disassemble, verify (zero risk, no writes to firmware)

### Step A1 — Set up workspace

```bash
mkdir -p /tmp/hdmi-work && cd /tmp/hdmi-work
cp /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt/FwPkt/camera/appfs.ubifs .
md5sum appfs.ubifs
```

**Checkpoint A1:** output is `47f2ae680be3a5f5d69aa20e20a2397b  appfs.ubifs`. If different, you have the wrong firmware revision — STOP.

### Step A2 — Extract appfs

```bash
docker run --rm -v /tmp/hdmi-work:/work --entrypoint bash \
  polaris-patcher-pentax-v3:latest \
  -c "ubireader_extract_files -k -o /work/app_ext /work/appfs.ubifs"
find /tmp/hdmi-work/app_ext -name polestar_app
```

**Checkpoint A2:** prints `/tmp/hdmi-work/app_ext/958962934/ubifs/bin/polestar_app`.

### Step A3 — Disassemble and hash

```bash
docker run --rm -v /tmp/hdmi-work:/work --entrypoint bash \
  polaris-patcher-pentax-v3:latest \
  -c "cd /work/app_ext/958962934/ubifs/bin && arm-linux-gnueabi-objdump -d polestar_app > /work/polestar.asm && md5sum polestar_app"
```

**Checkpoint A3:** md5 is `f1af6203f35848ca42b24f825dfc6ada`; `polestar.asm` is ~350k lines.

### Step A4 — Verify all three patch sites (MANDATORY gate)

Run each check; all three must pass:

**A4a — EDID blob.** File offset `0xbd4c7c` (= vaddr `0xbe4c7c`; RX segment maps vaddr = fileoff + 0x10000):

```bash
dd if=/tmp/hdmi-work/app_ext/958962934/ubifs/bin/polestar_app \
   bs=1 skip=$((0xbd4c7c)) count=16 2>/dev/null | xxd
```

Expected first 16 bytes: `00ff ffff ffff ff00 1914 0100 0101 0101` — the EDID header plus manufacturer code `19 14` ("FHT"). Also verify checksum validity:

```bash
python3 -c "
d=open('/tmp/hdmi-work/app_ext/958962934/ubifs/bin/polestar_app','rb').read()[0xbd4c7c:0xbd4c7c+256]
print('block sums mod 256:', sum(d[:128])%256, sum(d[128:])%256)"
```

Expected: `block sums mod 256: 0 0` (each 128-byte EDID block must sum to 0 mod 256).

**A4b — VENC branch A (H.264 path).**

```bash
grep -n "^ *13ce4c:\|^ *13cea4:\|^ *13ceac:" /tmp/hdmi-work/polestar.asm
```

Expected exactly:
```
13ce4c:	e3a03060 	mov	r3, #96	; 0x60        <- H.264 payload type
13cea4:	e3a03c05 	mov	r3, #1280	; 0x500     <- width store
13ceac:	e3a03e2d 	mov	r3, #720	; 0x2d0     <- height store
```

**A4c — VENC branch B (H.265 path).**

```bash
grep -n "^ *13d060:\|^ *13d0b8:\|^ *13d0c0:" /tmp/hdmi-work/polestar.asm
```

Expected exactly:
```
13d060:	e3003109 	movw	r3, #265	; 0x109    <- H.265 payload type
13d0b8:	e3a03c05 	mov	r3, #1280	; 0x500     <- width store
13d0c0:	e3a03e2d 	mov	r3, #720	; 0x2d0     <- height store
```

**If ANY line differs: STOP. Wrong firmware revision. Do not search for "nearby" values.**

### Step A5 — Record baseline

Save `md5sum` of the pristine `polestar_app` into `/tmp/hdmi-work/BASELINE.md5`. All later diffs are against this.

---

## Phase B — Patch 1: EDID injection

**Goal:** make the LT8619C receiver advertise a single clean preferred mode (1920×1080@60) so cameras set to HDMI "Auto" lock on reliably instead of failing negotiation.

### How it works (verified from disassembly)

`LT8619C_EDIDSet(void *edid)` at vaddr `0x139a20`:
- Writes I2C register `0xFF`=128 then `0x8E`=7 (select EDID RAM page).
- If argument is NULL, writes **256 bytes** (`mov r2,#256`) from a default blob to I2C address `0x90`; else writes 256 bytes from caller's buffer.
- The default blob lives at vaddr `0xbe4c7c` (fileoff `0xbd4c7c`) — 256 bytes = base block + CEA-861 extension block.

Therefore the patch is a **256-byte in-place blob replacement**. No code changes needed.

### Step B1 — Generate the replacement EDID

Create `/tmp/hdmi-work/gen_edid.py`:

```python
#!/usr/bin/env python3
"""Generate a 256-byte EDID: base block + CEA-861 ext advertising 1920x1080@60."""
import struct

def edid_checksum(block):
    block[127] = (-sum(block[:127])) & 0xFF
    assert sum(block) % 256 == 0
    return block

def base_block():
    b = bytearray(128)
    b[0:8] = bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
    b[8], b[9] = 0x19, 0x14                      # manufacturer "FHT" (keep stock identity)
    struct.pack_into('<H', b, 10, 0x0100)        # product code
    b[12:16] = bytes([0x01, 0, 0, 0])            # serial
    b[16] = 0x21                                 # week
    b[17] = 34                                   # year offset (2024)
    b[18] = 48                                   # max h size cm (adjust to taste)
    b[19] = 27                                   # max v size cm
    b[20] = 0x80                                 # digital input, bit depth/features
    b[21] = 0x01                                 # gamma
    b[22] = 0x01                                 # DPMS flags
    # Preferred timing descriptor: 1920x1080@60, pixel clock 148.5 MHz
    pclk = 14850                                  # in 10 kHz units
    b[54], b[55] = pclk & 0xFF, pclk >> 8
    hactive, hblank = 1920, 280
    vactive, vblank = 1080, 45
    b[56], b[57] = hactive & 0xFF, hblank & 0xFF
    b[58] = ((hactive >> 8) << 4) | (hblank >> 8)
    b[59], b[60] = vactive & 0xFF, vblank & 0xFF
    b[61] = ((vactive >> 8) << 4) | (vblank >> 8)
    b[62] = ((88 & 0xF) << 4) | 4                # hfront 88 low nibble | vsync offset 4
    b[63] = ((44 & 0xF) << 4) | 5                # hsync width 44 low nibble | vsync width 5
    b[64:68] = bytes([0x21, 0x50, 0x81, 0x00])   # h/v image size mm
    b[68] = 0xFD                                 # range limits descriptor tag
    b[69:72] = bytes([0x00, 0x30, 0x31])
    b[72:90] = bytes([0x10, 0x1F] + [0]*16)[:18]
    name = b'POLARIS-HDMI'
    b[90:95] = bytes([0x00, 0x00, 0x00, 0xFC, len(name)])
    b[95:95+len(name)] = name
    return edid_checksum(b)

def cea_block():
    c = bytearray(128)
    c[0] = 0x02            # CEA tag
    c[1] = 0x03            # revision
    dtd_start = 8          # after 2 short video descriptors + padding byte
    c[2] = dtd_start       # byte offset of first DTD within this block
    c[3] = 0x40            # HDMI signal, no audio
    c[4] = (16 << 1) | 1   # SVD: VIC 16 (1080p60), native
    c[5] = (4 << 1) | 0    # SVD: VIC 4 (720p60), supported
    d = bytearray(18)
    d[0], d[1] = 14850 & 0xFF, 14850 >> 8
    d[2], d[3] = 1920 & 0xFF, 280 & 0xFF
    d[4] = ((1920 >> 8) << 4) | (280 >> 8)
    d[5], d[6] = 1080 & 0xFF, 45 & 0xFF
    d[7] = ((1080 >> 8) << 4) | (45 >> 8)
    d[8] = (88 & 0xF) << 4 | 4
    d[9] = (44 & 0xF) << 4 | 5
    d[10:14] = bytes([0x21, 0x50, 0x81, 0x00])
    c[dtd_start:dtd_start+18] = d
    return edid_checksum(c)

open('/tmp/hdmi-work/new_edid.bin','wb').write(bytes(base_block() + cea_block()))
print("wrote 256-byte EDID")
```

```bash
python3 /tmp/hdmi-work/gen_edid.py
ls -l /tmp/hdmi-work/new_edid.bin   # must be exactly 256 bytes
```

> **Note for the implementer:** sync-timing nibbles follow CTA-861 1080p60 timings (hfp 88, hsync 44, vfp 4, vsync 5). Validate with an independent parser before flashing (B2) — do not trust the generator alone.

### Step B2 — Validate the EDID independently

```bash
sudo apt-get install -y edid-decode 2>/dev/null || pip install --user parse-edid
edid-decode < /tmp/hdmi-work/new_edid.bin
```

**Checkpoint B2:** parser reports no errors, both block checksums OK, preferred DTD = 1920×1080@60Hz, CEA VIC 16 flagged native. If no parser is available in your environment, write a small python checker verifying: header bytes, both checksums, DTD pixel clock = 14850, active H/V = 1920/1080 — and record its output as evidence.

### Step B3 — Apply the patch (idempotent script)

Create `/tmp/hdmi-work/hdmi_edid_patch.py`:

```python
#!/usr/bin/env python3
"""Replace the 256-byte default EDID blob in polestar_app.
Usage: hdmi_edid_patch.py <polestar_app_in> <edid_256.bin> <polestar_app_out>
Idempotent: detects an already-patched input and passes it through."""
import hashlib, sys

EDID_OFF = 0xbd4c7c          # file offset of the 256-byte default EDID blob
EXPECT_FIRST16 = bytes.fromhex('00ffffffffffff001914010001010101')

def main(inp, edid_path, outp):
    data = bytearray(open(inp, 'rb').read())
    edid = open(edid_path, 'rb').read()
    assert len(edid) == 256, "EDID must be exactly 256 bytes"
    cur = bytes(data[EDID_OFF:EDID_OFF+256])
    if cur == edid:
        print("already patched"); open(outp,'wb').write(data); return
    assert cur[:16] == EXPECT_FIRST16, \
        f"unexpected bytes at {hex(EDID_OFF)}: {cur[:16].hex()} — wrong firmware?"
    assert sum(edid[:128]) % 256 == 0 and sum(edid[128:]) % 256 == 0, "bad EDID checksums"
    data[EDID_OFF:EDID_OFF+256] = edid
    open(outp, 'wb').write(data)
    print("patched:", hashlib.md5(bytes(data)).hexdigest())

main(*sys.argv[1:4])
```

Run it:

```bash
cd /tmp/hdmi-work
python3 hdmi_edid_patch.py app_ext/958962934/ubifs/bin/polestar_app new_edid.bin polestar_patched
```

Then verify ONLY the EDID region changed:

```bash
cmp -l app_ext/958962934/ubifs/bin/polestar_app polestar_patched | awk '{print $1}' | \
  python3 -c "import sys;o=[int(l) for l in sys.stdin];print('changed bytes:',len(o),'range:',hex(min(o)-1),'-',hex(max(o)-1))"
```

**Checkpoint B3:** changed-bytes count ≤ 256 and range lies entirely within `0xbd4c7c – 0xbd4d7b`. Any byte outside that range = mistake; redo from a fresh extraction.

### Step B4 — Package

Copy the stock FwPkt (all files incl. `firmwareInfo`) to `/tmp/hdmi-work/stock_FwPkt`, place the patched binary into the extracted tree, then repack using the existing pipeline (this regenerates ALL device checksums automatically — see exploration doc §8.2):

```bash
cd /tmp/hdmi-work
cp -r /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt/FwPkt stock_FwPkt
cp polestar_patched app_ext/958962934/ubifs/bin/polestar_app
docker run --rm -v /tmp/hdmi-work:/work --entrypoint bash \
  polaris-patcher-pentax-v3:latest -c "
    set -e
    mkdir -p /work/out/FwPkt/camera /work/out/FwPkt/gimbal
    /opt/patcher/repack_appfs.sh /work/appfs.ubifs /work/app_ext/958962934/ubifs /work/out/appfs.ubifs
    cp /work/stock_FwPkt/camera/config /work/stock_FwPkt/camera/uImage /work/stock_FwPkt/camera/rootfs.ubifs /work/out/FwPkt/camera/
    cp /work/out/appfs.ubifs /work/out/FwPkt/camera/appfs.ubifs
    python3 /opt/patcher/gen_firmwareinfo.py /work/stock_FwPkt/firmwareInfo /work/out/FwPkt > /work/out/FwPkt/firmwareInfo"
```

**Checkpoint B4:** the regenerated `firmwareInfo` matches reality. Verify:

```bash
grep '^appfs' /tmp/hdmi-work/out/FwPkt/firmwareInfo
md5sum /tmp/hdmi-work/out/FwPkt/camera/appfs.ubifs
stat -c %s /tmp/hdmi-work/out/FwPkt/camera/appfs.ubifs
```

The MD5 and size on the `appfs` line must equal the md5sum/stat outputs above. Also confirm the other component lines (`config`, `uImage`, `rootfs`) are unchanged from stock firmwareInfo (only appfs should differ).

### Step B5 — ⚠️ Hardware test (acceptance criteria)

Flash per the project's normal flashing procedure. Verify each item and record evidence (serial log excerpt / screenshot):

- [ ] Device boots normally; no boot loop. Wait ≥ 3 minutes past boot.
- [ ] Serial log shows HDMI subsystem alive: `SP_CheckHdmiId` path succeeds (LT8619C ID registers 22/4).
- [ ] Connect camera set to HDMI **Auto** → device detects hotplug; serial log shows EDID read completing without I2C errors.
- [ ] Camera enters live-view-out over HDMI (its rear LCD may blank — normal when outputting).
- [ ] RTSP stream becomes available (`StartRtspVideoView` path); viewable in VLC at the device's RTSP URL.
- [ ] Unplug/replug HDMI → stream recovers within ~5 s.
- [ ] Reflash stock FwPkt → original behavior returns (recovery proven).

**If any box fails: STOP. Capture logs. Do NOT proceed to Phase C.** Most likely failure mode is the specific camera rejecting the EDID timing details — iterate only on `gen_edid.py` timings, never on code addresses.

### Step B6 — Commit

Commit to the working branch: the idempotent patch script (`container/hdmi_edid_patch.py`), the EDID generator (`container/gen_hdmi_edid.py`), updated `docs/HDMI-INPUT-EXPLORATION.md` status, and the acceptance checklist results. Do NOT commit binaries or extracted trees.

---

## Phase C — Patch 2: VENC geometry fix (only after Phase B passes on hardware)

**Goal:** RTSP stream at native 1920×1080 instead of downscaled 1280×720.

### How it works (verified from disassembly)

`SP_HdmiViInit` initializes VI at 1920×1080×30fps, but `SP_HdmiVencCreateChn` (vaddr `0x13cdf4`) builds the encoder channel config at 1280×720 in **two** branches. The exact instructions (ARM, 4 bytes each):

| Branch | Address | Current bytes | Current meaning | Purpose |
|---|---|---|---|---|
| A (H.264) | `0x13cea4` | `e3a03c05` | `mov r3, #1280` | width |
| A (H.264) | `0x13ceac` | `e3a03e2d` | `mov r3, #720` | height |
| B (H.265) | `0x13d0b8` | `e3a03c05` | `mov r3, #1280` | width |
| B (H.265) | `0x13d0c0` | `e3a03e2d` | `mov r3, #720` | height |

Each value is immediately stored to the channel-config stack frame (`str r3,[fp,#-108]` for width, `[fp,#-104]` for height).

**Encoding constraint (important):** 1920 = `0x780` IS directly encodable as an ARM modified immediate (`mov r3,#1920` = `e3a03c07`). 1080 = `0x438` is **NOT** encodable as a single ARM immediate (checked programmatically across all 16 rotations). The same-size fix uses `MOVW` (ARMv7+, already used by this binary at `0x13d060`):

| Address | New bytes | New instruction |
|---|---|---|
| `0x13cea4` | `e3a03c07` | `mov r3, #1920` |
| `0x13ceac` | `e3003438` | `movw r3, #1080` |
| `0x13d0b8` | `e3a03c07` | `mov r3, #1920` |
| `0x13d0c0` | `e3003438` | `movw r3, #1080` |

All replacements are exactly 4 bytes — **no size change, no branch displacement recalculation needed.**

### Bitrate side-effect (must be checked, not skipped)

Immediately before the width store in branch A (`0x13ce70–0x13ce90`) the code computes a float bitrate ≈ `width × height × 10.0` (visible as `vmul.f32 s15,s15,s14` with `s14 = 10.0`, result stored at `[fp,#-120]`). Because it reads the same stack slots we patch, the bitrate scales automatically (~2.25× at 1080p ≈ 20.7 Mbps nominal). The rc max-bitrate constants nearby (`4096`/`8192` selects at `0x13cef0`/`0x13ced0`) should be reviewed: if the computed bitrate exceeds the rc ceiling the encoder clamps quality. **Action:** after patching, read the disassembly around those stores, record the computed values in the commit message, and adjust constants ONLY if hardware testing shows visible quality clamping.

### Step C1 — Apply the patch (idempotent script)

Create `/tmp/hdmi-work/hdmi_venc_patch.py`:

```python
#!/usr/bin/env python3
"""Patch SP_HdmiVencCreateChn channel geometry 1280x720 -> 1920x1080.
Usage: hdmi_venc_patch.py <in> <out>. Idempotent."""
import sys

SITES = {                      # file offset = vaddr - 0x10000 (RX segment)
    0x13cea4 - 0x10000: (bytes.fromhex('e3a03c05'), bytes.fromhex('e3a03c07')),  # mov #1280 -> mov #1920
    0x13ceac - 0x10000: (bytes.fromhex('e3a03e2d'), bytes.fromhex('e3003438')),  # mov #720  -> movw #1080
    0x13d0b8 - 0x10000: (bytes.fromhex('e3a03c05'), bytes.fromhex('e3a03c07')),
    0x13d0c0 - 0x10000: (bytes.fromhex('e3a03e2d'), bytes.fromhex('e3003438')),
}

data = bytearray(open(sys.argv[1], 'rb').read())
for off, (old, new) in SITES.items():
    cur = bytes(data[off:off+4])
    if cur == new:
        continue                       # already patched
    assert cur == old, f"offset {hex(off)}: found {cur.hex()}, expected {old.hex()} — wrong firmware or wrong order"
    data[off:off+4] = new
open(sys.argv[2], 'wb').write(data)
print("venc geometry patched")
```

Run against the **Phase-B-patched** binary (phases compose):

```bash
cd /tmp/hdmi-work
python3 hdmi_venc_patch.py polestar_patched polestar_patched_c
```

### Step C2 — Diff gate (mandatory)

Disassemble the patched binary and diff against baseline:

```bash
docker run --rm -v /tmp/hdmi-work:/work --entrypoint bash \
  polaris-patcher-pentax-v3:latest \
  -c "arm-linux-gnueabi-objdump -d /work/polestar_patched_c > /work/polestar_c.asm"
diff /tmp/hdmi-work/polestar.asm /tmp/hdmi-work/polestar_c.asm
```

**Checkpoint C2:** the diff must contain EXACTLY 8 changed instruction lines (4 removed + 4 added), matching the table above. Anything else = mistake; redo from the Phase-B binary.

### Step C3 — Package

Identical flow to Step B4 (copy `polestar_patched_c` into the tree, repack, regenerate firmwareInfo, verify the `appfs` MD5/size line).

### Step C4 — ⚠️ Hardware test (acceptance criteria)

- [ ] Boots cleanly.
- [ ] RTSP stream properties show **1920×1080@30** (check VLC codec info or the SDP in the RTSP DESCRIBE response).
- [ ] Test BOTH codec paths if selectable (H.264 and H.265 variants) — both branches were patched.
- [ ] Watch 5+ minutes of live view: no stutter, artifacts, or encoder-error messages in serial log (would indicate rc/bitrate clamping — revisit the "Bitrate side-effect" action above).
- [ ] HDMI unplug/replug still recovers.
- [ ] Stock reflash restore still works.

### Step C5 — Commit

Same rules as B6: scripts, docs update, checklist evidence, no binaries.

---

## Phase D — HDMI TX (output) enablement — DO NOT START

Explicitly parked far downstream (exploration doc §8.1). Requires Phases A–C shipped and field-proven, plus explicit user authorization. Why out of scope for now: unknown whether the connector wires SoC TX pins; requires new application code against the HiSilicon MPP SDK (not byte patches); highest brick-risk tier. A junior agent receiving this plan must treat Phase D as out of scope.

---

## Escalation rules (obey literally)

1. Any Checkpoint mismatch → STOP, report exact observed vs expected output.
2. Boot failure/boot loop on hardware → STOP, reflash stock FwPkt, attach serial log.
3. Never edit files under `firmware/FwPkt/` in any checkout.
4. Never apply Phase C without Phase B passing on hardware.
5. Never hand-edit binary bytes interactively — always via the committed idempotent scripts.
6. If asked to skip a verification step → refuse and escalate to the user.

---

## Appendix A — Verification transcript (2026-08-26)

All facts in this plan were re-derived from the stock binary (`appfs.ubifs` md5 `47f2ae…397b`, extracted `polestar_app` md5 `f1af6203f35848ca42b24f825dfc6ada`):

- EDID blob at fileoff `0xbd4c7c`: first 16 bytes `00 ff ff ff ff ff ff 00 19 14 01 00 01 01 01 01`; both 128-byte block checksums sum to 0 mod 256. ✔
- `LT8619C_EDIDSet` @ `0x139a20`: writes 256 bytes (`mov r2,#256`) via `HDMI_WriteI2C_NBytes` to I2C `0x90`; NULL arg → default blob via pc-relative literal `0x00abb218`. ✔
- Branch A: `13ce4c mov r3,#96`; dims `13cea4 e3a03c05` (1280), `13ceac e3a03e2d` (720). ✔
- Branch B: `13d060 movw r3,#265`; dims `13d0b8 e3a03c05`, `13d0c0 e3a03e2d`. ✔
- Width stores go to `[fp,#-108]`, heights to `[fp,#-104]`; bitrate float calc (`×10.0`) at `0x13ce70–0x13ce90` stores to `[fp,#-120]`. ✔
- Immediate encodability checked programmatically: 1920 encodable as ARM imm (rotate 2); 1080 not encodable → MOVW encoding `e3003438` chosen (binary already uses MOVW at `0x13d060`, confirming ARMv7). ✔

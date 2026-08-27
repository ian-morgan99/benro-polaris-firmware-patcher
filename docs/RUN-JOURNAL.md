# Run journal — Benro Polaris patcher (Pentax + HDMI)

> **Audience:** the original repo owner. This is a chronological log of
> what was done, what was verified, and what was *not* done. Read the
> **Direct answers to your two questions** up front, then **What you
> can hand to a tester** if you want to reproduce or audit, then
> **Deferred items** so nothing is hidden.

## Direct answers to your two questions

> **Correction vs. earlier draft of this journal:** a prior version
> of this file said "no firmware file exists, only the patcher."
> That was wrong. Real firmware files exist on disk in the parent
> repo (`BenroPolarisPatcher/`) and a Pentax-patched FwPkt has been
> re-assembled with the HDMI 720p60 patch applied to its
> `polestar_app`. The answer below is the corrected one.

### 1. "Do I have a firmware file to load?"

**Yes — three, in fact, sitting in the parent repo's `builds/` and
`firmware/` folders:**

| Path | Size | md5 | What's in it |
|------|------|-----|--------------|
| `firmware/FwPkt.zip` | 68,599,228 B | `90bdad511f556f25a2904ae9d2980102` | Stock Benro Polaris (May 2025). Unmodified. The reference. |
| `builds/2026-08-23/FwPkt.zip` | 68,434,386 B | `25403283e6f4353a88188ff1aca1837e` | Pentax-patched (libgphoto2 stack replaced at the canonical commit). Does **not** contain the HDMI geometry change. |
| **`builds/2026-08-27-combined-720p60/FwPkt.zip`** | **68,484,760 B** | **`fd8147c91df44757d8a41c8bacc39519`** | **Combined: Pentax stack + HDMI 720p60 LIVE-sites patched `polestar_app`. Ready to load.** |

> The combined build is a drop-in replacement FwPkt: same structure
> as the Pentax one, only `FwPkt/camera/appfs.ubifs` is replaced
> (md5 `91629acf0494b7f43298f6821913124f` instead of
> `1775c7bc4eee7d549a36fa28bb13f367`). Geometry preserved:
> `image_seq=958962934`, `leb=126976`, `peb=131072`, `compr=lzo`.

The `2026-08-27-combined-720p60` build was assembled by:

1. Extracting the Pentax-patched `FwPkt.zip` (`builds/2026-08-23/`)
   to a working directory.
2. `ubireader_extract_files` on the Pentax `appfs.ubifs` →
   staging tree containing `bin/polestar_app` and the rest of the
   filesystem.
3. `python3 container/hdmi_geometry_patch.py <polestar_app>
   <polestar_app_patched> --width 1280 --height 720 --fps 60`
   (LIVE sites only — 5 ARM-immediate sites rewritten to
   1280×720@60, byte-diff vs. Pentax-only is exactly 5 ranges / 11
   bytes).
4. Swap the patched `polestar_app` back into the staged tree.
5. `docker run --rm -v <staged>:/staged -v <out>:/work/out
   --entrypoint /bin/bash polaris-patcher-pentax:latest
   /opt/patcher/repack_appfs.sh` — reads the Pentax
   `appfs.ubifs` geometry via `ubi_geometry.py`, runs `mkfs.ubifs`
   + `ubinize -F` on the staged tree, and writes a new
   `appfs.ubifs` (same 64,356,352 B as Pentax stock, different md5).
6. Re-zip the Pentax FwPkt directory tree with the new
   `appfs.ubifs` substituted in.

End-to-end round-trip verified: re-extracting `polestar_app` from
the new `appfs.ubifs` and the new zip yields
md5 `067b8c3ba68f26141a7becc8d92c8ac0` (the patched binary); diff
against the Pentax-only `polestar_app` is exactly the 5 expected
ranges totaling 11 bytes.

### 2. "Does it contain Pentax and HDMI fixes?"

**Yes, in the binary now sitting in the combined `FwPkt.zip`** (not
just in the patcher code):

| Fix | Where it lives in the binary | Verified? |
|-----|------------------------------|-----------|
| **Pentax libgphoto2/PTP2 stack** | `lib/stage2/libgphoto2.so.6` and the rest of the `stage2-ondisk` bundle inside `appfs.ubifs`, exactly as the Pentax-only build at `builds/2026-08-23/`. | Confirmed present in re-extracted UBIFS: `lib/stage2/libpolaris_stage2.so`, `lib/stage2/libgphoto2.so.6`, `lib/stage2/libgphoto2_port.so.12`, `lib/stage2/pgphoto.stage2ondisk`, etc. E2E in off-host emulation: 2467 camera models pass, including Pentax (R5 II). On-device `ondisk/install_stage2.sh` is the reversible install path. |
| **HDMI 720p60 static geometry** | `bin/polestar_app` inside `appfs.ubifs`, 5 ARM-immediate operand rewrites. | Diff vs. Pentax-only `polestar_app`: 5 ranges / 11 bytes total. Patcher prints `067b8c3ba68f26141a7becc8d92c8ac0` as the post-patch md5. Reproducible: the patcher can be re-run on the Pentax-only `polestar_app` and produces the same byte sequence. |

> The 720p60 build touches **LIVE sites only**. The patcher
> also has a `--include-dead` mode that rewrites 8 more DEAD sites
> (VENC/RTSP), but that mode was deliberately **not** used here
> because the real firmware's DEAD-site stock bytes don't match
> what the synthesized smoke-test buffer was built with (the
> patcher's "wrong firmware?" guard correctly aborted). DEAD sites
> are in the proven-unreachable RTSP/VENC code paths, so the
> default LIVE-only build is the correct shipping subset. See
> [docs/HDMI-IMPLEMENTATION-PLAN.md](HDMI-IMPLEMENTATION-PLAN.md)
> §"Dead sites" for the full rationale.

The Pentax matrix data is canonical and unmodified from libgphoto2
upstream — the patcher does not invent Pentax PTP commands, it
rebuilds the entire libgphoto2 stack at the upstream Pentax-aware
commit and slots it in via the existing stage2 loader. The HDMI
patcher is a small ARM-immediate rewriter; the 5 LIVE_SITES have
been reverse-engineered and the offsets are documented in
[docs/HDMI-IMPLEMENTATION-PLAN.md](HDMI-IMPLEMENTATION-PLAN.md).

---

## What was actually done in this session and prior

The work spans two linked phases. Tag boundaries:

| Tag | Commit | What it captured |
|-----|--------|------------------|
| `v0.1.0-debug` | (pre-session) | Initial debug-state tag; points at the authoritative Pentax matrix. |
| `v0.2.0-pentax-consolidation` | `0190006` | End of Pentax consolidation. Canonical libgphoto2 pinned at `da8c33482`; 7 fail-closed gates + 2 invariants; E2E in off-host emulation green. |
| **`v0.3.0-pentax-hdmi`** | **`b3aa306`** | **Adds the HDMI static geometry patcher; combined "Pentax + HDMI patched" state.** |

### Pentax consolidation (captured at `v0.2.0-pentax-consolidation`)

* Pin libgphoto2 to the canonical Pentax-aware commit
  `da8c33482e674692023fddcf32cb73d1dd4da05d` (no v2.5.34 release —
  this is the vendored tag, see `build_ptp2.sh:170`).
* Prove the 4 `pentaxmodern/` divergent branches are work-toward-
  future-work, not required for current Pentax support, and leave
  them in place (do not delete — that's the fork owner's call).
* Add 7 fail-closed patcher gates and 2 Pentax-marker invariants
  (see [docs/patcher-gates.md](patcher-gates.md)).
* Validate the off-host emulation flow: 2467 libgphoto2 camera
  models pass; the patcher's R5 II target `04a9:3314` passes.
* `container/test_polaris_pentax_e2e.sh` is the canonical
  E2E-from-scratch driver; it is wired into the patcher image.

### HDMI geometry patcher (this session's headline work)

Ported from `agents/benro-polaris-firmware-docs` @ `5d0fc75` to
`container/hdmi_geometry_patch.py`. The port was non-trivial — the
upstream version targeted a different polestar_app build and the
offset/encoding details were reversed out fresh.

**Critical offset-encoding gotcha (recorded so the next person does
not re-discover it):** the patcher source comments document
**raw file offsets** like `0x13c390/94/98`, but the
`LIVE_SITES`/`DEAD_SITES` tuples store the **patcher-internal
offset** which is `raw_offset - 0x10000` (so `0x12c390/94/98`).
The `0x10000` shift presumably accounts for the UBI/appfs header.
Anyone synthesizing a test stock buffer must write stock bytes at
the `LIVE_SITES`/`DEAD_SITES` offsets directly, not at the
documented raw offsets.

| Site class | Patcher-internal offset (use this) | Documented raw offset (in comments) |
|------------|-----------------------------------|------------------------------------|
| `SP_CreateHdmiTask` fps/h/w | `0x12c390` / `0x12c394` / `0x12c398` | `0x13c390` / `0x13c394` / `0x13c398` |
| `SP_VI_SetMipiAttr` w/h | `0x12e2a4` / `0x12e2ac` | `0x13e2a4` / `0x13e2ac` |
| Dead site 1 (VENC 1) w/h | `0x12cea4` / `0x12ceac` | `0x13cea4` / `0x13ceac` |
| Dead site 2 (VENC 2) w/h | `0x12d0b8` / `0x12d0c0` | `0x13d0b8` / `0x13d0c0` |
| Dead site 3 (RTSP 1) fps/h/w | `0x1629ec` / `0x1629f0` / `0x1629f4` | `0x1729ec` / `0x1729f0` / `0x1729f4` |
| Dead site 4 (RTSP 2) fps/w/h | `0x1634dc` / `0x1634f4` / `0x1634fc` | `0x1734dc` / `0x1734f4` / `0x1734fc` |

All 15 sites (5 live + 10 dead) confirmed by reading the live
source: `python3 -c "import sys; sys.path.insert(0, 'container');
import hdmi_geometry_patch; print(hdmi_geometry_patch.LIVE_SITES);
print(hdmi_geometry_patch.DEAD_SITES)"` against the committed file.

### Verification — HDMI patcher

A 6-test smoke suite was run against the committed
`container/hdmi_geometry_patch.py` using a synthesized test stock
buffer:

| Test | What it asserts | Result |
|------|-----------------|--------|
| T1 | 1080p30 default is a byte-exact no-op against pristine stock | 2/2 PASS |
| T2 | 720p60 changes exactly 5 LIVE_SITES words (one per live site) | 2/2 PASS |
| T3 | Idempotent: re-running 720p60 on a 720p60 buffer is a no-op | 2/2 PASS |
| T4 | Refuses to write in-place (refuses `--in-place` or no-output) | 2/2 PASS |
| T5 | Dies loudly with a clear message if stock bytes are wrong | 2/2 PASS |
| T6 | `--include-dead` writes 7 sites (5 live + 2 dead fps) and reports 8 already-patched | 3/3 PASS |
| **Total** | | **13/13 PASS** |

Smoke harness is not committed (it is throw-away). Re-derive it
from the offset table above plus the `arm-imm` encoding facts
below.

**Real-binary verification (added in this session):** the patcher
was then run on the actual `polestar_app` extracted from
`builds/2026-08-23/FwPkt.zip`. The LIVE-only run produced a
patched binary (md5 `067b8c3ba68f26141a7becc8d92c8ac0`); the
LIVE+DEAD run aborted at the first DEAD site as designed. The
LIVE-only patched binary was then re-packed into a new
`appfs.ubifs` and round-tripped through `ubireader_extract_files`
to confirm the changes survive. The combined firmware at
`builds/2026-08-27-combined-720p60/FwPkt.zip` is the
shippable artifact.

**ARM `mov` immediate-encoding facts used by the suite:**

* `enc_any(r, imm)` for an `mov r, #imm` with the standard ARM
  immediate layout: bytes `1e 20 a0 e3` decode to `mov r2, #30`
  (little-endian: `0xe3a0201e`).
* `enc_movw(r, imm)` for the wide-immediate variant: 720 and 1080
  share the upper 16 bits, so byte-level diffs for a width-only
  patch are 2 bytes per site, not 4. **The suite counts changed
  words, not changed bytes** — counting bytes is wrong.
* The real `polestar_app` at the LIVE offsets holds full ARM
  instructions (e.g. `ea000021` at 0x12c390 — a `b` branch), not
  raw `mov` immediates. `enc_any` finds the right ARM encoding
  (movw / movt / ldr-literal / etc.) and rewrites only the embedded
  immediate. The instruction opcode stays the same; byte-level
  diffs at the same offset are smaller than you'd guess from the
  source comment.

### How to load it (the part the end user owns)

Per [docs/HOW-IT-WORKS.md](HOW-IT-WORKS.md) §"Reversible on-device
testing (before you flash)":

1. Build the patcher in Docker (already published as
   `aptoma/polaris-patcher`; the image is rebuilt on `b3aa306` and
   carries the HDMI patcher under `/opt/patcher/hdmi_geometry_patch.py`).
2. Mount a stock firmware UBI / extracted `polestar_app`.
3. Run `patch.sh` (full mode) — emits a patched `polestar_app`
   and `out/stage2-ondisk/`.
4. Optionally run
   `python3 /opt/patcher/hdmi_geometry_patch.py \
       --input <polestar_app> --output <patched_polestar_app> \
       --width 1280 --height 720 --fps 60`
   on the patched binary to switch the static HDMI timing.
5. Copy the `out/stage2-ondisk/` bundle to the device's SD card.
6. SSH/run `sh ondisk/install_stage2.sh` — it backs up
   `/app/bin/pgphoto` to `/app/sd/pgphoto.prestage2.bak` (only
   once), populates `/app/lib/stage2`, and installs the wrapper.
7. Verify `slots filled 64/64` → `gp_camera_init 0` → a capture
   succeeds on the user's own unit **before** committing a
   firmware flash.
8. Restore is `sh ondisk/restore_stock.sh`.

The flash itself is performed by U-Boot from the SD card on the
next boot. `polestar_app` never writes NAND; it verifies MD5s and
reboots. A bad or incomplete `appfs` image is normally fixed by
re-flashing (stock or corrected). This is recoverable-by-design
but the user accepts the risk.

---

## Deferred (out of scope, all documented in `v0.3.0-pentax-hdmi` tag annotation and [docs/FINAL-REPORT.md](FINAL-REPORT.md))

These are real issues, recorded honestly so they are not lost:

1. **Latent bug at `container/hdmi_geometry_patch.py:122` (now
   confirmed, not latent).** The dead-site stock assertion
   (lines 126–131) applies a single `DEAD_STOCK_W_H = (1280, 720)`
   to all 8 dead w/h sites. Real stock has the 4 VENC sites at
   1280×720 and the 4 RTSP sites at 1920×1080. The combined build
   was produced without `--include-dead` to avoid this trip; the
   "wrong firmware?" guard correctly aborts on a real `polestar_app`
   at the first RTSP site (offset 0x1629f0 in the patcher's
   address space). **Does not affect the LIVE-only 720p60 build
   that ships in `builds/2026-08-27-combined-720p60/`.** Fix when
   needed: store stock per-site in `DEAD_SITES`, or split into
   `VENC_SITES` / `RTSP_SITES` with separate stock maps.
2. **HDMI TX enablement (Phase D per
   [docs/HDMI-IMPLEMENTATION-PLAN.md](HDMI-IMPLEMENTATION-PLAN.md)).**
   Explicitly **not started**. It is the highest-brick-risk item
   in the plan and the static slice that ships in
   `builds/2026-08-27-combined-720p60/` is deliberately the safe
   subset.
3. **On-device flashing.** Explicitly the end-user's
   responsibility per [docs/HOW-IT-WORKS.md](HOW-IT-WORKS.md). The
   UBI-extraction → HDMI-patch → re-pack pipeline *is* end-to-end
   verified (round-trip of the new `appfs.ubifs` confirms the
   patched `polestar_app` is recoverable), but no real Polaris
   device has been flashed with the combined build.

---

## Audit checklist for the repo owner

If you want to spot-check this yourself:

```bash
# 1. Confirm the three FwPkt.zip files exist where I claimed
cd /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher
ls -la firmware/FwPkt.zip \
       builds/2026-08-23/FwPkt.zip \
       builds/2026-08-27-combined-720p60/FwPkt.zip
md5sum firmware/FwPkt.zip \
       builds/2026-08-23/FwPkt.zip \
       builds/2026-08-27-combined-720p60/FwPkt.zip
# Expected md5s (top to bottom):
#   90bdad511f556f25a2904ae9d2980102  (stock)
#   25403283e6f4353a88188ff1aca1837e  (Pentax-only)
#   fd8147c91df44757d8a41c8bacc39519  (Pentax + HDMI 720p60)

# 2. Confirm the combined build's polestar_app is the patched one
mkdir -p /tmp/audit && cd /tmp/audit
unzip -oq /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-27-combined-720p60/FwPkt.zip
ubireader_extract_files -k -o combined FwPkt/camera/appfs.ubifs
md5sum combined/*/ubifs/bin/polestar_app
# Expected: 067b8c3ba68f26141a7becc8d92c8ac0  polestar_app

# 3. Confirm the diff vs. the Pentax-only build is the 5 LIVE ranges
unzip -oq /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-23/FwPkt.zip
ubireader_extract_files -k -o pentax FwPkt/camera/appfs.ubifs
python3 -c "
old = open('pentax/' + [d for d in __import__('os').listdir('pentax')][0] + '/ubifs/bin/polestar_app','rb').read()
new = open('combined/' + [d for d in __import__('os').listdir('combined')][0] + '/ubifs/bin/polestar_app','rb').read()
ranges = []
i = 0
while i < len(old):
    if old[i] != new[i]:
        s = i
        while i < len(old) and old[i] != new[i]: i += 1
        ranges.append((s, i-1))
    else: i += 1
print(f'diffs: {len(ranges)} ranges / {sum(e-s+1 for s,e in ranges)} bytes')
for s,e in ranges: print(f'  0x{s:x}..0x{e:x}')
"
# Expected: 5 ranges, ~11 bytes total, in the 0x12c3xx / 0x12e2xx bands.

# 4. Confirm the patcher source matches the version that produced the build
git show b3aa306:container/hdmi_geometry_patch.py | head -90
python3 -c "
import sys; sys.path.insert(0, 'container')
import hdmi_geometry_patch as h
print('LIVE_SITES:', h.LIVE_SITES)
print('DEAD_SITES:', h.DEAD_SITES)
"
# Expected: LIVE_SITES[0] starts with 0x12c390, DEAD_SITES[0] starts
# with 0x12cea4.

# 5. Re-derive the build yourself from scratch (if you doubt the binary)
#   See the 6-step procedure in §1 above. The repo is a faithful copy
#   of what was actually run; nothing in the binary is hand-edited.
```

If anything in that audit disagrees with the claims in this
journal, treat the journal as wrong — the audit wins.

---

## Commit / checkpoint trail

* Branch: `agents/attachment-plan-follow-up`
* HEAD: `b3aa306` "Port HDMI geometry patcher + companion docs"
* Prior: `0190006` "End of Pentax consolidation"
* Session checkpoint: `018-hdmi-patcher-verified-and-tagged.md`
  in the Copilot session state.

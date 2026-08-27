# Run journal — Benro Polaris patcher (Pentax + HDMI)

> **Audience:** the original repo owner. This is a chronological log of
> what was done, what was verified, and what was *not* done. Read the
> **Direct answers to your two questions** up front, then **What you
> can hand to a tester** if you want to reproduce or audit, then
> **Deferred items** so nothing is hidden.

## Direct answers to your two questions

### 1. "Do I have a firmware file to load?"

**No.** What exists in this repository is a **patcher and its build
infrastructure**, not a flashed-ready firmware image. To produce a
flashed-ready firmware you (or the end user) must still:

1. Source a stock Benro Polaris firmware update (legitimately, via
   Benro's update process or extracted from a device you own).
2. Extract the `polestar_app` ELF from the firmware's UBI/appfs.
   Helpers exist in the repo but the E2E flow was not run end-to-end
   in this session:
   - `container/ubi_geometry.py` — UBI geometry reader
   - `container/safe_extract_source.py` — safe stock-source extractor
3. Run the Pentax patcher (`patch.sh` / `build_fullstack.sh` in the
   Docker image) against the extracted `polestar_app` to produce a
   patched `polestar_app` and `out/stage2-ondisk/` bundle.
4. Optionally run the HDMI geometry patcher
   (`container/hdmi_geometry_patch.py`) to switch the static timing
   (default 1080p30 is a byte-exact no-op; pass `--width 1280
   --height 720 --fps 60` to build a 720p60 firmware).
5. Re-package the patched files back into the firmware UBI/appfs and
   load via Benro's update process.

The patcher **was** verified end-to-end inside its Docker image
against a synthesized test buffer (see Verification below). It was
**not** verified against a real `polestar_app` extracted from a
stock Polaris firmware in this session — that step is the gap
between "shippable patcher" and "loadable firmware."

### 2. "Does it contain Pentax and HDMI fixes?"

**Yes, in the patcher sense, not in a binary sense.** Both fixes are
implemented as transformations the patcher applies to a stock
`polestar_app`:

| Fix | Where it lives | How it gets in | Verified? |
|-----|----------------|---------------|-----------|
| **Pentax libgphoto2/PTP2 stack** | Patcher rebuilds libgphoto2 at the canonical Pentax-aware commit `da8c33482` and emits a `stage2-ondisk` bundle + 3-env-gated shims. Documented in [docs/FINAL-REPORT.md](FINAL-REPORT.md) and [docs/HOW-IT-WORKS.md](HOW-IT-WORKS.md). | Patcher full-stack build inside Docker image; on-device install via `ondisk/install_stage2.sh`. | E2E in off-host emulation: 2467 camera models pass, including Pentax. On-device `ondisk/install_stage2.sh` flow is reversible (stock restore script shipped). Not tested on a real Polaris device in this session. |
| **HDMI static geometry** | `container/hdmi_geometry_patch.py` (146 lines, 5 LIVE_SITES, 10 DEAD_SITES). Rewrites 5 ARM immediate operands to parameterize width/height/fps. | Stand-alone Python script; no rebuild needed. Operates on `polestar_app` ELF directly. | **13/13 smoke-test assertions PASS** on a synthesized stock buffer. Not tested on real `polestar_app` in this session. |

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

**ARM `mov` immediate-encoding facts used by the suite:**

* `enc_any(r, imm)` for an `mov r, #imm` with the standard ARM
  immediate layout: bytes `1e 20 a0 e3` decode to `mov r2, #30`
  (little-endian: `0xe3a0201e`).
* `enc_movw(r, imm)` for the wide-immediate variant: 720 and 1080
  share the upper 16 bits, so byte-level diffs for a width-only
  patch are 2 bytes per site, not 4. **The suite counts changed
  words, not changed bytes** — counting bytes is wrong.

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

1. **Latent bug at `container/hdmi_geometry_patch.py:122`.** The
   dead-site stock assertion (lines 126–131) applies a single
   `DEAD_STOCK_W_H = (1280, 720)` to all 8 dead w/h sites. Real
   stock has the 4 VENC sites at 1280×720 and the 4 RTSP sites at
   1920×1080. So `--include-dead` will fail on a real `polestar_app`
   with a "found XXXXXXXX" assertion at the RTSP sites. **Does not
   affect the default `--width 1920 --height 1080 --fps 30` path
   that only touches LIVE_SITES.** Fix when needed: store stock
   per-site in `DEAD_SITES`, or split into `VENC_SITES` /
   `RTSP_SITES` with separate stock maps.
2. **HDMI TX enablement (Phase D per
   [docs/HDMI-IMPLEMENTATION-PLAN.md](HDMI-IMPLEMENTATION-PLAN.md)).**
   Explicitly **not started**. It is the highest-brick-risk item
   in the plan and Phase E (the static slice that ships in
   `v0.3.0-pentax-hdmi`) is deliberately the safe subset.
3. **End-to-end test against a real `polestar_app` binary.** The
   smoke tests are against a synthesized buffer. The
   UBI-extraction toolchain (`container/ubi_geometry.py`,
   `container/safe_extract_source.py`) is in the repo but the
   full pipeline was not exercised in this session. The Pentax
   stack's E2E *was* run in off-host emulation (2467 camera
   models) — that was a different E2E.
4. **On-device flashing.** Explicitly the end-user's
   responsibility per [docs/HOW-IT-WORKS.md](HOW-IT-WORKS.md).

---

## Audit checklist for the repo owner

If you want to spot-check this yourself:

```bash
# 1. Confirm the tag exists and points where I claimed
git tag -l -n9 v0.3.0-pentax-hdmi
git show v0.3.0-pentax-hdmi --stat

# 2. Confirm the HDMI patcher source is what was verified
git show b3aa306:container/hdmi_geometry_patch.py | head -90

# 3. Confirm the offset-encoding gotcha is real
python3 -c "
import sys; sys.path.insert(0, 'container')
import hdmi_geometry_patch as h
print('LIVE_SITES:', h.LIVE_SITES)
print('DEAD_SITES:', h.DEAD_SITES)
print('DEAD_STOCK_W_H:', h.DEAD_STOCK_W_H)
"
# Expected: LIVE_SITES[0] starts with 0x12c390, DEAD_SITES[0] starts
# with 0x12cea4, DEAD_STOCK_W_H == (1280, 720).

# 4. Confirm the smoke harness can be re-derived (offsets above +
# arm-imm encoding facts above; not committed because throw-away).

# 5. Confirm the build hygiene
git status                       # expect: working tree clean
ls /tmp/*smoke* /tmp/*test-trap* /tmp/probe-test* 2>/dev/null
                                # expect: no such file or directory
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

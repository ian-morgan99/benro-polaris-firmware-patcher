# v4 Flash + Pentax Test Session — 2026-09-08

Full record of how v4 got onto the device, what actually triggers the install
(per the polestar_app decompiles), and the live test results for K-3 III /
K-1 II. Companion to `docs/RUN-JOURNAL.md` §"2026-09-07/08".

## 1. The build (v4) — what made it work this time

| | v3 (broken, installed Sep 7) | **v4 (this session)** |
|---|---|---|
| Built with | no `--libgphoto2-source` → vanilla GitHub tarball | `patch-polaris.sh --libgphoto2-source LibGphoto2/libgphoto2` (fork master `6aa3e4e66`) |
| ptp2.so size | 877,348 B — **no** fork markers | **927,572 B — all fork markers present** (`stale Pentax session`, `K-1 Mark II`, `observing camera state`, `Pentax vendor mode enabled`) |
| Provenance | `source_kind=release`, blank commit | `git_commit=6aa3e4e66` + dirty_diff_hash recorded |

**The zip: `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/out/k1ii-k3iii-fixed-v4-20260908/FwPkt.zip`**
- md5 `d0674ef6a12097dedaf91f94e7a8fd90`, 68,397,358 B
- appfs.ubifs md5 `85c3a693361fbe48a62467a4a8a87781` (matches firmwareInfo)

## 2. Staging + install — what we actually did, in order

1. **Pre-flight** (SSH): camera unplugged, `/app/sd` = 128 GB card with ~129 MB used;
   old v3 zip on card was `-rwxr-xr-x` (read-only for all users — noted: vfat
   encodes read-only as missing w-bits).
2. **Pushed the zip** via `cat | ssh 'cat > /app/sd/FwPkt.zip'`, then `chmod 755`.
   On-device md5 verified = local (`d0674ef6…`).
3. **Also pushed the extracted tree** to `/app/sd/FwPkt/` (tar over SSH) and
   verified all 6 `firmwareInfo` entries match the staged files (the on-board gate).
4. **Sent code 783** (`1&783&0&#` → :9090, decompile name `SP_SET_UPGRADE_START`,
   no payload) — **no visible effect**: no `/app/sd/FwPkt/crcInfo` appeared, no
   FwPkt/upgrade lines in Mlog. (266 pings *do* register in Mlog, so the wire
   channel works; 783 alone did not drive extraction on this firmware.)
5. **Fired 812** (`1&812&0&#`) — device came back fast and NAND was still v3
   (stage2 mtimes Sep 7 22:15, ptp2 = 877,348 B). So a plain reboot did **not**
   consume the staged tree.
6. **User power-cycled the gimbal manually → it flashed** (LED flashing during
   U-Boot reflash, then stopped). After boot: stage2 files carry v4 build-time
   mtimes and **ptp2.so = 927,572 B with all fork markers → v4 confirmed installed.**

### Why step 6 worked when 4/5 didn't (decompile evidence)

From `docs/evidence/polestar-disasm-2026-09-01/`:
- **`SP_EVENT_SD_MOUNTED`** is the case that starts upgrades: it calls
  `SP_ExdevUpgradeFromSD(2)` then `SP_OmsUpgradeFromSd` (doc 08 §4).
- **`SP_EVENT_SD_SCAN` does NOT start an upgrade** — it only memsets a BSS object
  and runs one mount handler (doc 08 §5). A plain reboot evidently re-fired
  SD_SCAN, not the full SD_MOUNTED upgrade path.
- The OMS pipeline (`SP_OmsUpgradeCheckFwPkt`, doc 18) is the **entire install**:
  unzip → run `getFwInfo.sh` (writes `crcInfo`) → MD5/CRC validate → write flash.
  It keys on the zip + its magic byte, not a pre-extracted tree.
- Net: the reliable trigger observed today was **zip on card + full power-cycle**
  (fresh SD_MOUNTED event). 783 and 812 were insufficient on their own in this
  firmware build. This needs a dedicated investigation issue (see §5).

## 3. Live test results (user-driven, via Benro Connect iPad app)

### K-3 III (first camera tested after v4 flash)
| Function | Result |
|---|---|
| ISO set | ✅ works |
| White balance set | ✅ works |
| Aperture set | ✅ works |
| Shutter speed set | ✅ sets, but image capture not working at the time |
| Autofocus | ❌ doesn't work |
| Preview (live view) | ❌ doesn't seem to work |
| Capture (manual mode) | ⚠️ "shot failed" first, then trigger fires 5–6 s later; **first shot quick, second says shoot failed** |
| Bulb shutter | ⚠️ massive lag between release request and actual firing |
| USB compatibility mode | **OFF works much better than ON** (ON = worse) |

### K-1 II (second camera)
| Function | Result |
|---|---|
| Recognition with Benro cable | ❌ not recognised at all; different cable tried |
| On attach | ⚠️ dumped a burst of images stuck in the buffer, **crashed the Benro Connect app** |
| USB compatibility mode | must be **OFF** for K-1 II as well |
| Camera settings display | ❌ all show blank on K-1 II |
| Focus settings | ❌ don't work |
| Capture | ⚠️ "shot failed" → image arrives a few seconds later → then it takes another; tends to fire **~10 shots and crash the iPad app** |

### Cross-camera observations
- **USB compatibility mode OFF is required for both cameras** (camera-side setting).
- **Delayed capture pattern**: trigger → "shot failed" → image delivered 3–6 s later.
  Consistent with the known delayed-image-delivery behaviour tracked in patcher #37
  (`K-3 III capture reports -1005 before successful delayed image delivery`).
- **Preview + focus broken on both** — matches open issues #36 (preview `0xa008`/
  NoUpdateImage) and the K-01/K-1 II matrix rows.
- **Burst/crash**: repeated captures (~10) crash the iPad app; possibly buffer
  flush + MJPEG preview interaction (#44 bind-8080).

## 4. Device state at end of session
- v4 installed and running (ptp2 fork markers verified on-device).
- K-1 II attached, camera cycled off/on by user; fresh battery being fitted.
- Gimbal left in agent's hands for a full test suite (ISO/WB/aperture/shutter/
  capture/focus/preview matrix + Clog/Mlog evidence pull).

## 5. Follow-ups
- [ ] **New issue**: "783/812 do not trigger FwPkt install; only fresh SD_MOUNTED
      (power-cycle) does" — with the decompile refs above (docs 05, 08, 18).
- [ ] Log K-3 III / K-1 II results into `docs/TESTED.md` matrix rows once the
      agent test suite completes.
- [ ] Investigate "shot failed → delayed image" against #37; preview/focus against
      #36/#48/#49; 10-shot crash + buffer dump as a new issue if it reproduces.
- [ ] Note for the guide: **USB compatibility mode OFF** is a camera-side
      prerequisite for Pentax on Polaris (both K-3 III and K-1 II).

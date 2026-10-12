# o-v17a offline validation record (2026-10-12)

Candidate: `o-v17a-shutter-fallback-off-20261012` — display version `6.0.0.54.66`.
Purpose: SHIM #6 (issue #187) — fail-closed `gp_camera_get_single_config` wrapper
that can synthesize a minimal TEXT widget for the `shutterspeed` widget when the
camera rejects it, so pgphoto's `updateCameraViewFinder` does not see `ret:-1`
and trigger a restart loop. Shipped **OFF** (`STAGE2_SHUTTER_FALLBACK=0`).

Device access was unavailable on 2026-10-12 (no BT adapter on the host, Polaris
AP unreachable), so this record documents everything that could be validated
offline. Physical A/B (`STAGE2_SHUTTER_FALLBACK=0` vs `1`) and the K-1 II
regression check remain pending.

## 1. Artifact identity

| field | value |
|---|---|
| zip path | `out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt.zip` (local staged; not yet published to PrivateResearch) |
| zip SHA-256 | `8fb21a6856f5074aa4b7b4a3a53d73d6b01632acb082b22bb112e529c02564e0` |
| zip MD5 | `da6fbce4654a748355ae0771599d3c6e` |
| FwVer | `FwVer:6.0.0.54.66;date:2026.10.12;` (MD5 `1311bce546b7…`) |
| appfs.ubifs MD5 | `6cd243515e7d4264824d4136f525ad49` (matches firmwareInfo manifest) |
| rootfs/uImage/config/gimbal MD5s | identical to o-v16g stock (see §2) |
| on-package provenance | `git_commit=2cde4485b…` (libgphoto2, same as o-v16g), `patcher_commit=unknown` (dirty working tree — see §3), `build_id=o-v17a-shutter-fallback-off-20261012`, `display_fwver=6.0.0.54.66` |

## 2. Static diff vs o-v16g (.65, the installed build)

Extracted both appfs trees (`ubireader_extract_files`) and compared file by file.
**16 files differ; every other file in the tree is byte-identical.**

| file | o-v16g MD5 (first 12) | o-v17a MD5 (first 12) | explanation |
|---|---|---|---|
| `FwVer` | `0be0ccb15686` | `1311bce546b7` | `.65` → `.66`, date 10.10 → 10.12 (expected) |
| `bin/pgphoto` (wrapper script) | `327199ceb4b4` | `2e3383301c76` | +`export STAGE2_SHUTTER_FALLBACK=${STAGE2_SHUTTER_FALLBACK:-0}` (verified present at line 35 of the o-v17a wrapper; absent in o-v16g) |
| `lib/stage2/libpolaris_stage2.so` | `95db5d54a0ef` | `d33ef3f52271` | SHIM #6 code (see §4) |
| `lib/stage2/pgphoto.stage2ondisk` | `f31ffcf9b9fd` | `c75ac67532c6` | +1 trampoline: `gp_camera_get_single_config` added to the boundary set (55 → 56 symbols in `stage2_patch.py CORE_BOUNDARY`) |
| `lib/stage2/libgphoto2/2.5.34/{ptp2,pentax}.so`, `camlibs.manifest` | `a2ac7e9b…` / `f5a287a7…` | `0ff16909…` / `e7e34873…` | **toolchain-only rebuild** (see below) |
| `lib/stage2/libgphoto2.so.6`, `libgphoto2_port.so.12`, `usb1.so` (+ stock-path copies under `lib/libgphoto2/2.5.27.1/`) | `5cd64dbd…` etc. | `f798178c…` etc. | **toolchain-only rebuild** (see below) |
| `openpolaris-libgphoto2-provenance.txt` | `d5a4d8f12cb0` | `ce3b80c0fd0b` | build_id / display_fwver / patcher_commit fields |

### Toolchain delta (documented, not a code change)

- libgphoto2 **source is identical**: both builds record `git_commit=2cde4485b0222b38c364f8893f487228102c2d2d` (clean, no dirty diff).
- o-v16g was built with **GCC 6.3.0 (Debian)**; o-v17a with **GCC 13.3.0 (Ubuntu 24.04)** — visible in `.comment` (`readelf -p .comment`).
- The o-v17a build also adds `CFLAGS=-fno-stack-protector` in `container/build_ptp2.sh`.
- Exported dynamic symbol sets of `ptp2.so` and `pentax.so` are **identical** between the two builds (only section symbols `.data`/`.tbss`/`.jcr` differ, which is a GCC-version artifact).
- Consequence: o-v17a is **not a single-variable change over .65** in the strictest sense — the camlib/core/port .so files are rebuilt with a different compiler. The *behavioral* delta is confined to SHIM #6 + the new trampoline + the wrapper env export, all gated OFF by default.

## 3. Patcher provenance

- o-v16g: patcher `9d0efe0` (clean `main`).
- o-v17a: built from `main` @ `7ad3bc9` **plus uncommitted working-tree changes** in `container/`:
  - `stage2_loader.c` — SHIM #6 implementation (+83 lines) and slot-region comment fix
  - `stage2_patch.py` — `gp_camera_get_single_config` added to `CORE_BOUNDARY` (55→56), doc/comment updates
  - `ondisk/pgphoto.wrapper.in` — `STAGE2_SHUTTER_FALLBACK` export (fail-closed default `0`)
  - `build_ptp2.sh` — `-fno-stack-protector` CFLAGS
  - `patch.sh` — build-flow adjustments
- The on-package provenance file therefore records `patcher_commit=unknown`. **Before publishing to PrivateResearch, commit the working tree and rebuild (or record the exact dirty-diff hash) so the registry row can carry a real SHA.**

## 4. SHIM #6 verification in the shipped binaries

`strings lib/stage2/libpolaris_stage2.so` (o-v17a) contains all expected markers,
absent from o-v16g:

- `STAGE2_SHUTTER_FALLBACK` (env gate)
- `shutterspeed` / `Shutter Speed` (widget name/label)
- `[stage2] shutter-fallback: synthesized shutterspeed widget (core ret=%d) -- issue #187`
- `[stage2] shutter-fallback: gp_camera_get_single_config slot -> shim (issue #187)`
- `stage2_shim_gp_camera_get_single_config`, `g_real_gp_camera_get_single_config`

Code review of `container/stage2_loader.c` (working tree):

- Pass-through on success (`ret == 0`) — zero behavior change in the normal path.
- Gate: `getenv("STAGE2_SHUTTER_FALLBACK")` must equal `"1"`; anything else (unset, `0`, other) returns the original error → **fail-closed**.
- Synthesis only for `name == "shutterspeed"`; all other widgets return the original error.
- Widget helpers (`gp_widget_new`, `gp_widget_set_name`, `gp_widget_set_value`) resolved lazily via `dlsym` from the stage2 core and cached; if unresolved, the original error is returned (no crash path).
- Synthesized widget: `GP_WIDGET_TEXT` (== 2), label "Shutter Speed", name "shutterspeed", value `"0/1"` (set-value failure is non-fatal by design — the caller only needs a readable string widget).
- Slot wiring: o-v17a loader logs `gp_camera_get_single_config slot -> shim`; o-v16g does not have that marker (count 0 vs 1).
- **Trampoline count in the shipped `pgphoto` binary** (12-byte ARM pattern `E59FC000 E59CF000` + slot word): o-v16g = **64**, o-v17a = **65** — exactly one new trampoline, for `gp_camera_get_single_config`. File size is unchanged (7,801,576 B) because the patcher rewrites entry points in place.

## 5. Regression checks on the repacked appfs

- **Timed-Bulb dispatch (o-v16g's fix) survived**: `container/polaris_bulb_dispatch_patch.py --check` on the o-v17a `pgphoto.stage2ondisk` → `verified duration-aware Pentax dispatch`.
- **polestar_app original Bulb branch intact** (pre-release gate check, PASS).
- **code-780 version patch** exact-copy + memset length preserved (PASS).

## 6. Pre-release gate (final run 2026-10-12T18:49Z)

`tests/run_prerelease_gate.sh --build out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt`
→ **GATE GREEN: 9 passed, 0 failed, 0 skipped** (log: `/tmp/ov17a-gate-final.log`):

1. container deterministic harness — 20 passed
2. python regression suite — 222 passed
3. agent host check (sandbox) — SANDBOX_OK
4. agent host check (config) — CONFIG_OK
5. code-780 version patch — PASS
6. FwPkt structural validation — PASS
7. firmwareInfo manifest gate (stock vs candidate) — PASS
8. polestar_app original Bulb branch intact — PASS
9. pgphoto timed Bulb dispatch present — PASS

Environment prerequisites that had to be satisfied for the gate to run in this
session (recorded so a future run is reproducible): `pytest` + `pyelftools`
installed for the host python3 (`/run/host/usr/bin/python3`, PEP 668
`--break-system-packages`); `bwrap` + `slirp4netns` symlinked into
`~/.local/bin`; `LD_LIBRARY_PATH=/tmp/hostlibs` (libisl for the cross-compiler);
`OBJDUMP=/run/host/usr/arm-linux-gnueabi/bin/objdump`.

## 7. Version registry

- `.66` recorded as consumed in `docs/RELEASE-VERSION-STATE.md`; monotonic
  allocator confirms next available = `.67`.
- o-v17a row added to `docs/FWPKT-PROVENANCE-CONTRACT.md` (candidate — staged,
  not yet installed).

## 8. Pending (requires device access)

1. **Wake the Polaris** — host currently has no BT adapter (`/dev/hci0` absent,
   no USB BT device, `bluetoothd` not running); AP `polaris_d13e86` unreachable.
2. **Stage o-v17a to `/app/sd/FwPkt`** + reboot via the on-boot watcher.
3. **Verify install**: FwVer `.66`, on-device provenance file, build_id.
4. **A/B test**: `STAGE2_SHUTTER_FALLBACK=0` (baseline, expect #187 restart-loop
   behavior unchanged) vs `=1` (expect no restart loop; watch for the
   `[stage2] shutter-fallback: synthesized shutterspeed widget` stderr line).
5. **K-1 II regression check** before enabling the fallback by default.
6. Commit the patcher working tree and republish with a real `patcher_commit`.

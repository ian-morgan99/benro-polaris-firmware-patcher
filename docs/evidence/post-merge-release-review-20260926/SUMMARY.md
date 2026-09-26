# Post-merge release review — 2026-09-26

- Branch: `release/o-v13d-review-convergence-20260926`
- Base: patcher main `688437b40a95c7aaf9963054b3c8be27ece1bf7d`
- Installed runtime (unchanged): `6.0.0.54.27-o-v13c-boundary-trace`
- Installed libgphoto2: `4868d3649b4a363679ea7ed9d695fbd153063827`
- Harness: `a8b65817354dae04f997d1357d7d4914e396c42f`

## Ownership map

| Behaviour | Owner | Existing implementation | Review change | Deterministic proof |
| --- | --- | --- | --- | --- |
| Operation completion | libgphoto2 exposure/output semantics; Stage-2 publishes Benro lifecycle | o-v13c boundary trace and `[1,4,0]` physical pass | no runtime change | libgphoto2 focused tests; patcher canary fixtures |
| Next-shutter admission | libgphoto2 before `InitiateCapture`; client gate before next request | selectable Pentax admission in `4868d3649` | failed gate operation now consumes the client failure budget; no retry | `tests/test_canary_two_shot.py` |
| Output obligation/reconciliation | libgphoto2 owns camera candidates; caller supplies mode contract | same-stem multi-output reconciliation | removed `photoFormat` inference; explicit one/two-file contract | RAW-only-with-`photoFormat:2`, pair/stale/order fixtures |
| Cancellation | libgphoto2 | cancellation-preserving capture path | no change | existing libgphoto2/harness coverage; physical test still owed |
| Session generation | persistent Benro/OpenPolaris session owner | harness generation contract | no change | harness 62-test suite |
| Reconnect/rebind | persistent Benro/OpenPolaris session owner | harness absent/present/generation model | no change | harness suite; physical rebind still owed |
| External mode/config change | session owner detects invalidation; libgphoto2 supplies config semantics | asynchronous config settle boundary documented | no new runtime behavior | not physically qualified |
| Live View scheduling | persistent workload owner, not generic libgphoto2 | o-v13c Preview suspend/capture/restore pass | no retry after failed capture in live gate | patcher fixtures; physical failure recovery owed |
| Stage-2 dispatch | firmware patcher | direct capture slot, boundary instrumentation | no change | 12 container checks |
| Firmware packaging | firmware patcher | matched stack + manifest/provenance gates | no artifact built because runtime payload is unchanged | package test not runnable without a new artifact |

## Deterministic results

- `./tests/run_prerelease_gate.sh`: 12 container checks PASS; 24 Python tests
  PASS; package checks not run because no new FwPkt exists.
- Harness `pytest -q` at `a8b658173`: 62 PASS.
- Focused canary tests: 7 PASS, including negative-state and timeout tests
  proving exactly one capture send and no retry/second shutter.
- Exact libgphoto2 `4868d3649` Meson regeneration built both selected camlibs
  (`ptp2.so`, `pentax.so`). `test-pentax-reconcile`, `test-pentax-utils`, and
  `test-pentax-aperture-alias` passed. An initial Autotools attempt lacked host
  `autopoint`; the successful Meson run supersedes that prerequisite gap.
- Live identity at 2026-09-26 07:12 UTC proved the `polaris_d13e86` AP/BSSID,
  Wi-Fi route, and installed o-v13c FwVer. No `25fb` USB device was enumerated;
  code 286 returned `manufacturer:none;model:none;state:-5`. The updated live
  shutter gate was therefore correctly not run. This is a camera-absent SKIP,
  not a failure and not new qualification evidence.

## Decisions and remaining physical boundary

- Do not restore the Stage-2 `gp_camera_capture` backoff shim. It obscured the
  lower-layer boundary and broke first-shot dispatch. Automatic retry policy
  belongs to the persistent session/workload owner. The release gate is
  fail-closed and never retries a failed shutter.
- `charge:2` is a status/enum field, not 2 percent. The same frames reported
  `capacity:100`; prior GitHub comments calling this “battery at 2%” are wrong.
- Panorama, Pro Panorama, timelapse/path-lapse, HDR, PLC/SUN/Holy Grail, Pixel
  Shift, cancellation, external physical mode changes, and failure recovery
  remain NOT TESTED unless separately evidenced. Do not infer support from an
  ordinary or Astro-equivalent capture.
- No o-v13d firmware was produced. Repackaging the unchanged o-v13c runtime
  under another version would not answer an outstanding hardware question.
- UVC support is a separate implementation work package. The two local VID:PID
  table entries are not a driver, camlib, Polaris source adapter, or packaged
  runtime.

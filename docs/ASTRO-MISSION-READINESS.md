# Polaris Astro mission readiness

**Review point:** 2026-10-28

This is the end-to-end check against the intended user journey. It is the
operational companion to the design and capture-flow documents; it does not
turn a host build or a simulated solve into hardware qualification.

## Mission map

| Step | Current implementation | Readiness and boundary |
|---|---|---|
| 1. Start Polaris | Existing firmware boot and Astro bundle install | Existing path unchanged. New daemons are opt-in. |
| 2. Autolevel in BenroConnect | BenroConnect remains the owner of autolevel | No plate-solving change is required or made here. |
| 3. Attach camera | Existing pgphoto/libgphoto2 ownership and transfer path | A local JPEG exists only after the transfer/publication contract completes. |
| 4. Select Astro mode | `polaris-trackwatch.sh` records `mode:8` in `/tmp/polaris-mode` | New automation refuses to operate outside mode 8. The mode evidence still needs a real BenroConnect trace on each supported firmware. |
| 5. Pentax StarAF | Existing camera/app autofocus path | This work does not replace or trigger StarAF. Camera focus remains an operator/app responsibility. |
| 6. Calibrate | `polaris-autosolve.sh` solves a live-view snapshot from the observed calibration sequence | Existing dry-run/quality gates remain. It can apply the established 527/530 path only when explicitly armed. Native search uses the focal/RA/Dec hint first and falls back to its bounded indexed blind pass. No full-resolution shutter is fired as a side effect. |
| 7. GOTO | `polaris-goto-solve.sh` supports direct GOTO+solve; `polaris-goto-watch.sh` can recognise Astro 519 `track:1` requests | BenroConnect watcher is opt-in and depends on the observed 519 wire fields. Calibration `track:0` is deliberately ignored. Hardware trace validation is still required. |
| 8. Repeated GOTO refinement | Each accepted solve writes `target.json`, a history record, and a session-local tangent-plane residual model | Sequential evidence accumulation is implemented. Model application is separately gated by `GOTO_MODEL_APPLY=1`; heading application is separately gated by `GOTO_SOLVE_APPLY=1`; low-confidence results never move the mount. |
| 9. Image 1 | Existing camera capture/transfer path publishes local JPEGs | No claim is made for a file that exists only on the camera card. |
| 10. Solve each image | `polaris-frame-watch.sh` watches the supported Polaris-side directories, admits only new/changed JPEG keys after its session boundary, waits for stable completion, solves, and embeds local EXIF by default | Opt-in with `AUTO_SOLVE_FRAMES=1`. It never fires the shutter. Camera-card writeback is not performed. A frame that was never published locally, or completed before the watcher was active, remains outside the automatic guarantee. |
| 11. Drift and rotation | Frame watcher compares solved RA/Dec with the current target and logs rotation | Optional bounded re-centre uses `FRAME_CORRECT=1`; it is withheld when rotation exceeds the configured threshold. Rotation is measured and reported, but no axis-rate command is sent. |
| 12. Adjust motor speed | No qualified firmware per-axis rate primitive is available | Intentionally not implemented through jog commands. Issue [#240](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/240) remains the dependency for exact command discovery, simulator/fault injection, and hardware qualification. |
| 13. Repeat | Frame watcher loop and solve history provide the repeat boundary | The loop is safe only in opt-in mode and with a known local capture-transfer path. It is not yet a universal every-camera guarantee. |

## Safe enablement order

The intended rollout is deliberately staged:

1. Leave `GOTO_SOLVE_WATCH=0`, `GOTO_PLATESOLVE=0`, `AUTO_SOLVE_FRAMES=0`,
   `GOTO_SOLVE_APPLY=0`, and `FRAME_CORRECT=0` while collecting logs.
2. Confirm `mode:8`, the 519 calibration/GOTO records, the app connection,
   local JPEG publication, EXIF focal length, and the selected sensor profile.
3. Enable the GOTO watcher in dry/non-applying mode and verify that calibration
   `track:0` is ignored while a real GOTO `track:1` produces one post-slew
   live-view solve.
4. Enable completed-frame solving and verify duplicate suppression, stable-file
   admission, solve history, pixel preservation, and EXIF readback.
5. Review at least three accepted GOTO residuals and the session-local model in
   dry mode before considering `GOTO_MODEL_APPLY=1`; a model is not a physical
   axis calibration.
6. Only then consider `GOTO_SOLVE_APPLY=1` or `FRAME_CORRECT=1`, with bounded
   correction and a physical recovery test.
7. Do not enable motor-rate adjustment until #240 has an exact firmware-backed
   command contract and a hardware qualification record.

## K-3 III protection

The new path is mode-gated, opt-in, and asynchronous. It does not alter the
normal K-3 III capture function, camera ownership, StarAF controls, or the
existing capture recovery code. It does not issue a shutter command. EXIF
updates operate on the Polaris-side copy and replace that file only after a
validated, flushed temporary output; directory durability and full EXIF
round-trip qualification remain tracked follow-up work in issue #247.

The independent native solver and its bounded native tile-search front end
remain selectable beside Astrometry.net. The real Gaia regional/native search
and a five-position host all-sky-package smoke now pass, including a corrected
triangle-ratio candidate index. The native path is not the default until that
package is installed with a clean ARM build and the wrong-solve, runtime, and
device-capture gates have passed.

## Critical review — 2026-10-28 capture-loop checkpoint

Against the requested mission, the new admission ledger closes one concrete
failure mode: enabling the watcher no longer causes old Polaris gallery files
to be re-solved, and a reused filename is re-admitted when its file key
changes. The watcher also recognises lower-case and upper-case `.jpg`/`.jpeg`
variants. The test is host-only; it does not prove that every camera or
firmware variant publishes every Astro frame under `/app/sd`.

The end goal is therefore still not met. Steps 1–5 remain the existing
BenroConnect/camera path; steps 6–10 have source-level and host/package
evidence but no new physical end-to-end run; step 11 can measure drift and
withhold unsafe corrections; step 12 is blocked on the exact per-axis rate
contract in issue #240; and step 13 cannot honestly be called complete until
rate control, local capture publication, and device qualification are closed.
The compact native index also has a known narrow-field blind-search boundary
for K-3 III APS-C, tracked in issue #248, while hinted solves pass.

The next work must stay in this order: capture/transfer trace on the exact
camera and `.73` runtime; host-only rate-command parser/simulator and fault
tests for #240; broaden or replace the APS-C index under a measured resource
budget; then physical calibration/GOTO/repeated-frame qualification. No live
motor command or firmware patch is justified by this checkpoint.

## Critical review — 2026-10-28 rate/model checkpoint

The plan now has two additional guarded pieces: accepted GOTO residuals are
accumulated in a resettable session model, and a host-only rate-frame safety
harness covers malformed frames, limits, ramping, watchdog expiry and link
loss. Neither changes the default mount behaviour. `GOTO_MODEL_APPLY` remains
off, and the rate harness is not a device command path.

This improves the route from repeated GOTO solves to a measurable experiment,
but it does not close the requested mission. The model is only a first-order
pointing offset, not a multi-axis calibration; model application has not been
physically tested. The matching `.73` MCU image and historical `J` handler are
now identified, but the application exposure/reply path, calibrated units,
axis signs, torque semantics, STOP priority and watchdog remain unqualified.
The frame watcher still depends on a verified Polaris-side publication for
each camera frame, and the native compact APS-C blind-search boundary remains
open (#248). K-3 III normal capture remains untouched because all new controls
are opt-in and rate output is absent.

The K-3 III APS-C geometry profile (23.3 mm) has a separate host result: the
hinted native solve passes in one nearest-tile attempt, but the compact
15-star/tile index does not yet guarantee a five-attempt no-hint solve for the
narrower field. That index-coverage/runtime trade-off is logged in follow-up
issue #248; the operational policy remains to use the mount RA/Dec hint first.

## Evidence still required before calling the mission complete

- Host-side Gaia package generation, tile verification, triangle-index
  verification, five indexed no-hint full-frame rendered solves, a hinted
  APS-C rendered solve, and the canonical ARM bundle/staged-install checks now
  pass. The native EXIF writer also passes a
  host JPEG decode/write-back smoke. This is not yet device proof: the package
  still needs sanctioned SD-card installation, post-boot identity, and
  physical capture qualification.
- A captured BenroConnect trace proving the exact calibration and GOTO 519
  fields on the target firmware, including ordering and duplicate behaviour.
- Two or more physical Astro sessions with a supported Pentax body, showing
  local JPEG publication, EXIF focal length/sensor provenance, solve history,
  and camera recovery after each operation.
- Repeated GOTO solves with a known target, including a deliberately rejected
  low-confidence frame and a stale/incorrect hint fallback.
- Repeated image solves with measured centre drift and field rotation, plus a
  proof that disabled correction sends no mount command.
- Exact firmware-backed motor-rate work from #240; jog/deadman commands are not
  a substitute for tracking-rate control.
- ARM/Polaris build and post-boot provenance checks, followed by physical
  qualification. Host compilation and synthetic sky results remain lower-tier
  evidence.

The honest current product description is therefore: **a guarded, opt-in
Astro solve pipeline with calibration solving, GOTO solve hooks, repeated local
JPEG solving, local EXIF annotation, and logged drift/rotation assessment;
per-axis motor-speed correction is not yet qualified.**

## Critical review — 2026-10-28 native-index correctness checkpoint

Against the thirteen-step end goal, steps 1–5 remain existing Benro/camera
operations and are protected by the new mode gates. Steps 6–10 are wired in
source and host-tested, including calibration/GOTO solve hooks, repeated frame
solving, indexed hint fallback, and local EXIF annotation. Step 11 now compares
frame roll against the stored target roll rather than treating an absolute
camera roll as drift; it still has only a bounded re-centre action and does not
claim tracking correction. Step 12 remains blocked on the exact firmware-backed
rate command in issue #240. Step 13 is a guarded repeat loop, not a complete
tracking system. Therefore the architecture is materially closer and the host
index is internally consistent, but the mission is not yet physically usable or
release-qualified.

## Critical review — 2026-10-28 static motor-path checkpoint

The exact `.73` application was rechecked read-only. It contains a concrete
existing fast-jog path: controls 513/514/521 become five-byte `AC 41` axis plus
signed-int16 speed messages, and the runtime already wraps those controls in a
server-side lease/repeat/stop implementation. The host harness now parses and
fault-tests that shape as well as the separate, still-unrouted `AC 4A` float
helper.

This narrows issue #240, but it does not close step 12. The jog path is not a
tracking-rate API; its physical units, axis signs, continuous-rate behaviour,
MCU acknowledgement, and stop/disconnect semantics still need exact firmware
and controlled hardware qualification. No new live motor command is wired to
the plate-solve loop. Steps 6--11 remain guarded source/host capability, not a
physical mission pass, and the compact APS-C blind-search limitation remains
open in #248. K-3 III capture code and defaults remain unchanged.

## Critical review — 2026-10-28 native bundle checkpoint

The native C focal-length parser is now bounds-safe for malformed/wrapped EXIF
offsets, and the rebuilt ARM bundle passed its ABI/dependency/licence checks,
staged-install checks, QEMU usage smoke and QEMU EXIF write-back smoke. The
same-frame two-solver host smoke also still passes: Astrometry.net was slightly
faster in that run, while the independent result matched its deliberately
paired catalogue exactly. The evidence is recorded in
[`native-arm-bundle-20261028`](evidence/native-arm-bundle-20261028/SUMMARY.md)
and [`dual-solver-overnight-20261028`](evidence/dual-solver-overnight-20261028/SUMMARY.md).

This closes another source/package gate, not the mission. There is still no
sanctioned SD installation, post-boot identity, local camera-publication trace,
physical calibration/GOTO/frame loop, or qualified motor-rate correction. The
runtime therefore remains opt-in and K-3 III-safe by default; no new live
motor path has been enabled.

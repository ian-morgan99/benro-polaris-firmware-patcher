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
| 6. Calibrate | `polaris-autosolve.sh` solves a live-view snapshot from the observed calibration sequence | Existing dry-run/quality gates remain. It can apply the established 527/530 path only when explicitly armed. No full-resolution shutter is fired as a side effect. |
| 7. GOTO | `polaris-goto-solve.sh` supports direct GOTO+solve; `polaris-goto-watch.sh` can recognise Astro 519 `track:1` requests | BenroConnect watcher is opt-in and depends on the observed 519 wire fields. Calibration `track:0` is deliberately ignored. Hardware trace validation is still required. |
| 8. Repeated GOTO refinement | Each accepted solve writes `target.json` and a history record | Sequential refinement is implemented. Heading application is separately gated by `GOTO_SOLVE_APPLY=1`; low-confidence results never move the mount. |
| 9. Image 1 | Existing camera capture/transfer path publishes local JPEGs | No claim is made for a file that exists only on the camera card. |
| 10. Solve each image | `polaris-frame-watch.sh` watches the supported Polaris-side directories, waits for stable JPEG completion, solves, and embeds local EXIF by default | Opt-in with `AUTO_SOLVE_FRAMES=1`. It never fires the shutter. Camera-card writeback is not performed. |
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
5. Only then consider `GOTO_SOLVE_APPLY=1` or `FRAME_CORRECT=1`, with bounded
   correction and a physical recovery test.
6. Do not enable motor-rate adjustment until #240 has an exact firmware-backed
   command contract and a hardware qualification record.

## K-3 III protection

The new path is mode-gated, opt-in, and asynchronous. It does not alter the
normal K-3 III capture function, camera ownership, StarAF controls, or the
existing capture recovery code. It does not issue a shutter command. EXIF
updates operate on the Polaris-side copy and currently replace that file via a
temporary file; loss-safe source/derived-file handling and full EXIF round-trip
qualification remain tracked follow-up work in issue #247.

The independent native solver and its bounded native tile-search front end
remain selectable beside Astrometry.net. The real Gaia regional/native search
and a five-position host all-sky-package smoke now pass, including a corrected
triangle-ratio candidate index. The native path is not the default until that
package is installed with a clean ARM build and the wrong-solve, runtime, and
device-capture gates have passed.

## Evidence still required before calling the mission complete

- Host-side Gaia package generation, tile verification, triangle-index
  verification, five indexed no-hint rendered solves, and the canonical ARM
  bundle/staged-install checks now pass. This is not yet device proof: the
  package still needs sanctioned SD-card installation, post-boot identity, and
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
solving, and local EXIF annotation. Step 11 measures drift and rotation but
only has a bounded re-centre action; it deliberately does not claim tracking
correction. Step 12 remains blocked on the exact firmware-backed rate command
in issue #240. Step 13 is a guarded repeat loop, not a complete tracking
system. Therefore the architecture is materially closer and the host index is
now internally consistent, but the mission is not yet physically usable or
release-qualified.

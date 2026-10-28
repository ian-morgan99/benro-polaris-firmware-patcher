# Plate-solving capture flow and safety contract

**Status: ALPHA / source-audited, not a universal hardware guarantee.**

This document is the canonical description of where a JPEG comes from, when it
exists locally, which component solves it, where EXIF is written, and which
operations may affect the mount. It deliberately separates the Benro head's
firmware protocol from the camera/libgphoto2 capture and transfer path.

## The short version

The solver always receives a local file path. That does **not** mean that every
JPEG captured in Astro mode is automatically copied to Polaris or automatically
solved.

There are three materially different flows:

```text
1. Calibration autosolve

   Benro app 519/530 step:1
       -> autosolve watcher
       -> live-view snapshot over localhost HTTP
       -> /tmp/autosolve-lv.jpg
       -> extract -> solve -> quality gate
       -> optional 527 heading correction / 530 confirmation

   No camera-card image is created by this path.

2. Full-resolution camera frame

   Benro app or supported capture path
       -> camera shutter / PTP capture
       -> camera card (original, where that capture mode supports it)
       -> libgphoto2 transfer
       -> /app/sd/<capture-category>/<frame>.jpg
       -> solve-now or an explicit solve job
       -> extract -> solve -> quality gate
       -> local EXIF update only

3. Astro stacking/lapse capture

   /api/astro/capture
       -> in-head 272 programme
       -> camera/head stacking path
       -> starskyStack or another capture directory

   When AUTO_SOLVE_FRAMES=1 and mode:8 is recorded, the opt-in frame watcher
   admits stable completed JPEGs from the supported local directories.
   Otherwise this remains an explicit/manual solve path.

The hook is opt-in: AUTO_SOLVE_FRAMES=1 plus mode:8 and stable-file
admission are required before a JPEG is sent to the solver.

The watcher establishes an admission boundary when it starts and whenever a
new Astro session opens. Files already present at that boundary are recorded
as baseline content and are not solved as if they were new Astro captures.
Subsequent `.jpg`, `.JPG`, `.jpeg`, and `.JPEG` files are admitted after their
size is stable and their JPEG end marker is present. A reused filename is
eligible again when its size or modification time changes. This prevents a
reboot or a mode transition from re-solving an entire old gallery while still
covering new files published during an enabled session.

This is a local-admission guarantee, not a camera-transfer guarantee. The
watcher cannot recover a frame that the camera/head never publishes under
`/app/sd`, and it cannot prove that the Polaris copy is the camera-card
original. If the watcher is started after a capture has completed, that frame
is outside its observable admission window and must be submitted explicitly.
```

## Source-level flow

### Calibration autosolve

The app's observed sequence is 527, 519, 530 step:1, then 530 step:2 and 531.
The daemon reacts to step:1. It obtains a single live-view JPEG from the head's
MJPEG snapshot endpoint and stores it as `/tmp/autosolve-lv.jpg` before invoking
`polaris-align.sh`.

Live view is not a full light frame. It is approximately 960×640 and has no
camera EXIF, so focal length comes from the configured value or the cached focal
length from a previous real frame. A successful solve can update the mount's
heading through 527 and can participate in the alignment confirmation flow.

The implementation intentionally does **not** fire a full capture when this
live-view solve fails. Earlier attempts to trigger 264/272 during the Astro
calibration window could leave the camera or lapse task wedged. A failed solve
leaves the dialog alone for the user to complete manually.

Relevant implementation:

- [`polaris-autosolve.sh`](../container/astro/ondisk/polaris-autosolve.sh),
  frame acquisition and failure behaviour.
- [`polaris-align.sh`](../container/astro/ondisk/polaris-align.sh), extraction,
  focal/sensor selection, solver invocation, and local EXIF replacement.

### Full-resolution capture and solve

`solve-now.sh` does one of three things:

- `--frame FILE`: solve the supplied local file;
- `--latest`: select the newest JPEG already present under the known
  `/app/sd/...` capture directories;
- `--wait`: wait for a new local JPEG after the user triggers the shot in the
  Benro app.

Its default capture attempt uses opcode 264, but the source explicitly records
that Astro mode may ignore externally initiated captures. The safe supported
Astro workflow is therefore: the user takes the frame in the Benro app, the
file-transfer path publishes a local copy, and `solve-now.sh --wait` or
`--latest` follows it.

The local media root is `/app/sd`. The current search includes:

```text
/app/sd/normal
/app/sd/starskyStack
/app/sd/HDR
/app/sd/panorama
/app/sd/focusStack
/app/sd/sun
/app/sd/Lapse/class_*
```

The local file is evidence that the transfer completed, not evidence that the
camera-card original was modified. The current flow never writes the solved
JPEG back to the camera card.

### Astro stacking/lapse capture

`/api/astro/capture` starts the head's 272 Astro/lapse programme. It is a
separate capture feature. The opt-in `polaris-frame-watch.sh` can now process
stable files under the supported output directories, including `starskyStack`,
but the watcher is not proof that every firmware variant publishes every
programme output locally. The gallery can see files under `/app/sd`, but
visibility in the gallery is not the same as a completed transfer record.

## Solve and EXIF flow

For any frame explicitly sent to `polaris-align.sh`:

```text
local JPEG
  -> polaris-extract
  -> local star list with full-resolution coordinates
  -> selected solver
  -> solved=true plus RA/Dec/scale/roll/confidence fields
  -> quality gate in the caller
  -> polaris-exif-solve writes a temporary JPEG
  -> successful temporary output is moved over the local input path
```

The current EXIF writer is local-only. It writes a unique same-directory
temporary file, flushes the generated JPEG before returning success, validates
the JPEG end marker, and only then atomically renames it over the local input;
on any failure, the original local file is retained. The camera-card file is
outside this operation.

This is stronger crash handling, but it is not a claim of full power-loss
qualification: directory-entry durability and camera/gallery round-trip
behaviour still require the acceptance tests below.

This replacement is not yet a release-grade archival contract. Before enabling
automatic processing of user photographs, we must prove that the writer:

1. preserves the JPEG's decoded pixels exactly;
2. preserves all required existing EXIF, MakerNote, orientation, and thumbnail
   data;
3. produces EXIF readable by the camera/gallery tools we support;
4. survives power loss without leaving a truncated source file; and
5. records solver provenance, catalogue version, focal source, sensor source,
   confidence, and failure state without pretending an unverified solve is true.

## What the mount actually consumes

The current mount-facing path uses:

- solved RA/Dec for astronomical position and heading derivation;
- 527 for the compass/heading correction;
- 530 for the alignment confirmation path;
- 531 for sidereal/lunar tracking state.

The reported image `rotation_deg` is useful metadata, but it is not a mount
tracking attribute in the firmware protocol we have. It must not be described
as something that the head consumes before tracking starts.

## Storage and ownership model

| Object | Location | Lifetime | Safe interpretation |
|---|---|---|---|
| Live-view solve frame | `/tmp/autosolve-lv.jpg` | temporary | A solver input, not a camera-card photograph |
| Full local JPEG | `/app/sd/<category>/...jpg` | persistent on Polaris SD | A transferred copy, if transfer completed |
| Camera original | camera SD or camera internal storage | camera-owned | Never modified by the current EXIF path |
| Failed-solve evidence | `/app/sd/polaris-astro/failed/` | bounded retention | Diagnostic copy, not a source of truth |
| Last solution | `/tmp/polaris-last-solution.json` | temporary | Runtime state; not durable provenance |

The camera-side and Polaris-side files must be treated as separate objects. A
matching filename or capture announcement is not sufficient proof that the
Polaris copy is complete; the local file must be checked for size, JPEG end
marker, and stable metadata before solving.

## Safety contract

The following invariants should hold before this becomes an unattended feature.

### Capture and file safety

- Never solve a file while it is still being written.
- Require a stable size across two observations, a valid JPEG structure, and a
  completed transfer result.
- Never select a merely newest file without recording the capture event or
  proving it appeared after the triggering event.
- Start the watcher before entering Astro mode when unattended per-frame
  solving is required. Its admission ledger intentionally excludes files that
  predate the active session.
- Preserve the original local JPEG. Prefer a sidecar or a new derived file
  until EXIF round-trip and crash-recovery testing are complete.
- Use a same-directory temporary file, `fsync`, and atomic rename only after
  validation. Do not unlink the only known-good copy first.
- Bound failed-frame retention and prevent a full SD card from stopping capture.

### Solver safety

- A solver failure must have no mount side effect.
- A solve must include a trustworthy focal source and sensor geometry, or be
  marked incomplete rather than silently using the wrong default.
- Require independent quality evidence: minimum matches, residual threshold,
  scale plausibility, hint distance, and catalogue/index provenance.
- Reject results that only echo the RA/Dec hint without demonstrating image
  agreement. This is especially important for the current independent C
  prototype.
- Keep Astrometry.net and the independent solver selectable until both have
  equivalent false-solve and recovery tests.
- Make blind search explicitly bounded. If a mount pose is unavailable, do not
  claim that the current independent solver can complete a blind solve.

### Mount safety

- Keep dry-run as the default.
- Never send 527, 530, goto, or 531 solely because a JPEG exists.
- Apply only after `solved=true`, quality gates pass, the frame age is within
  the allowed limit, and the clock/location inputs are known.
- Treat a missing or stale mount pose as a reason to stop, not as permission to
  widen a correction indefinitely.
- Keep image roll out of the mount command path unless a real firmware field is
  identified and separately qualified.
- On any uncertain or contradictory result, leave the user's alignment alone.

### Provenance and observability

Every processed frame should have a durable record containing:

```text
source kind: liveview | transferred-full-frame | synthetic
local path and camera path, if known
camera model and firmware identity
capture/transfer timestamp and file size
input SHA-256 and output SHA-256
solver name/version and catalogue/index identity
focal length, sensor width, and source of each
RA, Dec, scale, roll, match count, residual, confidence
mount action: none | dry-run | applied
failure reason, if not accepted
```

The record should be written atomically beside the local frame or into a
durable session log. `/tmp/polaris-last-solution.json` is useful for the live UI
but is not sufficient audit evidence by itself.

## Required tightening work

1. **Define the capture-transfer contract.** Add an explicit completion record
   from the camera/libgphoto2 path: camera object path, local path, expected
   outputs, actual outputs, sizes, and transfer status.
2. **Add a stable-file gate.** Do not enqueue a JPEG until size, JPEG end marker,
   and mtime have settled.
3. **Separate source and derived images.** Change automatic EXIF processing to
   write a derived file or a recoverable backup until round-trip qualification
   passes.
4. **Qualify the Astro capture watcher.** The initial mode-gated watcher now
   watches all supported directories, waits for a stable JPEG end marker, and
   records duplicate suppression. It still needs per-firmware capture-event
   correlation and physical qualification before it can be called universal.
5. **Harden EXIF validation.** Decode before/after and compare pixels; read back
   the exact solve fields; test existing camera EXIF and MakerNotes.
6. **Harden independent-solver acceptance.** Add false-positive tests with
   wrong hints, wrong focal lengths, unrelated catalogues, noise, repeated
   stars, and blank frames. Do not make it the default until those pass on ARM.
7. **Keep mount application separate.** The solve/EXIF worker should produce a
   result; a separate explicitly armed step should apply heading/alignment or
   tracking changes.
8. **Qualify per camera family.** The documented both-card/full-transfer claim
   is model- and firmware-specific. Repeat the capture, transfer, EXIF, and
   recovery matrix for each supported camera.

## Acceptance gates

The feature is not ready to call “tight and safe” until all of these are true:

| Gate | Pass condition |
|---|---|
| Live view | Snapshot solves or fails cleanly; no shutter/card side effect |
| Full frame | A completed transfer produces a stable local JPEG and preserves the camera original |
| Astro stack | Every claimed output directory is either processed or explicitly excluded |
| EXIF | Pixels and required metadata survive; power-loss test leaves a valid source |
| Solver | Both solvers reject wrong/ambiguous frames and agree within tolerance on fixtures |
| Focal/sensor | EXIF/profile provenance is recorded; unknown geometry fails closed |
| Mount | No command on failed/stale/low-confidence results; dry-run evidence is complete |
| Recovery | Camera, Polaris SD, and solver recover from transfer failure, reboot, and duplicate events |
| Hardware | At least two consecutive captures per supported camera model, with post-capture state and reconnect checked |

Until then, the safe product description is: **local-frame plate solving with
optional local EXIF annotation and guarded mount application**, not automatic
plate solving of every Astro JPEG.

# Instructions for Astro Mode Testing and Roadmap

Read the [v91 identity, installation hold and safety rules](../README.md).
The bundle is experimental additional SD-card software, not a demonstrated
autonomous tracking product or a verified new BenroConnect menu.

## What v91 supplies

- Astrometry.net reference solver and a native-C alternative.
- Gaia catalogue data and selected FITS indexes in `astro-bundle.tar.gz`.
- Opt-in calibration, post-GOTO and completed-frame orchestration.
- Measurement/history and optional local-image metadata processing.
- **No enabled live motor-rate control.** Plate solving is not equivalent to
  correcting tracking or demonstrating better pointing.

The published index selection is **50 mm focal length, 23.5 mm sensor width**.
Do not assume that selection covers another focal length or the full-frame
K-1/K-1 II geometry. The Astro owner must verify coverage and actual image
geometry, including crop mode, before interpreting a failure or enabling use.

## Stage A — package review without hardware

1. Obtain both v91 artifacts and their manifests from the linked PrivateResearch
   directory. Verify hashes; keep firmware and Astro bundle identities separate.
2. Review the bundle manifest and layout in an isolated host directory. Do not
   run ARM binaries directly on an x86 PC or execute a boot script to inspect it.
3. Ask the Astro owner to confirm the **packaged** solver names, config file,
   executable paths, dependencies, index paths and SD installation method.
4. Choose a disposable copy of an existing star-field JPEG with known focal
   length, body/sensor geometry and preferably independently known sky position.
   Keep its original and hash unchanged. RAW-only camera output is not proof
   that a JPEG-consuming Astro path can operate.

**Current handoff gap:** older source documents refer to `/app/astro` and
`polaris-solve-independent`, while newer notes name
`polaris-solve-independent-search` and the release describes additive SD-card
content. Do not treat those examples as a verified v91 installation command.
The owner must resolve them against commit `6825029c` and the actual archive,
then add a tested copy-and-paste procedure here. Do not manually replace Stage-2
or camera binaries over SSH to make those paths fit.

## Stage B — solve an existing image, no capture or motion

This becomes executable only after the owner supplies the verified command and
dependency/configuration recipe from Stage A. Use an offline host/QEMU setup,
or an approved installed device with camera and mount actions explicitly
disabled. A script named `align` must not be assumed to be solve-only.

1. Keep automatic capture, calibration, GOTO, frame watching, guiding,
   corrections and EXIF write-back disabled. Verify effective configuration,
   not just documented defaults. Do not start the optional boot daemons.
2. Run the reference solver on the copied JPEG and save stdout, stderr, exit
   status, duration, input hash, configuration and solution.
3. Run the native solver on the same unchanged image with the same geometry.
4. Compare accepted position, scale, rotation and confidence with independent
   truth. A zero exit code alone is not a correct solve.
5. Test a preselected unsuitable image/wrong hint and check rejection or bounded
   failure. Do not silently loosen quality thresholds until it passes.
6. Confirm no shutter command, mount movement or original-image modification.

Report the limits of a rendered/synthetic test separately from real-image
accuracy and physical Polaris performance.

## Stage C — camera capture to solve, only after camera acceptance

Complete the [camera-only guide](../Instructions%20for%20Camera%20Only%20testing/README.md)
for the specific body first. Use a supervised test window and one session owner.

1. Take one ordinary short exposure through the established app workflow.
2. Prove the matching completed JPEG reaches Polaris storage; record its path,
   size, timestamp, hash and capture-completion evidence.
3. Solve that file manually with correction and metadata writing disabled.
4. Only after this passes, qualify the completed-frame watcher: one image must
   be admitted once, stale/partial/duplicate files rejected, and a new session
   must not reuse an old target as its hint.
5. Do not disable the capture-event admission guard merely to make the watcher
   run. Missing capture-to-file correlation is a blocker to fix and test.

## Stage D — pointing and optional metadata, separately supervised

These are later gates, not currently proven v91 capabilities:

- Observe one calibration and one GOTO with solve-only follow-up and all
  correction/model-application gates off. Prove message ordering and attribution.
- Measure repeated pointing residuals before approving bounded correction.
  Moving the mount requires an explicit safe test window and operator control.
- Test optional EXIF writes only on disposable Polaris-side copies. Verify
  metadata preservation, read-back and interrupted-write recovery; never rewrite
  the camera-card originals as part of this test.
- Measure drift/rotation without claiming rate adjustment. Never substitute
  jog commands for an unqualified motor-rate protocol.

## Roadmap and exit evidence

| Order | Work required | Evidence needed before moving on |
|---|---|---|
| 1 | Resolve v91 package/install/command recipe | Exact archive paths, safe configuration and repeatable solve-only transcript |
| 2 | Finish shared camera #251 work | Exact candidate tests plus per-body physical acceptance; later fixes require a new candidate, not relabelling v91 |
| 3 | Validate optics/index coverage | Real-image cases for intended focal lengths and sensor/crop geometries; native narrow-field work tracked in #248 |
| 4 | Establish device-offline solving | Installed identity, bounded resource use, correct solutions and false-solve rejection |
| 5 | Qualify capture publication/watcher | Capture-to-file correlation, deduplication and failure/reconnect recovery |
| 6 | Qualify calibration/GOTO observation | Exact firmware traces and measured residuals, correction still disabled |
| 7 | Qualify bounded correction and optional EXIF | Independent safety review, stop priority, preservation/recovery and supervised physical results |
| 8 | Research motor-rate control | #240 / PrivateResearch #3: verified command, units/signs, watchdog and physical qualification |
| 9 | Consider unattended operation | Complete lifecycle and safety evidence; never inferred from solver/unit-test passes |

Source context: [Astro overview](../../ASTRO-README.md),
[mission readiness](../../ASTRO-MISSION-READINESS.md), and
[integration handoff](../../ASTRO-CAMERA-INTEGRATION-HANDOFF.md).
These living documents may describe newer work: the immutable v91 manifest
controls what v91 actually contains. Record every result using
[TEST-RECORD.md](../TEST-RECORD.md).

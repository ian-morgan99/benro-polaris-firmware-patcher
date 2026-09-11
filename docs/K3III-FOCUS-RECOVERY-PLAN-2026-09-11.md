# K-3 III focus recovery plan and junior-agent handover — 2026-09-11

## Objective and ordering

Finish K-3 III manual focus through the installed Polaris stack before widening
the work to K-1 II reliability. Do not claim success from a 9090 acknowledgement:
the acceptance gate is physical lens movement plus continued valid JPEG preview.

## Before-state (v9d)

- Installed artifact: `o-v9d-model-aware-focus`, libgphoto2 `90de508a5`.
- K-3 III live view: PASS. A continuous 120-second port-8080 client received
  58 complete JPEGs; ports 22 and 9090 and the Wi-Fi route stayed healthy.
- Direct K-3 III focus with the same libgphoto2 family: PASS in active PC-LV;
  bounded near/far operations use `0x9017`.
- Polaris K-3 III focus: FAIL. `311` returned `ret:0`, but the operator saw no
  movement and the retained log did not show the expected `0x9017` dispatch.
- K-1 II comparison on v9d: one `311 adj:+1` waited through two busy cycles,
  dispatched exactly one old-family `0x9016` operation and received `0x2001`;
  the opposite request immediately afterwards returned `ret:-1` before dispatch.
- Stock pgphoto disassembly establishes the path:
  `311 -> adjustFocusPosition -> adjustFocusStatus -> setFocusChange ->
  updateCameraManualFocus -> gp_camera_set_single_config`.
- `updateCameraManualFocus` calls `waitCameraIdle(500)` before the libgphoto2
  boundary. `setFocusChange` retries only when the pre-dispatch attempt fails;
  it stops after a successful libgphoto2 return. Background config/preview work
  can therefore consume the short idle window and make focus nondeterministic.

## Narrow implementation contract

1. Extend the existing fail-closed `analyze_pgphoto.py` reliability patch to
   identify the exact `waitCameraIdle(500)` call in `updateCameraManualFocus` by
   function range and instruction/call structure, not by a global byte search.
2. Increase only the pre-dispatch idle-wait budget. Do not retry a completed
   `0x9017`/`0x9016` movement, change direction/sign/magnitude, or change the
   model-aware libgphoto2 implementation.
3. Fail closed unless exactly one structurally valid focus wait site is found.
   Record the old/new instruction bytes and virtual address in build output.
4. Preserve the existing Canon R5 II, capturetarget, Pentax keep-LV and preview
   backoff paths. This is a pgphoto integration change, not a libgphoto2 change.
5. Add deterministic tests for exact-site discovery, patching, duplicate/missing
   site rejection, unrelated wait calls remaining byte-identical, and collision
   protection with Stage-2 trampolines.

The proposed budget must be selected from observed timing and encoded safely for
ARM. Do not guess an instruction encoding; assemble or independently decode the
old and new instruction, and make the test assert the immediate value.

## Offline gates before requesting K-3 III

- Focused patcher tests pass.
- Existing source-selection, Stage-2 loader, package and post-repack gates pass.
- Finished image contains matched core, port, camlib and iolib components.
- Firmware artifact has a new provenance row and private-repository copy with
  independently recomputed ZIP MD5/SHA-256 and appfs MD5.
- GitHub issue #47 records the implementation and explicitly says hardware is
  pending.

## K-3 III switch gate

Do not ask for the camera until every offline gate above passes. At that point:

1. Ask the operator to replace K-1 II with K-3 III on the Polaris USB port.
2. Prove identity `25fb:0189`, serial, v9d-successor artifact, loaded hashes,
   route, and open ports 22 and 9090.
3. Start live view and prove at least two complete JPEGs before focus.
4. Issue one minimum near request (`311`, `mode:1`, `adj:+/-1` according to the
   already verified Benro-to-model-aware sign mapping); record the exact
   `0x9017` line and ask the operator to confirm physical direction/movement.
5. Prove another complete JPEG, then issue one opposite minimum request and
   repeat the evidence gate.
6. Stop live view cleanly. Confirm camera state 1, route, ports 22/9090, and no
   `tdata_psh_info` exhaustion or pgphoto restart.

## Current checkpoint — ready for K-3 III (2026-09-11 13:09 BST)

- Source fix: patcher `e41a954`; corrected 17-byte aggregate fail-closed gate:
  `37bac5b`; registry commit: `e201ca6`. All are pushed to `origin/main`.
- Candidate: `o-v9e-focus-idle-wait`; libgphoto2
  `90de508a5441cb7e2b1b02d601b15a7547d7bcee` from a clean, self-contained
  checkout.
- Offline gates: focused tests 5/5 PASS; full-stack ABI/symbol, Stage-2
  collision, post-repack runtime-content, firmwareInfo, and ZIP-layout gates
  PASS.
- Artifact: ZIP MD5 `89e3714ee5f650c5d2463be11996b0ca`; ZIP SHA-256
  `9af10ebf42b17193e073f46902b6a5263509a6be19155ee307e8fc3350d52583`;
  appfs MD5 `3434cd42b3d092552c9599ff338fffc3`. Uploaded to the private
  `PrivateResearch/firmware-packets/o-v9e-focus-idle-wait/` folder.
- Installation: PASS through the sanctioned extracted `/app/sd/FwPkt/`
  boot-watcher flow. All six on-card files matched `firmwareInfo` before reboot.
- Post-install: all seven runtime files match the build byte-for-byte; embedded
  provenance names the clean libgphoto2 SHA; `polestar_app` and pgphoto are
  running; ports 22 and 9090 are open; K-1 II remains identified as `25fb:0183`.
- **Handover state: SWITCH TO K-3 III NOW.** Resume at switch-gate step 2 above.
  Do not modify source or move on to K-1 II until the K-3 III matrix is recorded.

## K-3 III result — PASS (2026-09-11 14:55 BST)

- Identity/provenance: PASS (`25fb:0189`; installed runtime hashes match v9e).
- Held-open PC-LV data plane: PASS. The qualification stream retained 44
  complete JPEG SOI/EOI pairs (3,106,590 bytes).
- Minimum `adj:-1` request while the 8080 client remained established: PASS.
  pgphoto logged `Pentax manual focus drive (new) returned response 0x2001`;
  complete preview frames continued immediately before and after the operation.
- Physical manual focus: **operator-confirmed PASS from the OpenPolaris app**.
  The operator explicitly clarified that this confirmation applies to manual
  focus only, covering functional movement rather than relying on the
  `311 ret:0` acknowledgement alone. Autofocus is not qualified by this result.
- Post-focus health: PASS. K-3 III remained enumerated; `polestar_app` and the
  same pgphoto process remained alive; ports 22, 8080, and 9090 stayed open;
  no `tdata_psh_info`, fatal, segmentation, or duplicate-launch signature was
  present in the current logs.
- K-3 III manual-focus objective is complete. Capture remains a separate
  follow-up because this test does not resolve v9d's pending-transfer timeout.
- **Handover state: K-3 III live view and manual focus COMPLETE; keep K-3 III
  attached while the newly isolated autofocus and dual-candidate capture work
  below is addressed. Do not request K-1 II yet.**

## Remaining K-3 III work discovered after manual-focus PASS

### A. Tap-to-position autofocus — OPEN

Observed UI result: manual focus works; autofocus does not produce a useful
visible result. Do not treat these as one feature.

The PrivateResearch IMAGE Transmitter 2 source supplies the missing contract:

1. Require active PC live view and map the tap from the displayed/cropped image
   into camera live-view coordinates, bounded by the CAF active area.
2. Write `PTP_DPC_PENTAX_LiveViewAFPosition` (`0xd036`) using the existing
   8-byte payload `{2,0,0,0,Xlo,Xhi,Ylo,Yhi}`. K-3 III snaps the requested
   coordinate to an AF point and echoes that point on read-back.
3. Invoke `CamAutoFocus()`, which calls Pentax `InitiateCapture` (`0x9011`)
   with release mode 0/current, **focus mode 1**, MWB mode, sync mode 0, and
   aperture-reset value. This is an autofocus-only operation, distinct from
   normal still capture (focus mode 2/3) and manual drive (`0x9017`).
4. Expose that operation as Pentax `autofocusdrive`; pgphoto's existing
   `updateCameraAutoFocus` path already requests this generic widget.

Acceptance: one centre and one off-centre app tap while PC-LV stays active;
`0xd036` SET/read-back proves the selected K-3 III point; exactly one focus-mode
1 operation succeeds; operator sees focus at the tapped area; JPEGs continue;
no still image/candidate is created. Track in libgphoto2 #57. Never alias this
to manual focus or claim success from the coordinate SET alone.

### B. Periodic Shot failed / Camera busy — OPEN, root cause proven

The 14:57 app shot succeeded completely: camera `IMGP3472.JPG`, capture return
0, download/delete return 0, protocol states 2/3/5, and a valid 14,076,599-byte
`/app/sd/normal/SP_0013.jpg` (MD5
`8fb0f2ac1adb79d3a29955579844a497`). The log also says
`numOfCaptureImage 2`. At 15:02 the next shot was refused before exposure:
`A previous capture's transfer candidate (1) is still pending`, library `-110`,
app `state:-1005`; `SP_0014.jpg` was not created.

This occurrence is not a slow-transfer/UI-timeout defect. A dual-format shot
created two camera-side candidates; libgphoto2 transferred/finalized one and
returned success while the second remained. Fix libgphoto2 #73 by reconciling
all candidates from the *same initiated exposure*, with a strict candidate/time
bound and conditions verification after every deletion. Preserve the later
pre-capture stale-candidate barrier: an unknown candidate found at session or
request start must never be blindly deleted. Also define which dual-format
member Polaris receives so RAW bytes cannot be silently saved under `.jpg`.

Acceptance: two consecutive K-3 III app captures in the current dual-format
configuration; each produces a valid intended-format file and protocol states
2/3/5; no pending candidate before shot two; then repeat with JPEG-only. Retain
the full Clog/Mlog window and post-test process/port health.

### C. Newly verified OpenPolaris UI behaviour

- Pinch-to-zoom works in live view (operator-confirmed).
- Manual near/far controls work (operator-confirmed and raw `0x2001`).
- Tap-to-position autofocus remains OPEN under section A; pinch zoom does not
  prove camera-side live-view zoom or AF-position semantics by itself.

## After-state acceptance matrix

| Gate | Required result |
|---|---|
| K-3 III identification/runtime provenance | PASS |
| Pre-focus live-view JPEG data plane | PASS |
| Near request reaches K-3 III new-family focus operation | PASS — raw `0x2001` |
| Near physical movement/direction | PASS — operator confirmed app manual-focus controls work |
| Intervening JPEG after near | PASS |
| Far request reaches K-3 III new-family focus operation | PASS — subsequent app controls logged raw `0x2001` |
| Far physical movement/direction | PASS — operator confirmed app manual-focus controls work |
| Post-focus preview and clean stop | PASS |
| Ports 22/9090, route and processes | PASS |
| Capture | Retest separately; not implied by focus PASS |

If any row fails, preserve Clog/Mlog and the client transcript, mark the row
FAIL or BLOCKED, update #47, and do not move on to K-1 II fixes.

## Subsequent K-1 II work

Only after K-3 III passes: rerun the same focus matrix expecting `0x9016`, then
address K-1 II config-poll/preview contention as a separate change. The current
one-success/one-failure comparison is evidence of nondeterminism, not permission
to add blind lens-movement retries.

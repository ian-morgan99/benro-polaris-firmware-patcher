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

## After-state acceptance matrix

| Gate | Required result |
|---|---|
| K-3 III identification/runtime provenance | PASS |
| Pre-focus live-view JPEG data plane | PASS |
| Near request reaches exactly one `0x9017` | PASS |
| Near physical movement/direction | Operator-confirmed PASS |
| Intervening JPEG after near | PASS |
| Far request reaches exactly one `0x9017` | PASS |
| Far physical movement/direction | Operator-confirmed PASS |
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

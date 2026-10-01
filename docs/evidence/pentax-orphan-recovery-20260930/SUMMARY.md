# Pentax orphan-output investigation — 2026-09-30

Status: **source-semantics conflict resolved; recovery NOT implemented;
direct-camera reproduction BLOCKED on physical attachment**. No device command,
shutter, candidate deletion, firmware build, or install occurred in this pass.

## Findings

The existing admission diagnostic misidentifies a transfer-candidate flag as
active capture. Both exact built camlibs (`fbc2e7e65`, installed lineage, and
`df64a6330`, current source) classify synthetic conditions matching the logged
`size=576,+32=1,+36=1,+104=0` as `capture-active`. Their reused-session
classifier calls the same input a stale candidate, handle 1. The attached probe
calls the production functions exported by each actual `ptp2.so`; it does not
replace them with a Python implementation. Its other condition words are zero,
so this is a synthetic diagnostic reproduction, **not a replay of a complete
camera frame or proof of physical idleness**.

The correct source interpretation is candidate-available at +32, candidate
selector at +36, shooting/processing at +104. In the K-3 III new-transfer path,
selector **1 is a sentinel**, remapped by IT2 to `uint.MaxValue`; it is not a
unique photograph ID. Never key a durable request journal by handle 1, or infer
that playback image `484-3701` is this candidate without reading its metadata.

Admission must remain closed. Relabelling `capture-active` alone cannot recover
the file, establish output ownership, or make the next shutter safe. A zero +104
sample alone also does not replace full mode/operation-state checks (including
Astro +24, noise reduction +12, task-changing +504, and unknown states).

## Normative source trace

Local source is `LibGphoto2/IT2_2625_decompile/RemoteAssistant/MtpDevice.cs`,
SHA-256 `e8d11ed772aad3731d7eabd0c06fb0174aae859c5a1f6d241bf73b6d046de059`.
These anchors refer to that exact file, not a different decompiler release.
The decompiled source remains in its existing location; it is not copied here.

| Boundary | Source anchor and observation |
| --- | --- |
| Model | `Model` setter, 546–555: K-3 III selects model 78420 and `_isNewTransferMode=true`. |
| UI/release | `MainWindow.ShutterBtn_Click` / `SendReleaseCommand`, 4918–4964, calls `CamRelease`; `MtpDevice.CamRelease`, 3659–3738, handles release/termination separately from transfer. A 0x2001 response is only acknowledgement. |
| Serialization | `ExecuteCommandWithoutDataPhase`, `ExecuteCommandWithDataToRead`, `ExecuteCommandWithDataToWrite`, around 4053–4086, lock `_wpdCmdLock`; command/data/response failures propagate separately. |
| Conditions | `MtpGetAllConditions`, 4662–4689: +32 equal to 1 sets `_transCandidateObjectFlag`; +36 supplies the selector. Selector 1 becomes `uint.MaxValue` and selects still/new transfer, not movie transfer. |
| Activity | Same method, 4691 onward and 5085–5117: +12 noise reduction, +24 Astro pre/main operation, +104 bit 0 shooting and bit 1 processing; these are separate from candidate availability. |
| Poll/dispatch | `TimerInitialize`, 3620–3625, starts the condition timer at 100 ms. `ConditionRefreshTask`, 2848–2907, reads conditions and dispatches `ExecuteFileTransfer` for new still transfer when the candidate is present and no transfer is running. It does not require a newly initiated shutter or a process-local original request. |
| Inspect/name | `ExecuteFileTransfer`, 3217 onward, first calls `GetTransferCandidateFileInfo(254)`; parses extension and chooses the camera filename, with collision handling and `FileMode.CreateNew`. |
| Transfer | Same method, 3420 onward: file info type 0, begin command 1, block command 3, seek commands 4/5/6, finish command 2. K-3 III uses 32 MiB blocks; other models 8 MiB. |
| Publication/finalize | Around 3516–3563: flush stream, close file, notify `RaiseFileTransferred`, then `MtpDeleteTransferCandidate`. The earlier unsaved-format branch deletes a candidate; **do not copy that branch for orphan recovery**. |
| Wire | 5337–5382: metadata 0x900b with image-type parameter, commands 0x900c, data 0x900d with requested byte count and returned Param1, release 0x900e GETDATA/no parameters. |
| Teardown | `Disconnect`, 3628–3653, stops/disposes timers, disables vendor mode, closes device. This is not evidence for automatically resetting or terminating an unknown exposure. |

The trace establishes IT2 field/dispatch semantics. It does not establish safe
transfer after every Pentax interruption, nor prove the crash's root cause.

## Production recovery and durability gaps

At libgphoto2 `df64a63300585dbd8642861d760668b1ace92f78`:

- `pentax-utils.c:799` checks unsafe +104 first, then labels +32 as capture
  active, then checks +36. Both nonzero flag/selector still block a new shutter.
- `library.c:10950` (`pentax_reconcile_reused_session`) remembers a stale
  candidate but neither transfers nor publishes it. `camera_pentax_capture`
  refuses subsequent capture requests while it remains present.
- `pentax_reconcile_transfer_candidate` transfers to a buffer, constructs a
  `CameraFile`, and publishes into `gp_filesystem_set_file_noop` plus the
  process-local publication cache. The extra-candidate loop can then release
  the camera candidate. This is not a durable file on Polaris SD and is not an
  acknowledgement from pgphoto that the file survived host process death.
- Consequently reusing that callback alone for orphan recovery would not meet
  the durable publication requirement. An orphan recovery API needs an explicit
  consumer publication acknowledgement, separate from successful RAM caching.

Required implementation boundary after a direct reproducer:

1. Inspect without initiating another exposure. Distinguish active/unknown
   operation from recoverable output; preserve candidate on all errors.
2. Persist camera identity, original request identity if provable, transport
   generation, camera filename/format, transfer state, and output digest/path.
   A filename or selector alone is insufficient to reclaim an old request.
3. Transfer to a new file; validate completeness, flush/fsync the file and
   publication directory, then journal publication. Do not overwrite an
   existing user image or map it to the refused request's SP filename.
4. Acknowledge/release only the exact candidate whose publication is confirmed.
   Revalidate candidate metadata and session before any acknowledgement; an
   ambiguous release outcome must not cause blind deletion of the next output.
5. Report an unowned file explicitly as recovered/orphan. Continue refusing the
   new request; a subsequent independent request requires fresh strict admission.

Required production-path regressions: active exposure with/without candidate;
idle orphan; missing metadata; truncated transfer; publication/fsync failure;
owner/process loss before and after publication; ambiguous finalization;
reused selector 1 for a different filename; RAW+JPEG companions; cancellation;
stale transport generation; distinct original/refused/recovered identities.
These are acceptance criteria, not implemented/passing tests.

## Build and test evidence

- Patcher base `360a104`: offline gate GREEN, 16 container checks and 25 Python
  tests passed. Nested container runner skipped `test_polaris_pentax_build_package`
  and `test_source_input` for absent prerequisites; the aggregate gate's zero
  skip counter does not include these. No package/live gate was run.
- Clean isolated libgphoto2 prefixes built from installed-lineage `fbc2e7e65`
  and current `df64a6330`, with ptp2/directory and libusb1/usbscsi, research
  capture enabled. Deterministic suites (`--no-suite no-ci`) each passed 14/14.
- The initial unrestricted df64 suite was 14 PASS / 1 FAIL: `no-ci:test-gp-port`
  attempted the host's unrelated USB storage port and failed with `Bad parameters`.
  The observed failure is recorded here; its temporary full log was removed
  before archival. It is not a Pentax test or a full-suite PASS.
- `fbc2-condition-probe.txt` and `df64-condition-probe.txt` record the compiled
  production classifier results and module hashes. Neither touched hardware.

## Qualification correction and next physical boundary

The 17:35 UTC review on patcher #149 marks o-v15a **PHYSICAL FAIL / NOT
RELEASE-QUALIFIED**, superseding the old "no shutter test" readiness state.
Preserve the distinction between incidents: the retained 14:43 accepted-shot
crash snapshot identifies **6.0.0.54.43 / o-v13x**, whereas the later 16:00–16:04
pre-shutter refusals and 16:43 identity check identify **6.0.0.54.44 / o-v15a**.
Do not relabel the earlier crash as proven on v15a.

At this pass no Pentax was enumerated on the PC and the route to 192.168.0.1
used wired `enp11s0`, not Polaris Wi-Fi. No SSH/device result was accepted.
The operator has been asked to attach the K-3 III directly to the PC with no
exposure running and camera apps closed. Next verify fresh 25fb:0189 enumeration,
then use the isolated **fbc2e7e65 installed-lineage** prefix for a bounded
conditions-only read with exact loader proof and a complete debug trace.
Do not send a shutter to reproduce the admission problem. The USB move may
clear the stale state; if so, record NOT REPRODUCED instead of manufacturing an
orphan by disconnecting during exposure. Compare current df64 only after the
installed-source baseline is understood.

The libgphoto2 owning repository's `AGENTS.md` requires a direct-camera
reproducer before a consumer-derived behavioral change. Until that boundary is
met, no library recovery behavior or supported firmware package is changed.


## Workspace relocation — 2026-10-01

The two build worktrees named in the original transcripts were retired after
verified archival. Their identical installed binaries now live at
`LibGphoto2/libgphoto2/_baselines/<full-source-sha>/prefix`; all 75 regular file
hashes in each prefix match. Both relocated production classifier probes and
CLI loader checks pass. See `../workspace-convergence-20260930/` for current
paths and verification, and `../../WORKSPACE-CONVERGENCE-20260930.md` for archive
recovery. Historical transcript paths are collection-time evidence.

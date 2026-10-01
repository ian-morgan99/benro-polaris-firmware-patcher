# Capacity recovered; Pentax capture remains blocked — 2026-09-30

After the user's observation that SD capacity had recovered, the current
Mlog confirms Polaris SD status became `status:1`, total 121866 MB, free
116833 MB, used 5032 MB. It had initially sent `status:0`, total/free/used 0
during startup. The SD-capacity issue recovered independently of the camera
capture state.

The updated Mlog records four Benro Connect capture requests:

| Time | Requested Polaris path | Result |
| --- | --- | --- |
| 16:00:42 | `SP_0151.jpg` | `-110` / app `-1005` |
| 16:01:49 | `SP_0152.jpg` | `-110` / app `-1005` |
| 16:02:00 | `SP_0153.jpg` | `-110` / app `-1005` |
| 16:03:44 | `SP_0154.jpg` | `-110` / app `-1005` |

For request 1 the Pentax strict admission sample was
`ptp=0x2001 size=576 field32=1 field36=1 field104=0`, blocked as
`capture-active`. Requests 2–4 ran the recovery probe, but received the same
conditions and remained blocked. There is no `InitiateCapture`, terminal
successful lifecycle, or code-773 file publication for these requests. The
four requested Polaris paths are absent on the Polaris SD. The camera stayed
enumerated as `25fb:0189`; no USB disconnect is visible in the kernel tail.

This confirms that the recovered Polaris SD capacity did not clear the Pentax
capture-active/candidate state. These four app requests did not initiate new
exposures; do not retry again. The state and candidate's exact camera-side
owner remain unresolved, so preserve it and do not clear it or weaken
admission.

Raw logs and hashes are in `raw/`.

## Camera playback clarification

The user confirms the latest visible camera image, `484-3701` at 14:33, was
taken through Benro Connect. The available evidence does not establish who
initiated it (the user or an earlier assistant test), whether the file was
transferred/published to Polaris, or whether the persistent `field36=1`
candidate is this image: the available 16:00 snapshot contains no
filename-to-camera-object mapping for `484-3701`. Preserve the candidate and
keep the capture barrier in place until transfer/publication ownership is
established.

## Read-only live check and implementation finding — 2026-09-30 16:43 BST

Polaris identity was re-verified before the read-only check: connected to
`polaris_d13e86`, BSSID `48:e7:da:d4:b5:73`, route to `192.168.0.1` via
`wlp8s0`, and `/app/FwVer` reported `6.0.0.54.44`. No command was sent to the
camera and no process was stopped or restarted.

`/app/sd/normal` still has no `SP_0151` through `SP_0154`; the newest listed
normal-capture pair is `SP_0150.dng/.jpg` from 01:59. The retained Mlogs have
no `484-3701` name or matching 14:33 code-773 publication. Thus the 14:33
camera image is not evidenced as published on Polaris, although it might have
been saved under another mapping/location not present in the retained logs.

The source-level liveness gap is now specific: on reused Pentax sessions,
`pentax_reconcile_reused_session()` records the pending candidate handle but
does not transfer or publish it. The next capture's recovery probe clears
`recovery_required` only when strict admission sees no active flag and no
candidate; the pre-shutter barrier then refuses any nonzero candidate. There
is no orphan-candidate salvage/publication path. This correctly avoids silently
discarding an unknown file, but after the original owner is lost it can leave
Benro Connect in permanent `CAMERA_BUSY` with no user-level way to recover.

The corrective work must separate two cases: (1) a genuinely active exposure,
which remains blocked; (2) an orphan candidate, which must be identified and
made safely recoverable without claiming it as a new shutter or deleting it
before publication. The lower-level libgphoto2 contract should expose that
candidate and retain it until publication is confirmed; Stage-2/pgphoto must
preserve the original request identity when available, and otherwise report a
distinct recovered/orphan output rather than mislabel it as the refused shot.
Add deterministic tests for both paths before any new firmware or shutter
test. No hardware behavior is claimed fixed by this inspection.

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/pentax-busy-after-sd-recovery-20260930-1604/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.

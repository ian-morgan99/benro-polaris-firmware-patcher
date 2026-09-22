# Polaris K-3 III shutter and thermal rescue handover — 2026-09-22

## Executive state

The original dirty worktrees were preserved. All rescue work is isolated and
pushed for review:

- patcher branch `rescue/shutter-thermal-20260922`
  - `499505547bfa16882dfedd063e07096523c43d22` — correlated Stage-2 capture return timing
  - `d02971e` — provenance rows through o-v12f
- libgphoto2 branch `rescue/shutter-observability-20260922`
  - `38d6e2fcb8b186580ba7bab9924f4fe8b4a81748` — observation-only capture boundaries
  - `7c60f8cbd3c1ee8733588d9a2410402ecd0b47cf` — publish finalized capture before invalid readiness gate, prevent duplicate delete, gate next shutter on recovery probe

Installed now: `6.0.0.54.16-o-v12f-shutterfix`, libgphoto2 `7c60f8cbd`,
patcher `4995055`. Runtime Stage-2 maps and matched stock/Stage-2 core+port
hashes passed.

## Decisive o-v12e diagnosis

K-3 III USB `25fb:0189`, exact matched stack, one physical exposure:

1. code 264 accepted the shot;
2. real `gp_camera_capture()` blocked for 63 seconds;
3. it emitted `The camera is still processing the capture; try again shortly.`;
4. it returned `GP_ERROR_CAMERA_BUSY (-110)`;
5. pgphoto logged `ARG_CAPTURE_IMAGE -110` and sent code 264 `state:-110`;
6. polestar mapped that to app `state:-1005`.

During that same 63-second wait, Benro successfully performed camera identity
and config reads about ten seconds after exposure. Therefore the current
GetAllConditions activity predicate is not a valid capture API-completion gate
on this K-3 III. This is the first complete mechanical mapping of `-1005`.

Evidence: `docs/evidence/o-v12e-shutter-diag-2026-09-22/`, especially
`capture-shot1.log` and persistent `Clog_000130.log` around line 10715.

## o-v12f result

o-v12f separates completed-file publication from readiness for a *later*
shutter. It also clears local candidate ownership after successful
DeleteTransferCandidate so `out:` cannot finalize the same candidate twice.

Three-shot acceptance run:

- shot 1: **PASS** in about 2 seconds; lifecycle `[1,4]`; real file event 773,
  `/app/sd/normal/SP_0062.jpg`, 208,575 bytes; real `gp_camera_capture()` returned
  0 in one second; camera filename `IMGP3585.JPG`.
- shot 2 after 10 seconds: **FAIL SAFE** before exposure; recovery probe returned
  `-110` in 0 seconds, mapped to `-1005`; no evidence of a second physical shot.

This proves the original 63-second completed-shot failure is fixed, but repeated
capture is not yet qualified. The next narrow task is to record the recovery
probe's raw GetAllConditions result, length and fields +32/+36/+104. Do not
weaken the unknown/pre-existing-candidate barrier. Determine which asserted bit
persists after a known-completed exposure and whether it represents actual
capture unsafety or a benign mode such as persistent Live View. Then update the
recovery predicate with a deterministic test and rerun >=3 consecutive shots.

Evidence: `docs/evidence/o-v12f-shutterfix-2026-09-22/`.

## Firmware artifacts

### o-v12e diagnostic (installed, superseded)

- private: `firmware-packets/o-v12e-shutter-diag-20260922/FwPkt.zip`
- zip MD5 `716c4e90b39ea4f917946025b3863d7d`
- zip SHA-256 `d2a6024def3c23cc9ba392bac78497b92feb63fafac99478f3a9fa8b532b3896`
- appfs MD5 `b77695dd8816324d8da469f272882611`
- private artifact commit `4ddf550`

### o-v12f shutter fix (installed; partial PASS, repeated-shot FAIL SAFE)

- private: `firmware-packets/o-v12f-shutterfix-20260922/FwPkt.zip`
- zip MD5 `9677a50dacc1a29668ea60afc2b54101`
- zip SHA-256 `6727ee628b434093745da7655fd746db79127ab3e5f47e6f5c81fb4ad471f81d`
- appfs MD5 `f5eefa15fb6a78a697e5dcacd116ef68`
- private artifact commit `b29197e`

Both were built from clean commits, passed package/manifest/ABI gates, uploaded
to PrivateResearch, registered before staging, and installed through the full
extracted `/app/sd/FwPkt` boot-watcher flow. No runtime files were edited over SSH.

## Camera heat / Live View result

Static audit proves a real workload difference:

- first successful Pentax preview enables camera PC Live View;
- Stage-2 forces `pentaxpclvkeep=1`;
- successful previews therefore leave camera-side Live View active;
- no normal UI-preview-idle/disconnect signal at this layer positively turns it
  off; normal stop ownership is error/capture/session teardown or process restart.

During firmware staging, with the camera on and preview restored, transfer rate
fell to roughly 2 MB/min. Sending preview OFF improved it sharply; with camera
off, the next full compressed firmware tree transferred in about 32 seconds.
This proves significant competing preview traffic, not thermal causality.

Per issues #67/#123, do not set `pentaxpclvkeep=0` globally and do not add a
Stage-2 timer. The correct fix remains demand-owned Live View in the persistent,
serialized pgphoto session scheduler: consumer count, session generation,
monotonic grace, explicit STOP_LV on last consumer, and restore after capture
only if a consumer remains. A controlled connected LV-OFF vs LV-ON/no-fetch
thermal A/B is still required.

## Qualification status

- Provenance/install/runtime loader: **PASS**.
- Original shot-1 63-second `-110/-1005`: **FIXED on o-v12f**.
- First JPEG publication: **PASS**.
- Second shutter after 10 seconds: **FAIL SAFE / NOT QUALIFIED**.
- Parameter config pass-through: retained from #129; not requalified after o-v12f.
- Preview restore: **PASS** after test cleanup.
- Camera-already-ON startup (#121): **NOT TESTED on o-v12f**.
- K-1 II and Canon R5 Mark II regression: **NOT TESTED**.
- Thermal causality and demand-owned LV implementation: **NOT TESTED / NOT IMPLEMENTED**.

Do not label o-v12f release-qualified. It is the newest evidence-backed
candidate and private recovery artifact.

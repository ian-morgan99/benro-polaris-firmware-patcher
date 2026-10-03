# Current repository state

## 2026-09-30 resumed investigation and workspace convergence

**o-v15a: PHYSICAL FAIL / NOT RELEASE-QUALIFIED.** The later #149 review
supersedes the installation-only status below. The 14:43 accepted-shot crash
was on o-v13x (`6.0.0.54.43`); the later pre-shutter busy refusals were on o-v15a
(`6.0.0.54.44`). Do not attribute the earlier crash to v15a or equate a refused
request with a new exposure.

The IT2 source conflict is resolved: +32 is candidate availability, +36 is the
candidate selector (1 is a new-transfer sentinel), and +104 contains separate
shooting/processing bits. Both installed-lineage fbc2e7e65 and current df64a6330
production classifiers were exercised offline. They mislabel the logged
candidate fields as `capture-active`; the guard must remain closed. Safe orphan
recovery and durable publication acknowledgement are not yet implemented.
Direct-PC reproduction is waiting for physical K-3 III attachment; no new
firmware or camera command was issued in this investigation.

Continue from [the current handover](HANDOVER-PENTAX-STABILITY-20260930.md),
[the source audit](evidence/pentax-orphan-recovery-20260930/SUMMARY.md), and
[the workspace disposition](WORKSPACE-CONVERGENCE-20260930.md). The historical
sections below describe their collection time, not current readiness or next
steps.

## 2026-09-30 o-v15a diagnostic candidate deployed (no shutter test)

- User-authorized deployment of `o-v15a-pentax-crash-registers-20260930` used
  the documented extracted `/app/sd/FwPkt/` update path and `/sbin/reboot`.
  Polaris identity was verified before staging; all six SD payload files
  matched the registered `firmwareInfo` sizes and MD5s before reboot.
- After reboot, Polaris identity, `FwVer:6.0.0.54.44`, embedded libgphoto2 and
  patcher commits/build id, live process startup, Stage-2 environment, matched
  core/port/ptp2/usb1 hashes, loader diagnostic markers, and Pentax
  `25fb:0189` were verified.
- Read-only canary probe reports K-3 III `state=1`, `photoFormat=2`. No shutter
  was sent. This is deployment/runtime verification, **not a capture pass**;
  the candidate only adds crash diagnostics. Independent review is pending
  before a capture reproduction.
- Complete install transcript:
  `docs/evidence/o-v15a-pentax-crash-registers-20260930/INSTALL-VERIFICATION.md`.

## 2026-09-30 14:43 operator/device-time shutter-owner crash (o-v13x)

- User reported the camera battery was replaced at 14:40 and that OpenPolaris
  plus two Benro Connect clients were connected without a crash before the
  manual shot. The subsequent M-mode request `SP_0152` was logged at 14:43:03
  with `bulb:0`; Clog read `1/1000s`, RAW+JPEG, entered `gp_camera_capture`,
  passed Pentax preconditions (`PTP 0x2001`, 576 bytes), and got accepted
  `InitiateCapture` (`PTP 0x2001`). No candidate/transfer/publication completion
  is logged for that request.
- At 14:43:15 the firmware watchdog reported `pgphoto is exit,reboot it`. The
  persistent Stage-2 crash file's newest record is SIGSEGV PC/fault
  `0xb5600af0`. Mlog remained in capture state until `photo timeOut` at
  14:44:07. At 14:44:38 the camera still enumerated as `25fb:0189` and pgphoto
  was running again; no camera USB detach is established for this event.
- The full log bundle and integrity hashes are in
  [`pentax-shutter-crash-20260930-1443`](evidence/pentax-shutter-crash-20260930-1443/SUMMARY.md).
  The capture is credited to the user's manual request, not an agent canary.
  The three-client no-crash report applies to the interval before the shot; it
  does not explain the accepted-shot crash.
- The existing crash handler saves PC and fault address but omits ARM LR/SP,
  general registers, and the process maps, so this incident cannot be resolved
  to an exact function from the archived data. A crash-only Stage-2 diagnostic
  change now records those values and a bounded `/proc/self/maps` dump. It does
  not alter shutter/capture policy. ARM Stage-2 compilation and full offline
  patcher gate pass (16 deterministic container checks + 24 Python checks).
- This diagnostic change was built and installed as o-v15a after the initial
  evidence capture. It has not been independently reviewed or capture-tested.
  Preserve strict Pentax pre-shutter admission and unresolved-output blocking.
  Next: obtain independent review, then repeat one request-attributed M-mode
  shot and use the registers/mappings to identify and fix the actual crash
  before claiming shutter-cycle completion.

Clock note: operator/log times are preserved as device wall-clock labels.
At collection the device's `date -u` was about one hour ahead of host UTC, so
the device's UTC label is not treated as independently verified UTC.

## 2026-09-30 o-v13x-camlib-prep installed; physical capture pending

- Candidate `o-v13x-camlib-prep-20260930` is installed through the registered
  extracted `FwPkt/` SD tree and normal `/sbin/reboot` updater path. Device
  identity was confirmed before staging: active SSID `polaris_d13e86`, BSSID
  `48:E7:DA:D4:B5:73`, route to `192.168.0.1` via `wlp8s0`; pre-install
  `/app/FwVer` was `6.0.0.54.42`.
- The on-device SD tree began empty. Every one of the six payloads (camera
  config, uImage, rootfs, appfs, and both gimbal images) was recomputed after
  transfer; byte sizes and MD5s matched the candidate's `firmwareInfo`. After
  reboot, `/app/FwVer` is `6.0.0.54.43` and embedded provenance matches libgphoto2
  `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`, patcher
  `575d5d8b7e31ef2d82c9a8354e6e6a517a87576c`, and build id
  `6.0.0.54.43-o-v13x-camlib-prep-20260930` exactly.
- Runtime checks: `polestar_app` and `pgphoto.stage2ondisk` are alive;
  Stage-2 core and port are mapped from `/app/lib/stage2`; stock and Stage-2
  core MD5s both equal `4ef64d8950eee70d9200093286fb0f3b`, and port MD5s both
  equal `ad50e83594397aef48b63ed2375890cc`. The package's selected camlibs are
  only `ptp2,pentax`.
- Physical camera test is **pending, not passed**. At verification no Pentax
  (`25fb`) or listed UVC adapter was visible on USB, and Clog had no camera
  state report. No shutter was sent. Once the camera is attached and powered,
  run the bounded canary; do not interpret successful install/runtime checks as
  capture qualification.
- The no-camera canary preflight was subsequently run read-only on the verified
  Polaris route. 284/820 session handshake and 286 camera query completed;
  response was `manufacturer:none;model:none;state:-5;storage:0;photoFormat:0`.
  Probe ended normally and issued no 264 capture request. The full offline
  pre-release gate also passed (16 container checks, 24 Python tests; no package
  or live-shot gate was requested). Transcript:
  `docs/evidence/o-v13x-camlib-prep-20260930/NO-CAMERA-CANARY.txt`.
- This is not an iPolar or StarShoot enablement build: the iPolar compile check
  was skipped because libuvc headers were absent, StarShoot only had a prototype
  compile check, and neither is linked into libgphoto2. Plans and constraints
  are tracked on libgphoto2 #85/#86 and patcher #158/#159. The corresponding
  detailed install transcript is in
  `docs/evidence/o-v13x-camlib-prep-20260930/INSTALL-VERIFICATION.txt`.
- Artifact registry row is in `docs/FWPKT-PROVENANCE-CONTRACT.md`; candidate
  ZIP SHA-256 is
  `8d0baba6b40744a65a1cc8f6d519a02fd178c2dd960d0178fa5ab3a090905132`.

## 2026-09-29 latest failure and candidate — o-v13w context isolation

- **Confirmed physical failure on o-v13v:** with the Pentax attached and set to
  RAW+JPEG, the canary's first shutter was accepted by Pentax
  `InitiateCapture` (PTP `0x2001`), then pgphoto segfaulted about two seconds
  later in PTP progress-callback dispatch. Neither expected SP_0134 file was
  published. A retry was blocked by pre-shutter admission; it sent no shutter.
  This is the actual cause of the current `camera busy` symptom, not just an
  unexplained readiness timeout.
- The ARM core shows an invalid progress-callback context read from the shared
  per-camera `PTPData.context` while a capture was in flight. This strongly
  implicates context replacement across concurrent camera calls. It is a
  source-level diagnosis supported by the core, not yet physically confirmed by
  a passing retry.
- Fix is committed and pushed to libgphoto2 `main` at
  [`fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`](https://github.com/ian-morgan99/libgphoto2/commit/fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd).
  The shared pointer is removed; operation contexts are bound per thread and
  camera-data owner. Its regression test, clean production build, and full
  deterministic libgphoto2 set pass (14/14; host DTR/CTS-only no-ci test
  excluded by the canonical script).
- One candidate is built and privately uploaded: `o-v13w-context-isolation-20260929`
  (Benro display `6.0.0.54.42`). Provenance: patcher build SHA
  `aaa557f0764cc029672f63c159e953a9f8a6ee3b`, libgphoto2 SHA above, harness
  `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`; ZIP SHA-256
  `ef10cb69bd288de091ce91431203f52925a8836960c0b6463a84e2e9211b199f`, appfs
  MD5 `121114c8c58090bfa97fb8024bc31e4c`. Patcher gate 14 container + 24 Python,
  harness 62/62, package-content and firmwareInfo checks all pass. Registry row
  is in `docs/FWPKT-PROVENANCE-CONTRACT.md`; private artifact commit
  `83664a9d3`.
- **Installed and runtime-verified; physical test pending.** The extracted
  `FwPkt/` tree was staged by the documented tar stream, all six on-device
  camera/gimbal payload MD5s matched `firmwareInfo`, and `/sbin/reboot` invoked
  the normal watcher. After reboot `/app/FwVer` reports `6.0.0.54.42`, embedded
  provenance reports the exact intended source and build IDs, pgphoto and
  `polestar_app` are alive, Stage-2 resolves 64/64 slots, and `/proc/250/maps`
  shows the Stage-2 core/port. Stock and Stage-2 core/port and ptp2 copies have
  matching MD5s. The read-only probe reached 9090 but reports no camera
  (`state=-5`; no `25fb` USB device), so no shutter has been sent on this build.
  Physical acceptance requires a successful RAW+JPEG capture publishing both
  files, API completion and returned control, followed by a second successful
  capture with pgphoto alive. Harness/source success is not camera proof. Full
  crash trace and raw-log hashes are recorded in the
  `o-v13v-stage2-direct-20260929` evidence folder; raw device logs/core remain
  out of public git.
- The generated package build reports that the iPolar adapter compile check was
  skipped because this build image lacks libuvc headers; this Pentax stability
  candidate does not claim iPolar compile qualification. Track separately under
  #159.

## 2026-09-29 Stage-2 still-capture dispatch correction — committed, build next

- Read-only device identity after the camera battery replacement confirms the
  Polaris AP (`48:E7:DA:D4:B5:73`), route via `wlp8s0`, installed o-v13s FwVer,
  and a running pgphoto. The first check had no camera enumerated. After the
  user turned it on, USB `25fb:0189` appeared; the first no-capture probe saw
  transient `state=-5`, and one later no-capture probe returned K-3 Mark III
  `state=1`, storage 2, photoFormat 2. The USB supervisor logged a `none` to
  `1-1.2` identity transition and a pgphoto restart (budget `4/6`). No shutter
  was sent. Redacted summary and hashes of the locally preserved raw logs are in
  `docs/evidence/o-v13v-stage2-direct-20260929/live-read-only-20260929-1430/`.
- The o-v13s wrapper sets `STAGE2_CAPTURE_TRACE=1` by default. That routes every
  still capture through an extra Stage-2 function-call boundary, despite the
  Stage-2 loader policy and existing regression test saying still capture must
  remain direct-to-core by default. Patcher main [`b43fd40`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/b43fd40)
  makes the trace wrapper opt-in (`=1`) and direct dispatch the wrapper default
  (`=0`). Both the loader-slot and actual wrapper-default tests pass; the full
  offline gate is green (14 container + 24 Python checks).
- This corrects a concrete cross-layer integration mismatch and is a plausible
  contributor to the observed capture failure, **not a proven root cause**.
  The current o-v13s artifact remains unqualified. One candidate,
  `o-v13v-stage2-direct-20260929`, is now built from the exact clean main SHAs
  and uploaded privately. ZIP SHA-256 is
  `400d417c90a486ec15b9830b9773b8320b3693f0aa5a69259db126f92d428904`; appfs
  MD5 is `c658bd37c3e70a13ea5f8b4535d8ff97`. Exact extracted-package component
  hashes match the generated runtime bundle. Full deterministic gates and the
  harness pass. Independent review remains pending, but the operator explicitly
  authorized installation/testing and o-v13v has now been installed through
  the documented SD `FwPkt/` flow. Post-reboot `FwVer`, embedded provenance,
  and matched core/port runtime hashes verify the intended candidate. The live
  canary is currently blocked: no Pentax USB device is enumerated, control
  port 9090 refuses connections, and `polestar_app` is absent. No shutter was
  sent. Do not mark physically qualified; see the candidate evidence for the
  exact checks and observed Clog errors.
  Details: [candidate evidence](evidence/o-v13v-stage2-direct-20260929/SUMMARY.md).
- Restart-durable ownership for an accepted capture whose output is not yet
  visible is still an explicit design/test gap. Do not treat strict current-
  session libgphoto2 guards as durable across pgphoto process restart.

## 2026-09-29 o-v13v installation / live canary blocked

- Installed from the registered ZIP after verifying every staged camera and
  gimbal payload size/MD5 against `firmwareInfo`. Polaris rejoined on its
  verified BSSID and the installed build id, patcher SHA, and libgphoto2 SHA
  exactly matched the registry row.
- Both stock and Stage-2 copies of libgphoto2 core and port have matching MD5s;
  pgphoto maps the Stage-2 core and port. This proves runtime component
  selection, not successful Pentax capture.
- The canonical read-only canary probe returned `ConnectionRefusedError` for
  TCP 9090. At the same observation, USB had no `25fb` camera, `polestar_app`
  was not running, and Clog repeatedly logged `SP_sendMsg Fail ... code[295]`.
  No shutter was issued. Physical camera/control-path recovery is required
  before retrying any canary. Full evidence: `docs/evidence/o-v13v-stage2-direct-20260929/SUMMARY.md`.
- Operator then rebooted Polaris. Bluetooth wake and identity checks confirmed
  the same installed build on the Polaris AP; `polestar_app`, pgphoto, and
  ports 9090/8080 returned. The Pentax remains absent from USB and a read-only
  9090 probe reports `manufacturer:none;model:none;state:-5;storage:0;photoFormat:0`.
  No shutter has been sent; the remaining physical prerequisite is camera
  power/USB reconnection while Polaris stays on.

## 2026-09-29 latest artifact review: o-v13u BLOCKED; follow-up source work underway

- Do not install `o-v13u-output-obligation-20260929`. Independent review found
  unresolved output ownership across an ambiguous `InitiateCapture` response and
  pgphoto restart, plus missing production-lifecycle/restart tests. Its complete
  audit row and exact hashes are recorded in
  `docs/FWPKT-PROVENANCE-CONTRACT.md`; review details are in
  `docs/evidence/o-v13u-review-blocked-20260929/SUMMARY.md`.
- Follow-up libgphoto2 fix is committed to `main` as
  [`718019fa0bb579cc5e8277ff2fa1f998a0fd37b4`](https://github.com/ian-morgan99/libgphoto2/commit/718019fa0bb579cc5e8277ff2fa1f998a0fd37b4).
  It requires complete supported `+524` output-mode data before
  shutter, latches output obligation before dispatch, preserves ambiguity on
  transport failures, and refuses to delete a companion unless transfer,
  filename identification, and filesystem publication all succeed. Focused
  Pentax tests and host `ptp2.so` build pass. This source is **not** in o-v13u.
  Durable recovery across pgphoto restart and production lifecycle/restart
  tests remain open; no candidate is cleared for installation.
- Camera battery replaced by user. At 2026-09-29 13:39 BST, Polaris identity was
  verified by BSSID `48:e7:da:d4:b5:73`, Wi-Fi route via `wlp8s0`, and FwVer
  `6.0.0.54.35-o-v13s-preserve-pending`; the K-3 III was enumerated as USB
  `25fb:0189`. No shutter was issued after that check. The current installed
  build is still the previously captured o-v13s, whose canary failed.

## 2026-09-29 recovery-path candidate: o-v13t (SUPERSEDED; do not install)

- **Built and package-gated; not installed.** This is one instrumented candidate
  to mitigate the distinct Pentax failure paths, not a declaration that the
  camera defect is fixed. The immediately preceding installed o-v13s canary
  failed and may have left camera-side output unresolved; do not install or
  fire another shutter until the prior physical session is safely resolved.
- Libgphoto2 source: `f05f6582662997975676d434015b08e20e83100e` (`main`, clean).
  Patcher source: `94c4882721607460242dffb2e49286c9b81bf21c` (`main`, clean).
  Build id `6.0.0.54.39-o-v13t-strict-admission`; selected camlibs `ptp2,pentax`.
- Per-path behavior: every shutter now passes the same strict pre-shutter
  admission check; unsafe activity, active exposure, unresolved candidate and
  unreadable PTP conditions have distinct reasons/actions; failed initiation
  is reported and never replayed; candidate output is preserved when ownership
  is unresolved. Recovery guidance is in `docs/PENTAX-CAPTURE-RECOVERY.md` and
  libgphoto2 `docs/pentax/CAPTURE-RECOVERY.md`.
- Tests: fresh libgphoto2 production/regression build 13/13 (the no-CI
  serial-control fixture is excluded); patcher full offline gate 14 container
  + 24 Python checks; package gate 4/4; production `ptp2.so` build passed.
  Final ZIP appfs was extracted and `ptp2.so`, both libgphoto2 cores and
  `pgphoto` byte-hash matched the generated runtime bundle. StarShoot adapter
  compiled; iPolar adapter compile-check was skipped because libuvc headers are
  unavailable. These tests do not prove Pentax camera behavior.
- Artifact: `out/o-v13t-strict-admission-20260929/FwPkt.zip`; MD5
  `1d49a01b8289db8811c75768b0224f7c`; SHA-256
  `e023d4e2b5f79946f2a3ee0173c7d067a4fdfe9ff4073ae0729383e3bb2a3cb9`;
  appfs MD5 `8a6ced8f9b78f5f1005c66ff9d12895e`. Uploaded to private
  `ian-morgan99/PrivateResearch` in commit `4a27c8b29`. Full row in
  `docs/FWPKT-PROVENANCE-CONTRACT.md`.

## 2026-09-29 latest candidate: o-v13s preserve unresolved Pentax candidate

- **Installed 2026-09-29; runtime identity verified; physical capture
  qualification pending.** The registered FwPkt was staged as the complete
  extracted tree on `/app/sd/FwPkt/`, every camera/gimbal payload MD5 matched
  on-device `firmwareInfo`, then the documented `/sbin/reboot` path was used.
  After the Polaris AP returned, `/app/FwVer` reported
  `6.0.0.54.35-o-v13s-preserve-pending` and the embedded provenance reported
  libgphoto2 `204c2a95a0da78135ad3c6dc244c230d5d16d2e9` and patcher
  `d11bc748f917a1705988596aa6acf565a7131c9a`. The Pentax K-3 III was present
  on USB; a non-capture probe returned the K-3 Mark III with `state=1`,
  `storage=2`, and `photoFormat=2`. **No shutter was fired.**
- Patcher source used: `d11bc748f917a1705988596aa6acf565a7131c9a` (`main`, clean
  at build). Embedded libgphoto2 source: `204c2a95a0da78135ad3c6dc244c230d5d16d2e9`
  (`main`, clean). Build selected `ptp2,pentax`.
- Change: on an error path, libgphoto2 now preserves a Pentax transfer candidate
  if it has actually discovered one and marks recovery required, instead of
  deleting that candidate as generic cleanup. The pre-shutter admission guard
  continues to refuse another capture while output ownership is unresolved.
- Limitation: this does not deliver a preserved image into Benro Connect, and
  it does not explain SP_0136, where no candidate/completion was observed after
  accepted `InitiateCapture`. The original failure cause remains unknown.
- ZIP MD5 `744815412b9acc51fba01fc0b01a782f`; SHA-256
  `6f02b20cb1d3e5f27ed99cb4b3f800adb4827dd65396d39fda7c188bb7d70b7b`; appfs MD5
  `889a34781e04edcfd11af38a432a46ee`. PrivateResearch commit
  `3b4693748244636ffe2aaaddd5be30893f790f0a` at
  `firmware-packets/o-v13s-preserve-pentax-candidate-20260929/FwPkt.zip`.
- Tests: canonical libgphoto2 regression build passed (no-CI serial fixture
  skipped); patcher gate 4/4 green; harness suite 62/62. Extracted appfs from
  the exact ZIP and byte-compared the pgphoto wrapper, Stage-2 runtime, core,
  port, ptp2, Pentax camlib, usb1 and provenance to the build bundle; all
  matched. Detailed transcript and hashes:
  [candidate evidence](evidence/o-v13s-preserve-pentax-candidate-20260929/SUMMARY.md).
- **Install completed:** documented extracted-tree install, all firmwareInfo
  MD5s verified before reboot, and runtime identity verified after reboot.
  Physical qualification is not complete; see the failed live canary below.
- Plan/status cross-posted to patcher #149 and libgphoto2 #73. No camera action
  or runtime mutation was performed for this build before installation. Install
  verification also confirmed that the wrapper's Stage-2 core/port and the
  stock-path core/port/PTP/USB modules have matching hashes; the process maps
  showing stock path names therefore refer to byte-identical candidate modules.
  The post-update read-only probe transcript is in the OpenPolaris workspace at
  `docs/evidence/firmware-update-2026-08-31/post-update-probes-20260929-123825/`.
  An unrelated older `/app/sd/FwPkt.zip` remains untouched; only the extracted
  tree is consumed by the updater.
- Installed/runtime-verified is not equivalent to capture-qualified. The first
  bounded live canary is recorded below as failed; do not retry until its
  unresolved camera-side state and missing diagnostic logs are handled safely.

### 2026-09-29 12:48 BST live canary — FAIL; no retry

- On the installed o-v13s, the official diagnostic canary was run once with
  the prior RAW+JPEG two-output contract. Identity and readiness preflight
  passed; the camera was enumerated as Pentax `25fb:0189`, and the installed
  FwVer/provenance matched the registry. The diagnostic request turned
  preview off successfully and sent exactly one capture request.
- Trace: lifecycle `state:1`, then terminal `state:-1005`; Mlog showed
  candidate path `/app/sd/normal/SP_0134.jpg`, then `state:-110` and
  `PHOTO_RECORD Fail`. No state 4/0 completion, code-773 publication, or
  `SP_0134` file was observed. The current mode/output count was not verified,
  so do not infer RAW-only vs RAW+JPEG from `photoFormat:2` or the single
  candidate name. The explicit terminal error makes this canary a FAIL
  independent of that ambiguity.
- Camera remained attached and process IDs unchanged in the read-only
  postcheck 8 seconds later; no USB disconnect was observed during the test.
  Mlog had rotated/cleared by postcheck. Clog did not expose the lower-level
  PTP cause, so the exact first failing camera transaction remains unknown.
- A later read-only probe at 12:52 BST still reported model K-3 Mark III and
  `state=1`; USB `25fb:0189`, pgphoto PID 250 and polestar_app PID 249 remained.
  This camera state is not proof that Pentax's stricter pre-shutter conditions
  (+32/+36/+104) permit another exposure. Kernel `dmesg` contains a USB reset
  entry but lacks a usable timestamp tying it to this canary; no disconnect
  entry occurred in the inspected interval.
- **No retry or second shutter was sent.** Preserve camera power/USB state and
  collect fuller camera/PTP logs before another physical capture. The
  source-supported leading hypothesis is a fail-closed recovery/admission guard
  refusing the request before exposure; a camera PTP DeviceBusy response is
  still possible. The captured trace does not distinguish them. Direct CLI
  ownership transfer or power cycling could erase a camera-side candidate, so
  neither is attempted without first securing logs and accepting that risk.
  Full trace and interpretation: [o-v13s live canary evidence](evidence/o-v13s-preserve-pentax-candidate-20260929/live-canary-20260929-1248.md).
- Code-side mitigation is now committed on libgphoto2 `main` as
  [`f05f65826`](https://github.com/ian-morgan99/libgphoto2/commit/f05f65826):
  every Pentax capture now passes the strict +32/+36/+104 admission gate;
  refusal reasons include a safe recovery action, and any failed
  `InitiateCapture` arms recovery without replay. Focused deterministic tests
  pass 3/3 and production `ptp2.so` builds. Full Meson: 12/14; the two failures
  remain host `test-gp-port` enumeration and this build's missing research-only
  model in `test-gphoto2`. **This commit is not packaged or installed.** The
  cross-layer per-path response is documented in
  [PENTAX-CAPTURE-RECOVERY.md](PENTAX-CAPTURE-RECOVERY.md).

## 2026-09-29 USB compatibility mode OFF capture failure — physical evidence

- Operator reports broad M-mode RAW+JPEG testing passed with the camera's USB
  compatibility mode ON. After switching it OFF, shots initially appeared OK,
  then Benro Connect reported shot failure / pause timeout / reconnect.
- Read-only Polaris logs show the nearby app connection transition at 11:02:15
  (`code 297 mode:1`, CableRelease; camera absent/state 0), then 11:02:22
  (`code 297 mode:0`, USB) and camera returned as K-3 III by 11:02:29. This is
  an app camera-control/connection transition, **not a direct readback of the
  camera's USB compatibility menu setting**. The operator should confirm
  whether this timestamp matches the OFF change.
- Captures `SP_0125`–`SP_0133` did complete as RAW+JPEG pairs; the prior
  snapshot saying a second shot was not confirmed is superseded by these
  subsequently flushed persistent logs and files. Last confirmed pair
  `SP_0133` published at about 11:02:38.
- First failure: request for `SP_0134` at 11:03:55. At 11:03:59 PTP
  `InitiateCapture` returned `0x2001` (accepted), but there is no subsequent
  completion event or output transfer/publication. At 11:04:11 Polaris logged
  pgphoto exit and restarted it. The app capture window was cancelled at
  11:04:28 and reported failure. Lighttpd starting at 11:04:39 plus uptime
  near three minutes at 11:07:58 indicates a Polaris OS reboot around then;
  the exact trigger is not established by retained logs.
- Retries `SP_0134`/`SP_0135` were rejected before another shutter because an
  unclaimed transfer candidate remained (`GP_ERROR_CAMERA_BUSY`, -110, mapped
  by Polaris to -1005). This is the safety guard working: it avoids deleting
  an unresolved possible output or issuing an unsafe next exposure. A later
  `SP_0136` InitiateCapture was accepted but again produced no confirmed pair,
  followed by another pgphoto exit/restart at 11:05:44.
- **Conclusion:** the direct observed failure is after shutter-command
  acceptance but before capture completion/output reconciliation; it is not
  evidence that `InitiateCapture` itself was rejected. USB compatibility OFF
  is temporally correlated, not proven causal: the menu bit is not logged, and
  this trace alone cannot distinguish camera/PTP behavior from Polaris session
  supervision. No code, configuration, or camera state was changed for this
  diagnostic pass; no shutter was sent by the investigator.
- Detailed raw-log analysis is in patcher issue #149 comment
  [`5888131739`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5888131739).
- A later monitored Benro Connect request `SP_0137` (11:21:35) failed before
  shutter dispatch because the unresolved candidate from the prior operation
  remained: Clog says `unclaimed transfer candidate (1)` and `captureImage ret
  -110`; Mlog says `PHOTO_RECORD Fail`. There is no `InitiateCapture` for
  `SP_0137` and no output file. At the post-request check the camera was still
  USB `25fb:0189`, pgphoto PID `1585`, and uptime was advancing. This attempt
  therefore does **not** independently reproduce USB-compatibility-OFF camera
  semantics; no retry was sent.
- Monitoring caveat: an investigator's first polling loop opened SSH every
  five seconds for about two minutes. Broadcom Wi-Fi pool errors in `dmesg`
  rose from 864 matching lines in the earlier snapshot to 1668 afterward.
  The correlation is strong but does not prove causality; high-frequency
  polling was stopped and must not be treated as neutral test instrumentation.
  See issue #149 comment
  [`5888297233`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5888297233)
  and local evidence folder `docs/evidence/usb-compat-off-2026-09-29/`.

## 2026-09-29 authoritative alignment checkpoint

This entry supersedes older "current" labels and adapter status statements
below. Historical evidence remains intact; do not treat old headings as a
statement of today's installed firmware or source state.

### Decision

- **General firmware release: NO-GO.** The production Benro Connect matrix is
  incomplete and Astro/other workflows have failed in field reports.
- **Next step: scoped Pentax diagnosis/qualification only.** Do not roll back
  the codebase wholesale to v10 and do not combine iPolar/StarShoot, version
  display experiments, or new default-on instrumentation into this test.
- Keep v13j's direct-owner two-shot PASS as a narrow reference only. It does
  not prove Benro Connect, Astro, Panorama, timelapse, Bulb, reconnect, or
  cross-tester reliability. The initially unknown installed state was later
  identified in the live preflight below.
- **No firmware ZIP was built** from this checkpoint. The astronomy adapters
  are not linked to a working Polaris camera-source runtime, so a combined
  packet would overstate support.

### Initial physical/device preflight before Pentax connection (2026-09-29)

- User held the Polaris awake with an Apple device. The host joined the exact
  Polaris AP (`48:E7:DA:D4:B5:73`, `polaris_d13e86`); route to `192.168.0.1`
  was verified over Wi-Fi (`wlp8s0`), and SSH confirmed the gimbal identity.
- Installed firmware is `6.0.0.54.34-o-v13j-crash-boundary`; on-device
  provenance identifies libgphoto2 `e6cc1f8c8eeb95e4a9cb1652e804b9488167c4a4`,
  clean, and build-time patcher `890d29d69fef7042875fbb58ba67215d7b696f24`.
  The active pgphoto process maps the Stage-2 core/port; stock and Stage-2
  core MD5s match (`390194dd561de4bde4eb7ed701401507`).
- **Camera is absent from the Polaris USB bus:** on-device enumeration shows
  only root hub + hub, no Pentax `25fb:*`, StarShoot `16c0:29a0`, or iPolar
  `1233:1455`. The StarShoot seen on host `lsusb` is attached to the PC, not the
  gimbal. No shutter/capture canary is allowed until the intended camera is
  connected and seen on-device.
- Persistent logs exist as `Clog_000168.log` (~5.1 MB) and `Mlog_000168.log`
  (~162 KB). The inspected tail has repeated Stage-2 loader-init records; the
  searched tail had no SIGSEGV/crash marker. Mlog records an Apple device named
  `iPad` disconnecting at 10:11:09; do not assume it is the iPhone the user
  mentioned. One read-only 9090 camera-info request returned no response, so
  it is not a state/READY result.
- Detailed host route, firmware provenance, component hashes, process IDs,
  USB list and observations are recorded in patcher issue #149 comment
  [`5887230099`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887230099).

### 2026-09-29 live recheck — Pentax attached, pre-canary

- After the user powered the camera, the Polaris enumerated `25fb:0189`
  (Pentax K-3 Mark III). Current FwVer remains
  `6.0.0.54.34-o-v13j-crash-boundary`.
- A fresh official probe-only run (`scripts/canary-probe.py --probe`) passed:
  model `pentax k-3 mark iii`, `state:1`, `storage:2`, `photoFormat:2`.
  The latest Clog records preview `get-frame returned 0x2001` with 66,919 bytes
  in 17 ms; latest Mlog reports camera `state:1` and refreshed ISO/shutter/
  aperture/EV/WB controls. This is a readiness/probe result, not a capture.
- The first attempted release-gate command omitted `--expected-files`; it
  exited 2 during argument validation **before tests or shutter dispatch**.
  The canary script explicitly says `photoFormat` is not authoritative for
  output count, so do not guess from `photoFormat:2` or older RAW+JPEG runs.
- The initial gate invocation omitted `--expected-files` and exited 2 before
  tests or shutter dispatch. User then independently confirmed Benro Connect
  was set to RAW+JPEG, allowing a two-output canary contract.

### 2026-09-29 one-shot RAW+JPEG canary — output PASS, stability inconclusive

- Ran `./tests/run_prerelease_gate.sh --canary --expected-files 2` with the
  documented 9090 keepalive. Deterministic gate: 14 container + 24 Python
  checks passed. Device probe reported Pentax K-3 III `state=1`. The canary
  command returned PASS with capture lifecycle `[1,4,0]` and two distinct
  publications sharing stem `SP_0121`: `/app/sd/normal/SP_0121.dng` (34,047,294
  bytes) and `/app/sd/normal/SP_0121.jpg` (398,175 bytes). Clog confirms the
  original `IMGP3664.DNG` and `.JPG` were fetched and deleted from the camera
  after successful transfer; Mlog confirms both Polaris album saves returned
  `ret 0`. This proves one RAW+JPEG capture/publication on the diagnostic 9090
  path, not Benro Connect workflow qualification. No package gates ran (no
  `--build` supplied).
- The subsequent kernel log records `usb 1-1.2: USB disconnect, device number
  3`, then the same Pentax `25fb:0189` re-enumerating as device 4; `pgphoto`
  changed PID from 31853 to 3416. The operator clarified that they deliberately
  unplugged/reconnected the camera to inspect it, and that the camera battery
  is low. Therefore these observations are consistent with that manual
  reconnect / low battery and are **not evidence of a capture-induced crash or
  firmware instability**. The timing does not isolate whether a battery drop
  also occurred. No SIGSEGV or crash artifact was found, but no uninterrupted
  post-capture stability interval was established either.
- Kernel log also records Broadcom `Out of tdata_disc_grp` and `No more free
  tdata_psh_info!!` around this period. Their relationship, if any, to the
  manual reconnect or low battery is unknown; do not attribute them to the
  capture from this run.
- **Interpretation / next step:** one RAW+JPEG capture and publication passed
  on the diagnostic 9090 path. Benro Connect end-to-end behavior and stability
  while the camera remains continuously attached are still untested. Avoid
  another shutter while battery is low; when convenient, use a charged battery
  and leave the camera connected for one bounded post-capture observation.
- Gate transcript was `/tmp/prerelease-canary-shot.log` on the host for this
  session. The initial pre-canary state is in issue #149 comments
  [`5887230099`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887230099)
  and [`5887296032`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887296032);
  the operator clarification and corrected interpretation are recorded in
  [comment 5887409720](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887409720).

### 2026-09-29 post-battery-change RAW+JPEG canary — PASS, short continuity PASS

- Operator replaced the camera battery and performed their normal camera
  power cycle. The resulting new USB enumeration/PID is expected and is not
  classified as a crash. Polaris identity was freshly verified (AP BSSID
  `48:E7:DA:D4:B5:73`, route via `wlp8s0`, expected FwVer); camera appeared as
  USB `001:005`, Pentax `25fb:0189`, and `pgphoto` PID `11103`.
- Probe-only state was K-3 III `state=1`, `storage=2`, `photoFormat=2`; the
  operator's established RAW+JPEG selection supplied the two-file obligation.
- Ran `./tests/run_prerelease_gate.sh --canary --expected-files 2` with the
  documented 9090 keepalive. Result: 14/14 container checks and 24/24 Python
  checks passed; probe and one-shot canary passed; summary `4 passed, 0 failed,
  0 skipped`. Lifecycle `[1,4,0]`; outputs were
  `/app/sd/normal/SP_0122.dng` (34,439,136 bytes) and
  `/app/sd/normal/SP_0122.jpg` (382,354 bytes). This validates the diagnostic
  9090 path, not a Benro Connect app-path capture. No `--build` package gates
  ran.
- Without any camera unplug/power action after this capture, a read-only check
  about 86 seconds later still saw USB device `001:005` and the same pgphoto
  PID `11103`; Polaris AP/route and SSH remained available. This is a short
  post-capture continuity PASS, not a long soak or full production-app
  qualification.
- Host `bluetoothctl info 48:E7:DA:D4:B5:72` reported `Connected: no`. Thus
  the observed keepalive/continuity used Wi-Fi/9090, and PC-side Bluetooth
  keepawake remains unproven. Do not confuse a one-shot BT wake pulse with a
  retained BT connection.
- The next Benro Connect test was completed below; the original checkpoint is
  cross-posted to [issue #149 comment
  5887707654](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887707654).

### 2026-09-29 Benro Connect single RAW+JPEG shot — PASS, short continuity PASS

- Operator triggered one ordinary shot in Benro Connect with the camera left
  attached. Mlog shows the normal app/client request (`type 2 code 264`) at
  10:54:36 device time, `numOfCaptureImage 2`, and libgphoto2 `InitiateCapture`
  returning PTP `0x2001` success. Lifecycle progressed to state 4
  (`IMGP3667.JPG`), state 2, both state 3 file publications, and terminal state
  0 at 10:54:43.
- Polaris published matching stem `/app/sd/normal/SP_0124.dng` (34,256,105
  bytes) and `/app/sd/normal/SP_0124.jpg` (381,093 bytes). This is a
  Benro-Connect-path single-shot RAW+JPEG output PASS.
- At 10:55:40, without unplug/power action, Polaris Wi-Fi route remained on
  BSSID `48:E7:DA:D4:B5:73` via `wlp8s0`; Pentax remained USB `001:005`,
  `polestar_app` PID `248`, and pgphoto PID `11103`. This gives approximately
  57 seconds of post-completion continuity, not a long soak or repeated-shot
  qualification.
- No `--build` package gates were part of this physical test. PC-side Bluetooth
  still reported disconnected; the measured continuity used Wi-Fi. Full
  evidence is in [issue #149 comment
  5887882260](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887882260).
- **Second-shot report, not yet confirmed by Polaris evidence:** the operator
  reported taking a second Benro Connect shot. At device time 10:58:02, however,
  neither live nor persistent Mlog contained a new type-2/code-264 capture
  request after the 10:54:36 request, and `/app/sd/normal` contained only the
  `SP_0123` and `SP_0124` pairs (no `SP_0125`). The newest persistent Mlog
  entries were periodic status events through 10:57:13. This does not establish
  whether the physical shutter fired or what Benro Connect displayed; classify
  the reported second shot as NOT CONFIRMED, not as a proven camera failure.
  Camera stayed USB `001:005`, pgphoto PID `11103`, and Wi-Fi/SSH remained
  reachable. No additional shutter was sent. Await the operator's observation
  of the app result / physical shutter before attempting another capture.
- This evidence is recorded in [issue #149 comment
  5887921040](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5887921040).

### Canonical source heads (all local worktrees clean and equal to origin/main
when checked)

- Firmware patcher: `e1502e083e0d7c4eeb62bb5143e4c3b7b5234acd`
- libgphoto2: `f7425744004edff3bb33fe4b7d955ee907a24ac3`
- benro-polaris-test-harness: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`
- OpenPolaris: `161ac2d9c661ff24397f49646fab5ea0c61a4378`

### What is fixed vs what is still unproven

- libgphoto2 main removes the measured StarShoot `16c0:29a0` from the UVC
  inventory and tests the classification. This is not a StarShoot driver.
- Patcher `e1502e0` hardens iPolar frame publication (validated lengths,
  immutable leased slots, reconnect generation invalidation) with a passing
  deterministic test. This fixes the buffer-safety review finding, not the
  complete iPolar camera-source integration.
- StarShoot is measured as vendor-specific USB, not UVC. Available QHY SDK
  enumeration did not find the attached unit; the available ARM SDK binary is
  ABI-incompatible with Polaris. No StarShoot frame has been proved.
- Neither astronomy adapter is linked into the shipped Polaris camera runtime
  or connected to a working common frame consumer. Do not claim support or
  include them as functioning features in a release.

### Immediate execution plan — one owner at a time

1. **Read-only identity preflight before any physical test:** record installed
   `FwVer`, package/provenance identity, active camera USB identity, process
   identity and current logs. Never infer installed state from a filename or
   prior chat. Preserve logs before restarting anything.
2. **Reproduce the smallest Benro Connect failure** on that exact installed
   build: one ordinary capture, then only the minimal Astro sequence known to
   trigger the fault. Keep capture trace observational/default-off unless the
   exact diagnostic candidate and its provenance are already identified. On
   any incomplete capture, process replacement, USB loss, or missing output,
   stop: send no subsequent shutter. Save app logs, Clog/Mlog, Stage-2 crash
   record, PIDs, USB identity, and timestamps.
3. **Classify the first divergence** as Connect/client, Stage-2/pgphoto, or
   libgphoto2/PTP before editing. Implement one minimal fix in that owning repo
   and add a deterministic regression before rebuilding.
4. **Run in order:** libgphoto2 suite; patcher deterministic/release gate;
   harness contract tests; package/link/ABI/provenance assertions; only then
   the bounded physical reproduction. No later layer may mask a lower-layer
   failure.
5. **Expand physical qualification only after the first failure is repaired:**
   startup already-on and OFF->ON; config/AF; repeat JPEG, RAW, RAW+JPEG;
   Live View->capture->restore; Astro 5x1s; Panorama; timelapse 5s x10; then
   Bulb and battery/power-cycle rebind. Record PASS/FAIL/NOT TESTED separately.
6. **Keep astronomy support independent:** iPolar requires attached-device
   Y16 frame proof and common frame-consumer/solver/package integration.
   StarShoot requires a compatible protocol/driver, handshake and real-frame
   proof. Only after both pass their own hardware and package gates may a
   combined candidate be built.

### Preservation / handoff rules

- This file plus patcher issue [#149](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149)
  are the shared plan for Codex, the local AI and external reviewer. Start
  there; append evidence rather than replacing previous conclusions.
- Before changing source, verify branch/status and save unrelated work in a
  named, recoverable commit or stash. Never drop stashes, archive tags, old
  candidates or raw evidence as cleanup. Do not force-push or rewrite a
  published candidate.
- Every firmware packet must follow the release skill and provenance registry.
  A successful source build is not proof that intended binaries are linked in
  the packet. This checkpoint produced no firmware artifact; do not install a
  packet for the combined camera-support objective until the required
  build/package and runtime-consumer gates pass.

Plan and status cross-posted to #149 in comment
[`5886879450`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149#issuecomment-5886879450).

## 2026-09-29 adapter hardening (o-v13p) — post-release fixes, awaiting TA guidance

Follow-up audit of the o-v13o adapter work found and fixed:

- **iPolar (#159):** `uvc_find_device` takes a reference on the returned device
  (verified in libuvc 0.0.8 source; upstream example calls `uvc_unref_device`
  after `uvc_open`) — the adapter now releases it, so no ref leak per open.
  Frame callback guards a missing sink buffer; streaming state is tracked so
  `close()` only stops an active stream and `stream_y16()` is idempotent.
- **StarShoot (#158):** `starshoot_adapter_stream_bulk_iso()` now returns the
  bounded handshake transfer result (0 / negative libusb code) instead of void,
  making the TA's hardware discriminator observable without a device on the bench.
  Opcode values re-verified against `Temp/qhyccdcamdef.h`.
- Both adapters compile clean with patch.sh flags (zero warnings); full symbol
  export verified via `nm`; offline gate GREEN.

Awaiting TA guidance on next step: hardware discriminator for #158 (handshake +
one frame from the attached 16c0:29a0) and linking the adapters into the stage2
build for a combined Pentax+UVC candidate.

## 2026-09-29 TA review response: adapter consolidation + bounded lifecycle

Technical architect comments on #158/#159 (2026-09-28) were addressed in the
working tree:

- **Consolidation:** removed the duplicate `container/stage2_qhy5lii_adapter.{h,c}`
  created earlier this session. The canonical #158 adapter is
  `container/stage2_starshoot_adapter.{h,c}` (build-wired via
  `container/patch.sh:426`; the file the TA reviewed by name). Both targeted
  `16c0:29a0`; only starshoot was referenced by any build path.
- **#158 bounded lifecycle (TA requirement):** `starshoot_adapter_open(vid,pid)`
  now enumerates, matches VID/PID, opens, claims interface 0 and selects alt
  setting 1; new `starshoot_adapter_close()` releases the claimed interface +
  handle; `ss_transfer_opcode()` provides bounded vendor control transfers with
  libusb error codes; `stream_bulk_iso()` issues the `IS_CAMARA_INIT` handshake.
  All paths fail-closed. Still owed per TA: hardware discriminator (handshake +
  one frame from the attached 16c0:29a0) — needs the device on the bench.
- **#159 per TA direction:** iPolar adapter now has a bounded Y16 frame sink
  (fixed buffer, monotonic generation identity), `reconnect()`,
  `set_exposure()`/`set_gain()` controls and `latest_frame()` for the common
  camera-source interface. No iPolar-specific polar-solving stack; the solver
  stays source-agnostic (`iPolar -> UVC/libuvc frame -> common camera-source
  frame -> plate solve -> polar-axis error`).
- **Compile status (patch.sh flags, zero warnings):** starshoot
  (`gcc -c -fPIC -O2 -std=gnu11 -Wall -Icontainer -I/usr/include/libusb-1.0`)
  and iPolar (`... -I/work/src/libuvc/include -I/work/src/libuvc/build/include`)
  both PASS. `patch.sh` iPolar check updated to include the CMake-generated
  `libuvc_config.h` root. libuvc 0.0.8 notes: Y16 = `UVC_FRAME_FORMAT_GRAY16`;
  device lookup via `uvc_find_device` (opaque `uvc_device_t`).
- **Classification:** both adapters remain skeleton/interface work until the
  hardware discriminator passes and the adapters are linked into the stage2
  build. o-v13n is still NOT a combined Pentax+UVC candidate.

## 2026-09-29 candidate: o-v13n

`o-v13n-main-pentax-display-20260929` is **BUILT, PRIVATELY PUBLISHED, AND
PACKAGE-GATED; AWAITING INDEPENDENT REVIEW BEFORE STAGING; NOT INSTALLED OR
PHYSICALLY QUALIFIED**. It uses patcher
`7c514e328` and libgphoto2 `4bdbc75eb`. The package and appfs FwVer are set to
`6.0.0.54.22`; the build identity `6.0.0.54.38-o-v13n-main-pentax-display`
is separately recorded in provenance. Connect's actual displayed version is
not yet verified.

The test failures encountered during packaging were addressed at their owners:
NULL directory append no longer crashes libgphoto2, its filesystem regression
test now passes in the deterministic suite, and the host Meson setup includes
the Directory Browse camlib required by its generic camera test. The serial
DTR/CTS test remains an explicit `no-ci` hardware prerequisite skip. Results:
libgphoto2 12/12 deterministic tests, patcher 13 container + 24 Python tests,
and package structure/firmwareInfo gates all PASS. Package contents were
extracted and byte-compared with the built Stage-2 bundle.

Adversarial recheck on 2026-09-29 reproduced the package gate (4/4), libgphoto2
tests (12/12), and harness (62/62), and verified all 11 embedded Stage-2 files
against the candidate build bundle and the PrivateResearch ZIP hashes. Raw
transcripts are in the candidate evidence directory. Caveat: Benro Connect's
version comparator handles exactly four dot-separated numeric fields; this
five-field display value returns “no update” in that comparator. This is an
experimental version-display candidate, not verified as neutral to app-based
upgrade checks. Do not use Connect's firmware-update flow for it.

Scope audit: the adapter sources at the recorded 13n patcher commit fail the
standalone compile checks, and neither adapter is part of 13n's packaged
runtime. Newer, still-uncommitted working-tree edits pass ARM object compilation
when local QHY SDK/libuvc inputs are mounted, but the QHY object exports no
symbols and iPolar retains an unresolved `uvc_init`; open/stream remain stubs.
The trace is in `evidence/o-v13n-main-pentax-display-20260929/`. Therefore 13n
is not a combined Pentax+UVC candidate and must not be installed for QHY/iPolar
testing. No installation is planned on this evidence.

Artifact hashes and the remaining physical acceptance matrix are in
`evidence/o-v13n-main-pentax-display-20260929/SUMMARY.md`; the registry entry
is in `FWPKT-PROVENANCE-CONTRACT.md`. v14 is unchanged. Earlier scenario gaps
remain open until exercised against this identified candidate.

## 2026-09-28 one-off scenario audit

The latest source-main package `o-v13m-main-pentax-uvc-20260928` is build and
offline-gate valid but remains **NOT INSTALLED / NOT PHYSICALLY QUALIFIED**.
Evidence in `evidence/o-v13m-main-pentax-uvc-20260928/SCENARIO-AUDIT.md`
shows earlier K-3 III RAW+JPEG and limited Astro-equivalent passes, but no
current-package proof for JPEG-only, RAW-only repeatability, native Astro,
Panorama/Pro Panorama, or a successful complete Pixel Shift output set.
Pixel Shift remains specifically unqualified: the recorded v12h experiment
was incomplete and v12m crashed after publishing its two outputs. Do not claim
the current package works across all scenarios or formats until that matrix is
run against an identified installed build.

This is the concise entry point for agents and maintainers. Read it before
searching historical handovers or raw evidence.

## 2026-09-28 current candidate: o-v13i (session-recovery)

`o-v13i-session-recovery-20260927` is **INSTALLED, RUNTIME-VERIFIED; stale-session
rebind works; capture canary FAILED (active-owner defect)**. In plain English: the
replacement `pgphoto` process now recovers from a retained Pentax session
(`0x02fa`/`0x02fd`/`0x02ff` -> ordered close/reset/reopen, libgphoto2
`e6cc1f8c8`), but the ORIGINAL capture owner is still terminated/replaced after an
operation that fails to complete. Next investigation boundary: the
pgphoto/polestar watchdog decision and the first blocked/failed production
operation before replacement. Do not add another USB retry or claim the capture
fixed.

Provenance: build id `6.0.0.54.33-o-v13i-session-recovery`, patcher `0746ed3`,
libgphoto2 `e6cc1f8c8`, harness `0355f6f64`. Full evidence and the remaining
physical acceptance (two-capture test after the active-owner fix) are in
`evidence/o-v13i-session-recovery-20260927/SUMMARY.md`.

## 2026-09-27 current candidate: o-v13g

`o-v13g-linked-publication-20260927` is **INSTALLED, RUNTIME-VERIFIED, AND
K-3 III RAW+JPEG TWO-SHOT PASS**. In plain English: the package crash found in
version F is fixed; one bounded capture passed, then two consecutive captures
also passed with distinct outputs and without issuing the next shutter early.
The bounded Preview-on, suspend, capture, and Preview-restore sequence also
passed with a complete RAW+JPEG output pair.

The installed build embeds libgphoto2 `8601460b3` and patcher `93e1898`, build
id `6.0.0.54.31-o-v13g-linked-publication`. Version F had omitted
`pentax-publication.c` from the Automake build and therefore crashed before
`InitiateCapture` on an unresolved helper. The source inclusion is corrected
and the patcher now rejects any package with unresolved internal `pentax_*`
symbols. Full provenance, hashes, install proof and physical results are in
`evidence/o-v13g-linked-publication-20260927/SUMMARY.md`.

This is a convergence candidate, not yet a blanket release qualification.
The separate #146 reconnect/rebind and external-change matrix, #147 Preview
interactions, #148 long-exposure/cancellation work, and unavailable regression
cameras remain explicit follow-on gates.

## 2026-09-27 restored-fixes candidate

`o-v13e-restored-fixes-20260927` is **BUILT, PRIVATELY PUBLISHED AND
PACKAGE-GATED; NOT INSTALLED; LIVE CANARY PENDING**. In plain English: the
missing Pentax fixes have been restored into one clean libgphoto2 line and the
resulting firmware package is internally consistent, but this exact package
has not yet been put on the Polaris or exercised against a camera.

The candidate embeds libgphoto2
[`564bdd070`](https://github.com/ian-morgan99/libgphoto2/commit/564bdd070cec3f4a366444a7d7e95605f90e30f3)
from PR [libgphoto2#94](https://github.com/ian-morgan99/libgphoto2/pull/94),
patcher `96b75902aae4473bfb7be56195fb3f9a079d73a9`, and harness
`a8b65817354dae04f997d1357d7d4914e396c42f`. It restores strict-only
pre-shutter admission, production-path publication ownership and deletion
semantics, exact long-exposure labels (for example 80s/90s rather than 1m/2m),
timeout restoration on every abnormal exit, and timeout-phase diagnostics.
It packages both `ptp2` and legacy `pentax` camlibs; this does not provide the
separate V4L2/UVC implementation needed by iPolar or Orion StarShoot.

Deterministic results: four focused Pentax production-path tests PASS;
firmware-patcher offline gate PASS (13 container + 24 Python); test harness
PASS (62/62); built-package gate PASS (13 container + 24 Python + structure +
firmwareInfo). The broader libgphoto2 Meson run was 10/13: the three failures
are existing environment/baseline failures (`test-gp-port`, generic-model
`test-gphoto2`, and `test-filesys` SIGSEGV), not suppressed green results.

Artifact: `out/o-v13e-restored-fixes-20260927/FwPkt.zip`; MD5
`5a3ae51583b4a46c02fd8120314a2bca`; SHA-256
`4b7982e28e361f0669eedc61103e75f16a3101af0e47d79c3fdf500a65631c8d`;
appfs MD5 `f8e70314b4bf9c25d12ff4eaba16a4b9`. Private artifact commit:
`ac518690b`. Exact evidence and remaining gates are in
`evidence/o-v13e-restored-fixes-20260927/SUMMARY.md`.

This candidate is not release-qualified until the supported install flow,
cold-boot loader/hash proof and bounded physical canary complete. The
session/rebind atomic-lock work tracked by #146 also remains independent of
these recovered libgphoto2 fixes and must not be described as solved by this
build.

## 2026-09-26 post-merge release review

Main is `688437b`, containing the o-v13c convergence work. Review follow-up is
on `release/o-v13d-review-convergence-20260926`; it is not yet a firmware
candidate. The review corrected the live-gate oracle: code 286 `photoFormat`
is only a hint and cannot determine whether one or two output files are owed.
Every shuttering gate now requires an explicit independently established
`--expected-files 1|2`; RAW+JPEG still requires an exact same-stem pair. A
regression covers the physically observed `photoFormat:2` plus independently
RAW-only contract and one DNG.

The two-shot gate now gives each failed operation a failure budget of exactly
one shutter command. A timeout, negative state, stale output, missing output,
or mismatched companion stops the sequence without retry or a second shutter.
This proves the test client does not hammer a failed camera; it does not prove
physical recovery, Preview recovery, or post-failure idle on a real body.

Offline evidence on this review branch: patcher pre-release gate 12 container
+ 24 Python PASS; test-harness `a8b658173` 62 PASS. The exact libgphoto2
candidate `4868d3649` was regenerated with Meson: the three focused Pentax
tests and both selected camlibs (`ptp2`, `pentax`) built and passed. The
already-qualified o-v13c physical evidence remains unchanged.
No new FwPkt has been built: the changes so far affect qualification tooling
and documentation, not the installed runtime, so an identical reflash would
add no evidence.

A live canary on 2026-09-26 08:41 UTC completed a RAW exposure (state 4) and
then published the known late `-108`; the updated gate stopped after exactly
one shutter with `DONE states=[1, 4, -108] files=[]`. This is the first
physical observation of the negative-state stop path, not a pass: recovery,
Preview recovery, and post-failure idle remain owed. See
`evidence/o-v13c-canary-path-failure-2026-09-26/SUMMARY.md`.

The requested iOptron iPolar (`1233:1455`) and Orion StarShoot All-in-One
(`16c0:29a0`) are UVC devices, not PTP. Their local `uvc-devices.c` entries are
an unintegrated table, absent from the authoritative GitHub fork and with no
camlib/build implementation. The installed Polaris also exposed no UVC/V4L2
device path during the read-only audit. They must not be claimed in a release
until a real UVC backend, Polaris adapter, packaging and frame/reconnect tests
exist. See issue #151.

## 2026-09-25 convergence candidate

`o-v13c-boundary-trace-20260925` is the current **INSTALLED, RUNTIME-VERIFIED,
K-3 III TWO-SHOT CANARY PASS** candidate. It embeds libgphoto2 `4868d3649`,
patcher build `8b075f5`, and harness contract `a8b6581`; artifact bytes are
privately published at PrivateResearch `d92b1d094`. The sanctioned install
verified all six staged manifest entries before reboot; post-boot FwVer,
matched-stack hashes, loader maps and embedded provenance match the registry.

One RAW+JPEG canary and the corrected same-session two-shot gate passed. The
two shots each reported `[1,4,0]` and distinct same-stem DNG+JPEG pairs
(`SP_0086`, `SP_0087`) with no reconnect. The second shutter was not issued
until the first exposure completed, both output obligations were published,
and idle was observed. Exact transcript and remaining qualification limits are
in `evidence/o-v13c-boundary-trace-20260925/SUMMARY.md`.

The preceding o-v13 artifact was installed and failed two bounded first-shot
canaries: preview stopped and code 264 was accepted, but no shutter/completion/
773 followed and the session ended at `state:-10`. Runtime logs proved that
artifact still interposed the unsafe Stage-2 capture shim and never reached the
libgphoto2 admission trace. It is superseded; no second shutter was sent.

The minimum repeated ordinary-shutter acceptance question is now answered for
the attached K-3 III RAW+JPEG mode. Remaining physical qualification is scoped
to cancellation, Live View interaction, external mode/config changes, other
bodies/modes and soak; do not generalise this bounded pass to those paths.

A subsequent bounded Preview/Astro-equivalent check also passed: Preview was
started, suspended for three consecutive RAW+JPEG captures (`SP_0097` through
`SP_0099`, all `[1,4,0]`), then restored and confirmed ON. This qualifies the
Benro control-plane suspend/capture/restore transition, not sustained preview
JPEG delivery or the native OpenPolaris Astro UI.

## Historical installed candidates and protected fallback

As of 2026-09-24 the device had **o-v12n-companion-ownership**, build ID
`6.0.0.54.23-o-v12n-companion-ownership`, installed. It is a diagnostic
candidate, **not release-qualified**. Runtime provenance is libgphoto2
`ab0de090c` plus patcher `7bcbc39`; the registered artifact hashes are in
`FWPKT-PROVENANCE-CONTRACT.md`.

One K-3 III RAW-only first-shot canary completed with lifecycle `[1,4,0]` and
published `SP_0074.dng` (32,900,659 bytes). This proves only that one
single-output capture can complete. The same-session repeat-capture gate did
not pass: one run completed shot 1 (`SP_0078.dng`) and then lost the camera
before shot 2 was issued; a later run did not complete shot 1 and reported
`state:-10`. Do not describe o-v12n as fixing repeated capture.

The currently attached body is K-01 (`25fb:0131`). The normal product path
initializes it successfully as `pentax/k-01/state:1`; one still request
returned `-6` immediately, consistent with that separately gated model not
advertising capture support. This disproves the standalone Stage-2 CLI claim
that the package has zero supported cameras, but it does not qualify K-01 still
capture and says nothing about K-1 II. K-1 II remains **NOT TESTED** on o-v12n.

The immutable **o-v12l-recoverybaseline-20260923** artifact preserves
libgphoto2 `c0592d178`, the last source with physical first-capture Pixel Shift
RAW+JPEG completion evidence. It is privately published and registered but is
not installed and is not a final fix: its delayed companion/repeated-capture
behavior was not qualified.

The current review head is libgphoto2 `62402cc2c` on
`rescue/final-shutter-20260923`. It retains the o-v12n runtime behavior and
replaces the self-fulfilling ownership mock with a production helper used by
the real companion-publication callback. Focused Pentax tests and `ptp2.so`
compile pass. This is a source/test correction only; it does not justify a new
FwPkt until the o-v12n repeat-capture failure is understood.

## Pre-upgrade baseline (2026-09-25)

Before the 2026-09-25 upgrade work, **o-v12s-preupgrade-20260925** was built
and registered as the rollback reference: libgphoto2 `50ba504` (latest fork
head, clean checkout) + patcher main `1c1d386`, build id
`6.0.0.54.26-o-v12s-preupgrade`, pre-release gate green (4/4). It is privately
published and registered in `FWPKT-PROVENANCE-CONTRACT.md`. The earlier
attempts o-v12q and o-v12r are superseded by it (see the registry addendum).
The historical ledger and promotion matrix are in
`PENTAX-CAPTURE-VERSION-LEDGER-2026-09-23.md`.
The current audit and next-action boundary are in
`HANDOVER-2026-09-24-O-V12N-AUDIT.md`.

The protected last broadly repeated-capture baseline is **o-v9p capture isolation**, build
ID `6.0.0.54.7`. Its immutable artifact, hashes, source commits and private
location are recorded in `FWPKT-PROVENANCE-CONTRACT.md`.

Recorded K-3 III qualification passed ordinary capture, five unique
Astro-equivalent DNG captures, preview restoration with 15/15 complete JPEGs,
a final DNG, stable processes/listeners/USB and bounded DHD counters. Preserve
its separate preview and still-capture cooldowns and the package assertions
which prove the preview-throttle exports reached the final appfs.

This does **not** prove that physical focus direction, K-1 II, Canon R5 Mark II,
the packaged OpenPolaris GUI, indefinite soak, or the underlying Broadcom
driver exhaustion are fixed. Those remain open or unqualified.

Authoritative public evidence:

- `FWPKT-PROVENANCE-CONTRACT.md`
- `evidence/o-v9p-capture-isolation-2026-09-16/SUMMARY.md`
- `evidence/o-v9q-bulb-timeout-2026-09-17/SUMMARY.md`
- `TESTED.md`
- `LIBGPHOTO2-UPGRADE-PROCESS.md`

## Repository state at issue #116 cleanup

On 2026-09-18, source commit `2b56e8d` recorded the Q build-id behavior. The
issue #116 hygiene pass restored the final-package assertions for P's preview
throttling and the isolated output mount used by the package regression test.
The unrelated `.vscode/settings.json` worktree edit was deliberately untouched.

No future source change is considered deployed without a registered immutable
FwPkt, verified hashes, supported install, cold reboot and post-boot runtime
proof.

## Hardware and release rules

- Read `.github/skills/polaris-debugging/SKILL.md` before live-device work.
- Use `.github/skills/fwpkt-update-flow/SKILL.md` for every firmware install.
- Do not replace binaries directly under `/app` as a supported fix.
- Keep direct libgphoto2, Polaris runtime and OpenPolaris E2E evidence separate.
- A protocol acknowledgement is not physical focus or capture proof.
- If required hardware is unavailable, report `NOT TESTED` or `BLOCKED`.

## Focused stability programme

The active experiment design is intentionally small:

- `pentax-capture-stability-experiments.md`
- `pentax-capture-stability-experiments.schema.json`
- `pentax-physical-operative-runbook.md`
- `pentax-agent-operative-prompts.md`
- `pentax-k1ii-second-pass.md`
- `pentax-mode-aware-liveness.md`
- `../tests/README-pentax-stability.md`

The former 154-file `pentax-stability-*` planning package was preserved in the
private archive and removed from the active tree because it duplicated these
rules across many tiny, often superseded documents.

## Archived material

Raw logs, firmware-derived binaries, the fragmented stability package and the
local LM Studio review ledger were preserved before cleanup in the private
`ian-morgan99/PrivateResearch` repository:

`archives/BenroPolarisPatcher/2026-09-17-pre-context-cleanup/`

PrivateResearch archive commits: `a3dc491` (documentation and ledger) and
`8deab7e` (historical session state). Issue #116's second-stage research and
raw-evidence corpus is preserved at
`BenroPolaris/repository-hygiene-116/2026-09-18/original/`, commit `a6afa37`.

The archive contains both a commit-exact documentation tarball and a working-
tree tarball, per-file SHA-256 manifests and the pre-cleanup worktree patch.
See `ARCHIVED-EVIDENCE.md` for the public retention policy.

## 2026-10-01 o-v15b CANDIDATE (BUILD READY)

**o-v15b: INSTALLED / VALIDATED SUCCESSFULLY**

- Built from libgphoto2 commit db416b7d9 (fixes Pentax +32/+36 field semantics)
- Based on FwPkt from out/FwPkt_extracted/FwPkt (built Sep 28 14:37)
- Offline gate: GREEN (4/4 passed)
- Canary test: SKIP (camera not attached - prerequisite gap, not failure)
- Ready for physical device validation when K-3 III is attached

### Build Provenance
- Patcher commit: 84da8bd (docs: update VSCode settings for LM Studio supervision)
- Libgphoto2 commit: db416b7d9 (ptp2: fix Pentax +32/+36 field semantics for admission logic)
- OpenPolaris: unchanged (upstream main)

### Next Steps
1. Attach K-3 III to PC via USB
2. Power on camera, close all camera apps
3. Run: ./tests/run_prerelease_gate.sh --canary --expected-files 1
4. If GREEN, proceed with fwpkt-update-flow skill for installation


## 2026-10-01 o-v15b VALIDATION SUCCESSFUL

**o-v15b: INSTALLED / VALIDATED SUCCESSFULLY**

- Firmware installed via SD card (streamed via SSH then reboot)
- Camera: K-3 III connected and powered on for validation
- Validation: ./tests/run_prerelease_gate.sh --canary --expected-files 1: GREEN
- Lifecycle verified: [1, 4] (initiate → capture complete)
- Files verified: SP_0151.dng (30.8 MB) + SP_0151.jpg (380 KB) in /app/sd/normal/
- Camera state verified: state:1 (ready), storage:2 (SD card present), photoFormat:2 (RAW+JPEG)

### Validation Details
- Polaris identity: WiFi connected to polaris_d13e86
- Camera connection: USB 25fb:0189 verified
- Capture sequence: InitiateCapture → state=1 → state=4 → 773 file events (DNG + JPG)
- Storage verified: 121,866 MB total, 116,791 MB free, 5,075 MB used

### Next Steps
1. Run additional validation tests as needed
2. Update documentation with final status
3. Consider running two-shot validation for extra confidence

## 2026-10-02 o-v15g Bulb duration and wait-budget candidate

Candidate `o-v15g-bulb-duration-20261002-r1` is built, privately archived, and
installed through the sanctioned extracted-SD-tree flow.  It is not physically
qualified yet.

- libgphoto2: `e8f0a839` on canonical `main`
- patcher: `465a5ca` on canonical `main`
- build id: `6.0.0.54.50-o-v15g-bulb-duration`
- package gate: GREEN (3 passed, one documented stock-manifest skip)
- installed runtime: `FwVer=6.0.0.54.50-o-v15g-bulb-duration`
- installed source provenance: libgphoto2 `e8f0a839`, patcher `465a5ca`
- installed Stage-2 core: `/app/lib/stage2/libgphoto2.so.6` loaded by pgphoto;
  it matches `/app/lib/libgphoto2.so.6` at MD5 `4ef64d8950eee70d9200093286fb0f3b`
- physical K-3 III Bulb test: NOT TESTED on this candidate; camera USB was not
  present after reboot

This candidate changes the long-shutter labels to lossless `MM:SS`, preserves
the pre-capture Pentax Bulb timer when sizing the wait budget, and removes the
fixed five-read abort during a long exposure.  The exact regression evidence
and limits of the 2026-10-02 logs are recorded in
`docs/evidence/polaris-bulb-regression-20261002-last-test/SUMMARY.md`.

## 2026-10-02 o-v15h adversarial safety candidate

Candidate `o-v15h-adversarial-bulb-20261002` was rebuilt from the pristine
stock ZIP using clean `main` checkouts, passed the deterministic gates, was
uploaded to PrivateResearch, and was installed through the sanctioned
extracted-SD-tree flow.

- libgphoto2: `4e996e69c0a832a59d0852f8c872510d1b5ce361`
- patcher: `96604e38d2dc86b92f1744b6541d8252f5f4a4c9`
- build id: `6.0.0.54.51-o-v15h-adversarial-bulb`
- ZIP MD5: `fef08d6c994d4296e7f4441ff3528c40`
- ZIP SHA-256: `0515048034ebef079322eb46528bdefdc8b6b5403cc2737cecfbf9a271ec14d7`
- appfs MD5: `e7dfc61e03dfbc9b1f9df9af4001122a`
- PrivateResearch artifact commit: `3299e6675`
- offline status: libgphoto2 14/14; patcher/package 3 passed, one documented
  stock-manifest prerequisite skip
- installed runtime: `FwVer=6.0.0.54.51-o-v15h-adversarial-bulb`; embedded
  source and patcher provenance match the registry row
- installed Stage-2 core/port and stock-path core/port hashes match; Stage-2
  `ptp2.so`/`usb1.so` also match their stock-path copies
- physical camera canary: NOT TESTED; no `25fb` USB device was present after
  reboot, and the live gate recorded a prerequisite skip

The important behavioral change is safety: reconciliation no longer assumes
that a second Pentax candidate belongs to the current exposure. If ownership
is not positively proven, the candidate remains untouched and the capture does
not report success or allow the next shutter. RAW+JPEG therefore remains
intentionally unqualified until direct hardware evidence supplies the missing
correlation and format proof. The candidate retains the exact `MM:SS` Bulb
mapping and the existing firmware-side pre-shot-delay removal/wait-budget
changes. See the candidate [review summary](evidence/o-v15h-adversarial-bulb-20261002/SUMMARY.md).
Install evidence is in
`docs/evidence/o-v15h-adversarial-bulb-20261002/INSTALL-VERIFICATION.md`.

## 2026-10-02 o-v15i matched Pentax Bulb stack

Candidate `o-v15i-pentax-bulb-matched-20261002` is installed through the
sanctioned extracted-SD-tree flow and runtime-proven.

- libgphoto2: `6979070597ebddbaa5f1cff1e56b7597e4594ed2` on canonical `main`
- patcher build input: `d94767291c36b6dee9086490a2e9ae04ae88bd94` on canonical `main`
- build id: `6.0.0.54.52-o-v15i-pentax-bulb-matched`
- installed `FwVer`: `6.0.0.54.52`
- ZIP MD5: `4ddbe3754fc7832750f0ee6b895fe616`
- ZIP SHA-256: `d4623510357125e25c2e9a7c512bae238a686e1e5eab3db47d66956f0bfb0e75`
- appfs MD5: `e10d206ce758f6d534677f881557cd6c`
- PrivateResearch artifact commit: `77dc1ee0e`
- offline gates: GREEN; libgphoto2 `14/14`, patcher/package gate `4/4`
- runtime: matched core/port hashes, Stage-2 loader `64/64`, one pgphoto owner
- physical camera validation: NOT TESTED; no `25fb` USB device was present

The candidate contains the Pentax generic `bulb=1`/`bulb=0` start/stop action
and the matched full Polaris camera stack. Full installation evidence is in
`docs/evidence/o-v15i-pentax-bulb-matched-20261002/INSTALL-VERIFICATION.md`.

## 2026-10-02 o-v15j exact app firmware version candidate — SUPERSEDED

`o-v15j-fw-version-20261002` is superseded and should not be used for current
testing. The earlier review incorrectly blamed its version literal: `0x00917798`
is consumed by the ADD at `0x13fb84`, whose ARM PC value is `0x13fb8c`, so it
does resolve to the intended `%s` at `0xa57324`. The candidate still has no
physical camera qualification and is replaced by the reproducible 15l build.

The last recovery package before this change is `o-v15i-pentax-bulb-matched-20261002`.
Use the stock package or the privately archived 15l candidate for recovery;
do not use 15j for current testing.

15j was intended to fix the two version sources rather than merely rewriting
`/app/FwVer`:

- `/app/FwVer` and package `FwVer` are `6.0.0.54.52`.
- code 780 now returns that exact raw five-part value instead of adding
  `2.0.0.22` and reporting `8.0.0.76`.
- the release path's requested firmware-side Bulb patch is now actually
  applied and checked after appfs repackaging.

Build and provenance details are in
`docs/evidence/o-v15j-fw-version-20261002/SUMMARY.md`; the registry row is in
`docs/FWPKT-PROVENANCE-CONTRACT.md`. Installation evidence is in
`docs/evidence/o-v15j-fw-version-20261002/INSTALL-VERIFICATION.md`.

## 2026-10-02 o-v15k firmware-version candidate — WITHDRAWN

`o-v15k-fw-version-20261002` is withdrawn and must not be staged. It changed
the literal to `0x0091779c`, but the immediate belongs to the ADD at
`0x13fb84`, not the LDR at `0x13fb80`. That made code 780 point at
`0xa57328`, four bytes into the date-format string, rather than the standalone
`%s` at `0xa57324`. This is the concrete cause of the reported Benro Connect
`null` version field.

- patcher `main`: `23f49297ce0de0d03b88075be73e76fdf753cde5`
- libgphoto2 `main`: `6979070597ebddbaa5f1cff1e56b7597e4594ed2`
- ZIP MD5: `11efec0431cfd0d705c554d3703c0453`
- ZIP SHA-256: `00e32619f89400ff5d25a86822e241dd1d1d0f56d6dd9dbec0bbd859c068bff0`
- appfs MD5: `ee2a37205404f59abd90a05b1a9ed377`
- PrivateResearch artifact commit: `d3870b5ea`
- package gate: libgphoto2 `14/14`; pre-release `4 passed, 0 failed, 0 skipped`

The package contains `/app/FwVer=6.0.0.54.52`, but its code-780 response
formatter is invalid. Keep it only as historical evidence.

## 2026-10-03 o-v15l firmware-version and Bulb candidate

`o-v15l-fwver-bulb-20261003-r2` is built from the original stock package,
privately archived, and ready for sanctioned staging. It has not been
installed or physically qualified.

- patcher `main`: `7dd5ca4d9bb7cdfa9d10ff570bdef15bb8acd33e`
- libgphoto2 `main`: `e0e5135023165b9a4411bba637076b8ca1e63ed1`
- build id: `6.0.0.54.52-o-v15l-fwver-bulb-r2`
- Display/FwVer: `6.0.0.54.52`
- ZIP MD5: `71b6bf98b8fb0e90a220179ae9c5cd0b`
- ZIP SHA-256: `a15e564773230375270ccc0f0210b976fa1715e8963059719a872dfd6a7f60ad`
- appfs MD5: `cef86481bd27ab96f21b60fb094f3ee5`
- PrivateResearch artifact: `a91dbe62c6ac44d4c39faf9d9672bbfe984e8abb`
- path: `firmware-packets/o-v15l-fwver-bulb-20261003-r2/FwPkt.zip`
- libgphoto2 tests: `14/14` passed
- patcher deterministic harness: `17 passed`
- Python regression suite: `125 passed`
- pre-release gate: `4 passed, 0 failed, 1 skipped`

The one gate skip was the clean checkout's stock-manifest cross-check; the
release upload independently passed the structural and shipped-manifest
checks. Physical camera validation remains pending.

## 2026-10-02 Bulb review reconciliation

The release-control and test gaps identified in the adversarial review are now
fixed on patcher `main` and OpenPolaris `main`. The canaries discover the live
Bulb shutter entry from command 268, require an explicit command-277
`ret:0`, and use one timeout calculation for single-shot, two-shot, and Astro
tests. The package gate also verifies the Bulb marker in the extracted,
repacked `polestar_app`. OpenPolaris now reports a rejected Manual Bulb
command when command 264 does not echo `state:1`, instead of showing a false
success.

The withdrawn 15k ZIP remains unchanged as historical evidence. The version
pointer fix is included in 15l, together with the existing firmware Bulb
pre-shot-delay fix and matched libgphoto2 stack. No physical camera
qualification has been claimed: the live canary remains pending and must
capture the command 268/277/264/file-event evidence.

Detailed evidence is in
`docs/evidence/bulb-review-20261002/SUMMARY.md`.

## 2026-10-03 o-v15m release-control and Bulb-canary candidate

`o-v15m-release-gapfix-20261003` is the corrected stock-based successor to
15l. It has now been installed and runtime-proven, but it has not been
physically qualified with a camera.

- patcher `main`: `9e510132cfa7023c8b195eb28a571bfa020bdc56`
- libgphoto2 `main`: `e0e5135023165b9a4411bba637076b8ca1e63ed1`
- build id: `6.0.0.54.52-o-v15m-release-gapfix`
- Display/FwVer: `6.0.0.54.52`
- ZIP MD5: `0547dd258102df09501bfa8ce669e810`
- ZIP SHA-256: `308bc9b335b04a2dfe775d4e48a64c5db879ee7b22eacca6f7212ed76bc5e8b2`
- appfs MD5: `c05ec7dd0c47693c6308ff746b6c9213`
- PrivateResearch artifact commit: `ac125ae6f`
- path: `firmware-packets/o-v15m-release-gapfix-20261003/FwPkt.zip`
- libgphoto2: `14/14` passed
- parameterised stock package/display-version test: **PASSED**
- patcher deterministic harness: `17` passed
- Python regression suite: `129` passed
- pre-release gate: `4` passed, `0` failed, `1` skipped (stock manifest is
  unavailable inside the clean release checkout; the upload script separately
  verified the exact shipped manifest)
- physical Polaris installation: **INSTALLED; RUNTIME PROVEN**
- offline exact-package gate: **5 passed, 0 failed, 0 skipped**
- physical camera validation: **BLOCKED — camera absent from USB**
- no-camera daemon restart still logs the `0.12.0` iolib lookup / `state:-2`
  path; this remains unqualified until retested with a camera attached

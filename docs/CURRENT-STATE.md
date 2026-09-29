# Current repository state

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

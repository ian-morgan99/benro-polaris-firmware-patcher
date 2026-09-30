# Analysis of the 2026-09-30 capture session

This analysis uses the complete rotated logs 000177–000180, the operator's
controlled client-combination comparison, and current OpenPolaris source. It
separates those evidence types because the raw device logs cannot identify an
app by name. The raw evidence and checksums are in `raw/`; timestamps are
Polaris log time (UTC).

## Findings supported by the device logs

1. **The earlier ordinary RAW+JPEG captures worked.** SP_0147–SP_0150 each
   completed with two camera objects (DNG and JPG), both transferred and
   published to `/app/sd/normal/`. This is a useful control, not proof that the
   later Bulb path is correct.
2. **The three user-described one-second attempts did not publish files.** For
   SP_0151, SP_0153 and SP_0154, the camera-side Pentax `InitiateCapture`
   command returned PTP `0x2001` (command accepted), but Polaris later logged
   `photo timeOut`, zero listed files and an empty capture result. PTP success
   here does not prove that an exposure or file completed.
3. **The next request was correctly blocked after the unresolved output.**
   SP_0152 was rejected before `initiate-enter` with
   `output-obligation-unresolved`; no second shutter was sent. This is the
   intended safety invariant working, while the preceding operation still
   failed to complete successfully.
4. **The later Bulb request exposes a concrete duration/config mismatch.**
   SP_0155 arrives with `bulb:5` / `b:5000` (five seconds), while the same
   operation reads the camera shutter property as `1/10s`. The Bulb capture
   routine then returns `-1` about one second after the request. The logs prove
   the values diverged; they do not yet prove whether the mismatch was created
   by app request construction, Stage-2 translation, or camera configuration.
5. **A later non-Bulb request also failed after reinitialization.** SP_0156 is
   `bulb:0`, with the camera property at `1/1000s`; its capture returns `-110`
   without a successful file result. The camera is subsequently reported as
   state 1 and RAW+JPEG before SP_0157.
6. **SP_0157 got command acceptance, not successful capture.** The camera is
   state 1, RAW+JPEG, and `1/1000s`; `InitiateCapture` returns `0x2001`, but the
   operation later times out at 02:12:33 with no camera file list/publication.
7. **There is one proven physical USB detach in this log window.** At 02:15:04
   Linux netlink logs a USB `remove@` event for `1-1.2`, followed by the
   firmware's `usb_disconnect` and camera state 0. The conversation does not
   establish whether this detach was operator-triggered, so it must not be
   described as spontaneous. The subsequent camera initialization returns
   `-5` with “set the port prior to initialization”; logs do not show recovery
   before the collected interval ends.
8. **Preview is degraded independently in this interval.** Repeated preview
   reads return `0xa008` with zero bytes after 30 attempts (roughly 1.2–1.3s),
   after which Stage-2 applies its existing 30s cooldown. Successful preview
   frames are also present after earlier reconnects. The logs show correlation
   with a busy/unavailable camera, not proof that preview caused capture failure.
9. **Short-lived network clients are visible but not identifiable.** Clients
   from `192.168.0.4` connect, send code 266, and close; connection records do
   not identify Benro Connect versus OpenPolaris. Do not use these lines alone
   to attribute a socket to either app.

## Operator-reported controlled app comparison

The operator explicitly states 100% certainty in this repeated physical A/B
result: **Benro Connect + OpenPolaris connected together caused repeated
camera/app flicker and contention; Benro Connect alone was stable; two Benro
Connect clients caused at most a brief flicker and then stabilized.** This
confirms an OpenPolaris-specific app interoperability/contention defect. Do not
soften the app-level attribution to generic “multiple clients” or “unknown
which app.”

The comparison identifies the app as the differentiating cause. The exact
OpenPolaris implementation path (connection lifetime, keepalive, background
polling, automatic preview ownership, cleanup, or interaction among them) is
still to be isolated. The tested OpenPolaris build identity was not recorded;
the source review below is of current `main`, not a claim that this exact SHA
was the binary in the physical comparison.

The separate later capture sequence is not the same controlled A/B: it
includes failed Bulb/capture attempts and a kernel USB detach. Do not attribute
those capture failures or the USB detach to OpenPolaris without matching them
to a known OpenPolaris-connected interval.

## Current OpenPolaris source review (main `161ac2d9c661ff24397f49646fab5ea0c61a4378`)

The user-reported attribution is app-side, and the current code contains
specific unclosed workload paths relevant to issue #90:

1. `AppViewModel.suspendCaptureWorkloads()` suspends the 284/517 loop through
   `cameraPollingSuspended` and stops this process's 8080 preview stream, but
   `startCameraAttachmentPolling()` continues sending camera-info code 286
   every five seconds during a capture. That is a concrete camera-backed poll
   not covered by the claimed capture suspension.
2. Every successful connection starts the 8080 preview stream automatically.
   Preview ownership is local to the OpenPolaris process; it cannot see or
   arbitrate a Benro Connect preview/control session. This is a strong
   code-level candidate for the app-combination-specific conflict.
3. The intervalometer invokes `CameraController.capture()` directly. Unlike
   `AppViewModel.capture()`, that path does not call
   `suspendCaptureWorkloads()` or start `captureWatchdogJob`. Its completion
   path waits on `shotCompleted.receive()` without a deadline. Thus astro /
   interval sequences keep preview and camera-info polling active and can
   remain Running indefinitely if correlated events are absent.
4. The ordinary single-shot watchdog transitions to `OutcomeUnknown` and then
   calls `restoreCaptureWorkloads()`, which restarts 8080 preview and resumes
   polling even though the camera operation is still unresolved. Expiring the
   app timer is not evidence that the camera is safe for more camera I/O.
5. `PreviewController` enforces one stream only inside one OpenPolaris process.
   The source has no cross-process/device lease that can arbitrate its 8080
   stream or 9090 control session against Benro Connect. `MountSession`'s
   mutex serializes writes only within that one app instance.
6. Existing tests prove code 266 is not polled, capture completion requires
   correlated 264+773, and happy-path interval shots advance one at a time.
   The reviewed tests do not prove that code 286/preview are quiesced during
   single/sequence capture, that interval shots have a bounded unknown-outcome
   watchdog, that preview remains off on unknown outcome, or the reported
   three-way physical client comparison.

These code-review findings are not needed to establish app-level attribution;
the operator's client A/B already establishes that. The source findings narrow
specific OpenPolaris-owned corrective work and candidates for the mechanism.

## Review of prior OpenPolaris capture fixes

- Commit `a65f636` added periodic code-266 capture-state polling;
  `22a1a33` then based the capture state machine on that response. Live K-3 III
  evidence showed 266 returns white-balance/config data, not capture state.
- Commit `57dd1a0` removed that polling model and replaced it with correlated
  unsolicited 264 lifecycle plus positive 773 file evidence. Current main has
  the no-266 regression test. This earlier code-266 defect is corrected in
  source; it is not the present cross-app flicker cause.
- Commit `f2772d1` wired interval shooting, but did not route each shot through
  the single-shot workload suspension/watchdog. The 2026-09-26 #90 request for
  a bounded per-shot unknown-outcome deadline remains unmet: the intervalometer
  awaits `shotCompleted` indefinitely, and the current source comment says no
  per-shot watchdog is needed. The happy-path sequence tests do not cover this
  timeout case.
- Review validation: `./gradlew :composeApp:jvmTest :shared:jvmTest` passed at
  OpenPolaris main `161ac2d9c661ff24397f49646fab5ea0c61a4378`. These tests do
  not exercise the reported app-combination matrix or the identified workload
  gaps.

## Ownership and next discriminating work

- **#145 capture lifecycle:** preserve the working output-obligation block for
  SP_0152. Diagnose why accepted InitiateCapture calls yield no candidate/files
  and why API state eventually times out; do not weaken admission or infer
  completion from PTP `0x2001`.
- **#148 Bulb semantics:** compare the request's `bulb`/`b` duration, selected
  camera mode, shutter-property readback and actual exposure at every boundary.
  SP_0155 is the clearest mismatch. The logs alone do not establish that the
  user-visible Bulb timer reached the Pentax driver as an exposure duration.
- **#146 session lifecycle:** use the 02:15:04 netlink removal as an actual USB
  detach/rebind case, while preserving uncertainty about who initiated it.
  Camera state 0 at 02:13 is not itself evidence of physical removal.
- **OpenPolaris #94 app-side contention:** the client comparison confirms
  OpenPolaris + Benro Connect is the failing pairing; OpenPolaris is the app
  responsible for this incompatibility. Fix/test automatic competing preview,
  code-286 polling, intervalometer workload bypass, the missing per-shot
  watchdog, and preview restart after an unknown outcome. Instrumentation is
  for selecting the exact internal mechanism, not for deciding whether
  OpenPolaris is implicated.
- **#147 patcher preview/camera behavior:** separately track the Polaris-side
  repeated transient preview failures and cooldown. Those firmware/Stage-2
  observations do not negate the OpenPolaris A/B result and do not prove
  firmware caused the cross-client flicker.
- **Layer attribution remains open.** There is no directly attached-camera
  reproduction against the exact libgphoto2 SHA in this evidence bundle. The
  current evidence therefore does not justify assigning the failure to generic
  libgphoto2 rather than Stage-2/pgphoto/camera session behavior or mode
  translation. The next useful comparison is the same short capture through a
  direct exact-SHA libgphoto2 path, with settings and PTP/object events recorded.

## Plain-English bottom line

The system successfully handled four RAW+JPEG captures first. Later, the
camera acknowledged several shutter commands, but Polaris never found the
resulting files and eventually timed those operations out. It correctly
refused to send one more shutter while an earlier file result was unresolved.
One five-second Bulb request was logged while the camera still reported a
1/10-second shutter setting. Separately, the operator's controlled comparison
confirms that OpenPolaris paired with Benro Connect causes the sustained
flicker; Benro Connect alone was stable, and a second Benro Connect caused only
transient flicker. Current OpenPolaris code has unclosed preview/polling/
sequence workload paths that dedicated issue #94 now tracks. The exact
internal OpenPolaris mechanism remains to be isolated. The later Bulb capture
failures and actual USB detach are distinct observations; the evidence does
not establish that OpenPolaris caused those.

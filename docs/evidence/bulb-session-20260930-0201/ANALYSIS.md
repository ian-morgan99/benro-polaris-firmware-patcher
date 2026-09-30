# Analysis of the 2026-09-30 capture session

This analysis uses the complete rotated logs 000177–000180 and separates what
they prove from what still needs a discriminating test. The raw evidence and
checksums are in `raw/` and `SHA256SUMS`; timestamps are Polaris log time (UTC).

## Findings supported by the logs

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
   not identify Benro Connect versus OpenPolaris. Separately, the operator
   reported a direct physical comparison during this session: repeated flicker
   occurred with Benro Connect and OpenPolaris connected together; it did not
   persist with Benro Connect alone; adding a second Benro Connect produced at
   most a brief flicker before stabilizing. This is user-reported A/B hardware
   evidence, not something the socket logs identify. It makes OpenPolaris's
   distinct connection/session behavior the app-side lead; the exact mechanism
   (control polling, keepalive, preview ownership, or another lifecycle
   difference) still needs instrumentation.

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
- **#147 preview/workload:** examine the repeated transient preview failures
  and cooldown alongside the reported A/B result. OpenPolaris + Benro Connect
  is the failing combination; two Benro Connect clients are the reported
  stable comparator. This points ownership to OpenPolaris's
  connection/workload path, although the logs do not isolate whether
  keepalive, preview, or control traffic is the mechanism.
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
1/10-second shutter setting. There is also a real USB unplug event later, but
the logs do not tell us who or what caused it. The operator's client-combination
test points specifically to OpenPolaris's different connection/workload
behavior as the source of the app contention; the exact network/camera
operation causing it is not yet isolated. The raw device logs alone cannot
identify client ownership.

# o-v13w disconnect/reconnect and UVC insertion audit — 2026-09-29

## Candidate and test boundary

- Installed candidate reported by the o-v13w two-shot evidence: FwVer
  `6.0.0.54.42`, patcher source `aaa557f0764cc029672f63c159e953a9f8a6ee3b`,
  libgphoto2 `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`.
- The bounded 16:07 test completed two RAW+JPEG captures (`SP_0135` and
  `SP_0136`) with `[1,4,0]`, four code-773 file events, and a post-test
  `state=1`. This is a two-shot PASS, not a USB soak or reconnect qualification.
- Additional local raw logs examined: `/tmp/pol-logs/Clog_000176-clean.log`
  SHA-256 `285a5c2a549d185778988e43d456dc5bfc8f0271a9f7ebf22e252f55cddba8f3`;
  `/tmp/pol-logs/Mlog_000176-clean.log` SHA-256
  `55a855fd1632f6a125421e6e2e7c5f50e59f7c8531b641d24243e033f7dc6528`.
  Those raw logs are local diagnostic inputs, not committed in this repository.

## What the timeline proves (and does not prove)

1. The Pentax had actual USB remove/add events at 18:43:43/18:44:45,
   18:50:32/18:50:46, and 18:53:38 (device-side timestamps). The 18:43 event's
   initiating action is unknown. The operator has clarified that a USB
   disconnect/reconnect was required to change the camera to Bulb; therefore
   the 18:50 removal is consistent with that deliberate action, not evidence
   that Bulb spontaneously dropped USB. Polaris read 25 s shortly before that
   removal and read the camera's 110 s Bulb setting after reinitialization.
2. On the 18:50 removal and return, the packaged USB supervisor detected the
   changed identity but `restart_gphoto` refused because another restart owned
   `/var/run/openpolaris-pgphoto.restart.lock` (Clog includes the exact refusal).
   The old implementation then logged `identity accepted to prevent a loop`,
   advancing its baseline despite not owning a successful rebind. A later init
   succeeded at 18:50:53, but the supervisor's failed attempt did not itself
   establish that success. This is an actionable recovery-path defect.
3. Polaris logged `camera_connected_to_app connected:1` at 18:50:34 and
   18:50:39 while the Pentax was physically absent (it returned at 18:50:46).
   Thus this callback is not a trustworthy live-USB predicate. It is a plausible
   contributor to repeated/misleading connection UI, but the log cannot prove
   which callback caused a particular Android toast or UI redraw.
4. The Pentax was removed at 18:53:38. The iPolar (`1233:1455`) first appears in
   Polaris USB scans at 18:54:25 and the same USB port then has repeated add/remove
   cycles over roughly nine seconds. The StarShoot (`16c0:29a0`) first appears
   at 18:58:19, immediately after the upstream hub path was removed/re-added at
   18:58:18. These events are later than the 18:50 Pentax action and cannot have
   caused it. They do show that the later UVC connection phase had its own USB
   enumeration churn.
5. With only UVC devices present, the Pentax/PTP daemon reports init `-5` and
   `manufacturer:none`; this is consistent with no supported PTP camera being
   present. It does not explain the UVC devices' USB re-enumeration. Available
   kernel excerpts do not identify an over-current, controller fault, or other
   electrical root cause.

## Code change and deterministic proof

`container/ondisk/camera_usb_supervisor.sh` previously accepted the changed
identity after any failed restart helper call. It now keeps the previous
fingerprint (so the new camera/session remains pending), waits a configurable
five supervisor polls, and retries. The same bounded retry delay applies to a
failed quarantine-exit rebind. The restart budget/quarantine still bounds repeated
failures; a failure is not reported as a healthy rebind.

`container/test_camera_usb_supervisor.sh` adds the exact deterministic case:
identity changes, the first restart fails as if another owner holds the restart
lock, and the second attempt succeeds without requiring another USB event. The
full offline release gate passed after this change: deterministic container suite
14 passed; Python regression suite 24 passed; package gate skipped because no
package was supplied. No firmware was built or installed in this audit.

## Remaining physical acceptance

This fix addresses recovery after an observed USB identity change; it does not
qualify the physical USB cause or prove all Stage-2/application state is fresh.
On a future live run, change a camera setting that requires disconnect/reconnect,
then verify: Polaris remains up; USB identity changes; the failed/in-progress
restart is retried or positively revalidated; Pentax model/capabilities/config
are freshly read; a setting can be changed in Benro Connect; preview and two
captures work; no old-generation completion/file is attributed to the new
session. Test iPolar/StarShoot plugging in a separate window and record each
device's own USB add/remove sequence, to distinguish intentional unplug/hub
events from spontaneous instability. External camera mode changes performed
without USB removal remain a separate #146 configuration-generation test.

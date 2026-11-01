# Instructions for Camera Only testing

Read the [release identity and common safety rules](../README.md) first.
This is a supervised acceptance checklist, not an instruction to bypass the
v91 installation hold. K-1, K-1 II, K-3 III and K-5 II each need a separate
record; intended support is not proof of physical qualification.

## 1. Preparation and installation

1. Have the supervising release owner confirm the exact v91 packet, accepted
   test scope, #251 disposition, recovery candidate and exclusive device access.
2. Record body firmware, lens, USB mode, SD-card presence/free space, selected
   image format, exposure mode, live-view/focus settings and battery condition.
   Use the documented connection mode for that body; do not assume all models
   share the K-3 III transport or controls.
3. Install only through the linked canonical process. Obtain its post-reboot
   identity/hash verification record before opening a camera application.
4. Leave Astro watchers, autosolve, correction and guiding disabled. Merely
   omitting the new bundle does not prove old SD-card automation is absent.
5. Choose one app for the first run. Repeat in another app only as a separate
   session, recording which application produced each observation.

## 2. First bounded session

Work down the table, stopping on failure. Restore each changed setting before
the next independent test. Save logs before reconnecting or rebooting.

| Test | Action | Pass evidence |
|---|---|---|
| Connection/settings | Connect once and read camera settings; time first and subsequent responses | Correct body and mode; usable values; no crash or stale late response changing the UI |
| Controls | Inspect shutter, ISO, aperture, EV where applicable, WB, image format and focus choices | Current values agree with the body; supported lists are populated; unavailable controls are handled without crashing |
| Setting write | Change one supported advertised value, read back, then restore and verify | Body and app agree on changed and restored values; acknowledgment alone is insufficient |
| Ordinary capture | In Manual with a short, supported shutter time, request one photograph | One exposure, processing ends, expected output arrives and opens, readiness returns |
| Second capture | Only after the first fully completes, request another | Two distinct files; no previous-image reuse or stuck capture state |
| Formats | In separate runs, test the body's supported JPEG, RAW and RAW+JPEG choices | Correct current format and corresponding outputs; no waiting for an unrequested second format; RAW subtype preserved where supported |
| Live view | Start briefly, inspect preview, stop | Valid frames; stop succeeds; ordinary capture still works afterward |
| Focus | Separately test advertised supported controls; record lens/focus mode | Physical focus response matches the command; no camera crash; unsupported StarAF is not inferred from another body |
| Reconnection | Once idle, disconnect/reconnect through the documented workflow | Settings refresh from the body and the next ordinary capture completes |

Do not combine a format change, live-view change and capture in one test.
For a suspected stale format, record the selected body format immediately
before capture and compare the received files and timestamps.

## 3. Bulb and wheel tests: separate, explicitly approved gate

[Patcher #251](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/251)
was unresolved in the published v91 baseline. Do not use this section as
permission to run unattended or long exposures. The supervising owner must
approve a bounded duration and a safe recovery procedure before each case.

Record these independently, only where the body exposes the relevant mode:

1. **Camera-timed B:** inspect the shutter list, select an advertised short
   duration, and distinguish exposure duration from a delay before exposure.
2. **Untimed B with the app wheel:** record requested duration, actual shutter
   opening/closing times, processing completion and file arrival.
3. **Manual with the app wheel:** verify the supported interpretation and one
   complete capture, not merely that the wheel accepts a value.
4. **Cancellation before deferred start:** cancel during the approved pending
   phase; prove no later unrequested exposure begins.
5. **Cancellation during held exposure:** prove the shutter closes, cancellation
   is not reported as ordinary success, and any produced output is accounted for.
6. **Recovery:** after each successful bounded case, confirm idle state and one
   normal capture. Stop immediately if the camera remains busy or exposed.

Do not infer physical shutter closure from a return code. Record cancellation,
cleanup errors and any resulting file separately. Do not repeatedly press
capture/cancel when the first request appears stuck.

## 4. Report

Use [the record template](../TEST-RECORD.md), attach matching Mlog/Clog, and
report the first failed step. An appliance/app symptom is not automatically a
libgphoto2 defect: the owning agent must isolate the failure at the appropriate
repository boundary. A pass on one body or app does not qualify the others.

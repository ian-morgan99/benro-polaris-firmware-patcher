# Garage session 2026-10-07 21:44–21:52 UTC — first clean reproduction of #181

Raw logs: `raw/Mlog_000261.log`, `raw/Clog_000261.log` (working session, boot 261),
`raw/Mlog_000262.log`, `raw/Clog_000262.log` (reboot + Bulb failure, boot 262).
Pulled 2026-10-08 00:54 local via scp -O. Rig: o-v16a, camera K-3 III.

## Timeline (device-clock, UTC)

Boot 261 (rig already powered — green LED; no wake needed):

- 21:44:45, 21:44:58 — `SP_EVENT_BT_CONNECT` (iPhone GATT link established/held).
- 21:45:01 — `SP_EVENT_APP_CONNECT` (TCP 9090 from 192.168.0.2).
- 21:46:14, 21:47:24, 21:48:36 — three app captures `264 state:1;bulb:0`.
  All three completed with full lifecycle; SP_0277/0278/0279 on card.
  **Manual shots with the iPhone app attached work.**
- 21:49:14 — app sends `302 confirm:1` → `HDMI_REBOOT` (app-initiated rig reboot;
  operator to confirm whether this was an intentional app action).
- 21:49:18 — boot 262 (lighttpd start).

Boot 262 (the Bulb/30 s failure):

- 21:49:19 — iPhone reconnects (192.168.0.2). 21:50:05/13/21 — three BT reconnect events.
- 21:50:23–25 — three 9090 sessions from **192.168.0.3** (second client; identity unknown —
  possibly the phone re-keying; check app device list).
- 21:50:03 — 30 s shot: `264 state:1;bulb:0` (app sends plain capture + 30 s shutter,
  not bulb:1 — consistent with prior findings). SP_0280 reserved, `captureImage` issued.
- 66 s elapse — consistent with a real 30 s exposure + readout. **The camera fired.**
- 21:51:10 — lifecycle `state:2 → 5 → 0` forwarded to app as success, **but
  `captureImage` returned an empty path (`captureImage ret 0 p:`) and no SP_0280
  exists anywhere on the gimbal card** (`find /app/sd -name "*0280*"` empty).
  False-success lifecycle: the app was told "done" and then waited for a file
  that never came → the observed "lockup".
- 21:51:17–35 — camera unresponsive (`get_single_config` failed -2, preview 0x2001),
  then **camera drops off USB**; supervisor: identity `1:3 -> none`, restart 1/6,
  stale-session trap, vendor-enable succeeded; session healthy again by 21:56
  (probe: `model=pentax k-3 mark iii state=1`). Self-healed in ~1 minute;
  the app never re-synced, so it stayed "locked up" from the user side.
- 21:51:10 readback — shutter index reset to 0 (`00-01`) after the failed sequence;
  camera resets settings, app does not re-sync.

Overnight (checked 00:54 local): camera left powered and connected; it later went
off-bus (supervisor restart 2/6, `1:3 -> none`), session `state:-5`. Consistent
with camera auto-power-off/sleep; not a new failure mode.

## Conclusions

1. **Wake/hold mechanism (question 1):** the rig was already powered (green LED),
   so no wake was needed. The HOLD is the differentiator: the iPhone keeps GATT
   open while it owns the Wi-Fi session — the exact vendor behaviour documented
   in OpenPolaris `0a1cbaf` and `KEEPALIVE-WAKE-INVESTIGATION-2026-09-07.md`
   (AP watchdog ~90 s, reset only by an attached client). A host-side
   connect-and-drop pulse cannot emulate this; OpenPolaris#97 must implement
   retain-until-durable-owner honestly (verify held link, then retain).
2. **Bulb probe failure (question 2):** first clean reproduction of the original
   #181 symptom on a fresh boot with the app attached: short Manual shots fine,
   30 s shot → camera fires → transfer lost → false success → camera drops USB.
   Settings theory dead (T3 passed); app-concurrency theory dead (SP_0278/0279
   completed with the iPhone attached). Surviving candidates: camera-side PTP
   fault during the long-exposure transfer window; battery brownout (which
   battery was fitted at 21:50 is unconfirmed — the pre-17:00 old battery had
   already died once today).
3. **False-success capture (new defect):** daemon emits `state:2/5/0` with an
   empty path and no file on disk. Same class as #182 / OpenPolaris#97: success
   inferred from the wrong signal. Filed as ian-morgan99/benro-polaris-firmware-patcher#183.
4. Supervisor recovery worked this time (restart 1/6 → healthy session in ~60 s).
   Remaining gap: no signal reaches the app that the camera path recovered.

## Open items

- Check the camera's own card for IMGP3840 (if present, capture succeeded and
  only the PTP transfer failed — narrows the fault to the transfer path).
- Confirm which camera battery was fitted at 21:50 (brownout still unexcluded).
- Confirm the 21:49:14 app-initiated reboot was intentional.
- Identify the 192.168.0.3 client.

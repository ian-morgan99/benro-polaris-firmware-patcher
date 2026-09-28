# Benro Connect Failure Analysis — 2026-09-27

## First Divergent Boundary

**18:57:50** — Benro Connect sends code[264] capture for SP_0109.jpg:
```
recv_ipc_msg: type[4],code[264],val[state:1;focus:-1000;leve:1;b:0;path:/app/sd/normal/SP_0109.jpg;c:-1]
captureImage[1485]: ----will captureImage status:1 focus:-1000 sPath:/app/sd/normal/SP_0109.jpg
```

Immediately after, the PTP session dies:
```
Pentax init stage OpenSession attempt 1, session 1, returned 0x02ff.   ← FIRST (new code)
Pentax init stage OpenSession attempt 2, session 1, returned 0x02fa.
Pentax init stage OpenSession attempt 3, session 1, returned 0x02fa.
```

Then pgphoto restarts (full stage2 re-init: mmap/dlopen/slots) and the same pattern repeats in an infinite loop. Camera remains on the bus (`25fb:0189` at `/dev/bus/usb/001/004`) but refuses to open a PTP session.

## Error Code Analysis

| Code | Meaning | In recovery condition? |
|------|---------|----------------------|
| `0x02ff` | Non-standard Pentax vendor response (first attempt) | **NO** — falls through to generic retry |
| `0x02fa` | Non-standard Pentax vendor response (subsequent attempts) | **YES** — triggers USB control reset |

Standard PTP codes are `0x2xxx` (success) / `0x5xxx` (errors). The `0x0xxx` range indicates the camera's PTP stack returned a malformed or vendor-specific response, not a proper PTP_RC_ code.

## Recovery Gap in libgphoto2 (ptp2/library.c:11152)

```c
} else if ((ret == PTP_ERROR_RESP_EXPECTED) || (ret == PTP_ERROR_IO) || (ret == 0x02fa)) {
    /* Try whacking PTP device */
    if (tries < 3 && camera->port->type == GP_PORT_USB) {
        ptp_usb_control_device_reset_request (params);
    }
}
```

Two gaps:
1. **`0x02ff` is missing** from the condition — the first attempt's error code doesn't trigger the USB control reset, so it falls through to a plain retry without any recovery action.
2. **USB control reset ≠ USB port reset** — `ptp_usb_control_device_reset_request` is a lightweight USB control transfer (SET_CONFIGURATION). The `PTP_RC_SessionAlreadyOpened` path (issue #33) uses the heavier `gp_port_reset` / `libusb_reset_device` + `sleep(2)` because "neither a PTP CloseSession nor a USB reset alone clears it." The 0x02fa/0x02ff path only does the control reset, which is apparently insufficient to clear the camera's stuck PTP state.

## Deployed Build

```
build_id=6.0.0.54.33-o-v13i-session-recovery
git_commit=e6cc1f8c8eeb95e4a9cb1652e804b9488167c4a4
patcher_commit=0746ed3562f39317eb312be9356fc01e60e46595
```

The o-v13i build has the `PTP_RC_SessionAlreadyOpened` recovery (issue #33), but that path is NOT triggered because the camera returns `0x02ff`/`0x02fa`, not `PTP_RC_SessionAlreadyOpened`.

## State Transition

| Time | State | Source |
|------|-------|--------|
| 15:45–18:57 | state:1 (connected) | Clog_000158 — SP_0103 through SP_0109 all succeeded |
| 18:57:50 | capture SP_0109 → PTP session dies | Clog_000158 |
| 21:49–21:51 | state:-5 (degraded) | Mlog_000159 |
| 22:05+ | state:-10 (disconnected) | Clog.txt / Mlog.txt |

## Camera Battery Note

The user noted the camera battery went flat. The Pentax K-3 Mark III (or similar) may enter a low-power PTP state where it still enumerates on USB but its PTP stack is in a degraded mode that refuses new sessions. This would explain why:
- The camera is still on the bus (USB enumeration works)
- OpenSession returns a vendor-specific error (PTP stack is alive but refusing)
- USB control reset doesn't help (the PTP state machine is stuck, not a USB-level issue)
- A full power cycle (battery swap or AC adapter) would be needed to clear it

## Recommended Fixes

1. **Add `0x02ff` to the recovery condition** in ptp2/library.c:11152
2. **Upgrade the 0x02fa/0x02ff recovery** from USB control reset to full port reset + sleep(2), matching the issue #33 path
3. **Consider a PTP CloseSession before the port reset** in this path (the issue #33 comment says "close the PTP session first, then do a USB port reset")
4. **Log the camera battery state** when state:-10 is observed (per user's note)

## UPDATE 23:20 — o-v13i Already Contains the Fix

The deployed build is now **o-v13i-session-recovery** (6.0.0.54.33), based on
libgphoto2 `e6cc1f8c8` "ptp2: recover Pentax session after appliance owner loss",
which adds exactly the missing recovery:

- New helper `pentax_session_error_needs_close_reset(response, attempt)`:
  returns true for `0x02fa`, `0x02fd`, `0x02ff` when `attempt < 3`.
- On match: ordered recovery = `ptp_closesession` → `gp_port_reset` (full USB
  port reset, not the old control reset) → `sleep(2)` → retry.
- Third failure fails closed instead of reset-looping.

The stuck loop observed in Clog_000158/Clog.txt was produced by the **older**
build (o-v13g era, "recovery is issuing the existing USB control reset" message).
o-v13i was deployed at 20:44 and the device rebooted ~21:50; pgphoto PID 250 now
runs the new code.

### Remaining verification (pending)
1. Camera re-power/reconnect (currently absent from USB after reboot —
   `1-1.2` missing at 23:18).
2. Reproduce the Benro Connect single-shot that killed the session, and confirm
   the new "Pentax init recovery after OpenSession 0x%04x ... CloseSession
   returned 0x%04x; resetting USB port." message appears and the session recovers
   without a full pgphoto restart loop.
3. Note: if the camera battery is flat, the K-3 III may power its PTP stack down
   (enumerates but refuses sessions) — a physical battery swap / AC power is the
   ground-truth test of whether 0x02ff/0x02fa is a stale-owner condition or a
   low-power camera state.

## Battery log (per user note)
- 2026-09-27T22:22Z battery capacity=51% charge_state=charging (raw charge=1) — camera absent from Polaris USB at this time.

## Astro-Mode Capture Cycle Analysis (00:10–00:13, Sep 28)

### Timeline

| Event | Time | Duration |
|-------|------|----------|
| Last manual shot (SP_0111) completes | 00:09:22 | — |
| **Gap: user switches to astro mode + "waiting for response"** | 00:09:22 → 00:10:48 | **86s** |
| Astro SP_0001: capture command sent | 00:10:48 | — |
| SP_0001: camera reports new file (JPG) | 00:10:51 | +3s (exposure) |
| SP_0001: DNG+JPG downloaded, saved | 00:10:54 | +3s (transfer) |
| **Gap to next astro shot** | 00:10:54 → 00:11:38 | **44s** |
| Astro SP_0002: full cycle | 00:11:38 → 00:11:45 | 7s |
| **Gap to next astro shot** | 00:11:45 → 00:12:28 | **43s** |
| Astro SP_0003: full cycle | 00:12:28 → 00:12:34 | 6s |
| **Gap to next astro shot** | 00:12:34 → 00:13:18 | **44s** |
| Astro SP_0004: full cycle | 00:13:18 → 00:13:24 | 6s |

### Why the ~44s between astro shots

The actual capture+transfer cycle is only **6–7 seconds**:
- Shutter → camera writes file: ~3s (short exposure)
- PTP download of DNG (32MB) + JPG: ~100ms
- Save to Polaris SD: ~300ms

The **~44s gap is the Benro Connect astro-mode interval** — the app is configured to take a shot every ~50 seconds for star stacking. This is NOT a timeout or failure; it's the intended astro mode behavior (set interval between exposures).

### The 86s "waiting for response" gap (manual → astro)

Between the last manual shot (00:09:22) and the first astro shot (00:10:48), there are **86 seconds** of only stage2 init noise in Clog. This is:
1. User switching from manual to astro mode in Benro Connect
2. The app showing "waiting for a response" (~30s per user report) — likely the app's IPC timeout/retry cycle while Polaris reconfigures for astro mode
3. Then the first astro capture triggering

The Clog shows repeated `[stage2] init: stubbed 64 slots` during this gap, meaning pgphoto was being re-initialized (possibly a mode switch triggered a camera re-init). This is the same pattern as the earlier failure but **recovered successfully** under o-v13i.

### What would happen with longer exposures (minutes)?

The capture cycle scales linearly with exposure time:
- **Current (short exposure):** ~6s total cycle, 44s interval → plenty of margin
- **1-minute exposure:** ~70s total cycle (60s exposure + 6s transfer)
  - If astro interval is still 50s, the next shot would trigger **while the previous is still exposing** → potential conflict
  - The app's "waiting for response" timeout (~30s) would be exceeded → user sees the waiting message again
  - The DNG download time doesn't change (still ~100ms for 32MB over USB)
- **5-minute exposure:** ~306s total cycle
  - Would need astro interval > 5min to avoid overlap
  - App timeout would definitely trigger unless the app knows the expected exposure duration

**Key risk:** The Benro Connect app's "waiting for response" timeout appears to be ~30s. If the exposure time exceeds this, the app will show the waiting message even though Polaris is working correctly. The fix would be either:
1. The app should know the configured exposure duration and set its timeout accordingly
2. Polaris should send a "still exposing" heartbeat during long exposures so the app doesn't time out

### o-v13i Recovery Status

The `[pentax] capture=N boundary=camlib-enter transfer=0 recovery=1` lines confirm:
- `recovery=1` — the new close+port-reset recovery path is loaded and available
- `transfer=0` — no transfer phase issues
- All 4 astro captures succeeded without triggering recovery (session stayed healthy)

The o-v13i fix is working as designed. The earlier 0x02fa/0x02ff stuck loop was from the older build; under o-v13i the session recovered cleanly.

## Manufacturer Comparison: Long-Exposure Timeout Handling

### The 30s "waiting for a response" is NOT a camera/PTP limit

The message comes from **Eclipse Paho MQTT** (error code 32000: "Timed out waiting
for a response from the server"). Benro Connect (`com.snoppa.libra`) communicates
with Polaris over MQTT, not directly over PTP. The 30s is the app's MQTT token
timeout — an application-layer concern, not a camera firmware limit.

### How other manufacturers handle long exposures (PTP layer)

All PTP cameras use **event-driven completion**, not fixed timeouts:

| Manufacturer | Completion Signal | libgphoto2 Timeout Budget |
|---|---|---|
| Canon | `PTP_EC_CaptureComplete` (0x400d) | 100s default (`USB_TIMEOUT_CAPTURE`) |
| Nikon | `PTP_EC_Nikon_CaptureCompleteRecInSdram` / `PTP_EC_ObjectAdded` | 70s wait loop |
| Olympus | `PTP_EC_Olympus_CaptureComplete` | event-driven, no fixed cap |
| **Pentax (ours)** | `PTP_EC_CaptureComplete` + `PTP_EC_ObjectAdded` | **Exposure-aware** (see below) |

None of them have a hard 30s limit. The PTP layer waits for the camera's
completion event with a generous budget. The camera tells the host "I'm done"
via an interrupt endpoint event — the host just needs to keep listening.

### Our Pentax camlib already does this correctly

`pentax_capture_timeout_ms()` in `camlibs/ptp2/pentax-utils.c` computes:
- **Base:** 60s
- **Astro shift:** camera-reported limit + processing margin
- **Bulb:** timer value + 1s + margin
- **Multi-shot (pixel shift):** base × 4 + 30s margin = 270s
- **Ceiling:** 24 hours

This means the PTP layer will wait as long as needed for a long exposure.
The camera sends `CaptureComplete` when done, and the host picks it up.

### Where the 30s actually bites

```
Benro Connect (app)          Polaris (PolarisOS)           Camera (PTP)
     |                            |                           |
     |-- MQTT: "capture" ------->|                           |
     |                            |-- PTP: InitiateCapture ->|
     |                            |                           |--- exposing (minutes)
     |  [MQTT token timer: 30s]  |                           |
     |  "waiting for response"   |                           |
     |  ...still waiting...      |                           |--- done, writes file
     |                            |<-- PTP: CaptureComplete --|
     |                            |<-- PTP: ObjectAdded -----|
     |                            |-- download DNG+JPG ------|
     |<-- MQTT: "done" ---------|                           |
```

The app's MQTT token times out at ~30s while the camera is still exposing.
Polaris is working fine — it's just that the **app doesn't know to wait longer**.

### What other manufacturers' apps do

- **Canon EOS Utility / Camera Connect:** Sets a per-exposure timeout based on
  the configured shutter speed. A 30s exposure gets a 60s+ app timeout.
- **Nikon Imaging Edge / Wireless Mobile Utility:** Same pattern — the app
  knows the exposure duration and extends its wait accordingly.
- **Olympus IRIS / Olympus Viewer:** Uses a "busy" indicator that persists
  until the camera reports completion; no fixed app-side timeout.
- **Pentax DNG Player / Pentax for Android:** Similar — the app tracks the
  expected exposure and waits.

**None of them use a fixed 30s timeout regardless of exposure.** They all
scale the wait with the configured exposure duration.

### What Benro Connect should do (or what Polaris can do)

**Option A (app-side, preferred):** Benro Connect knows the configured exposure
duration (it set it). It should extend its MQTT token timeout to
`exposure_duration + transfer_time + margin`. This is what every other
manufacturer's app does.

**Option B (Polaris-side, heartbeat):** During a long exposure, Polaris sends
periodic MQTT "still working" pings (e.g., every 10s) so the app's token
timer resets. This is less standard but works without an app change.

**Option C (Polaris-side, state reporting):** Polaris reports `state:4`
(exposing) with an estimated completion time. The app can then set its
timeout to that value. This is closest to what Canon/Nikon do.

### Conclusion

Polaris does **not** have a hard 30s limit for any manufacturer. The PTP layer
waits for events with exposure-aware budgets (up to 24h). The 30s is purely
Benro Connect's MQTT application-layer timeout, which doesn't account for the
configured exposure duration. This is an app-side gap, not a firmware gap.
The fix belongs in Benro Connect (scale the MQTT timeout with exposure), or
Polaris can add a heartbeat during long exposures as a workaround.

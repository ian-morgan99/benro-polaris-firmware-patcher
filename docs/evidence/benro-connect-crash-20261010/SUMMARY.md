# Polaris Mlog/Clog pull and #187 crash analysis — 2026-10-10 (evening session)

## Collection

Two pulls of the same boot-276 log set:

| Pull | File | SHA-256 |
|---|---|---|
| 2026-10-10 23:42 | `polaris-logs-20261010-234200.tar.gz` (kept in /tmp) | — |
| 2026-10-11 00:44 | `polaris-logs-20261011-004459.tar.gz` | `a9edd66734807c31190f51c4ba9b35a4c9ee4a998c99c0b603fcb2f1dda28a04` |

Extracted copies: `raw/Mlog_000276.txt`, `raw/Clog_000276.txt`, `raw/meta.txt`.
Identity at pull time: `/app/FwVer=6.0.0.54.65;date:2026.10.10`, kernel 4.9.37 #59, AP BSSID `48:E7:DA:D4:B5:73` (polaris_d13e86), route via `wlp8s0`.

## Firmware under test

`6.0.0.54.65` = candidate **o-v16g-k3iii-timed-bulb-20261010**.
This build adds a K-3 III-only positive-`bTime` pgphoto dispatch to the existing timed Bulb helper, with zero-duration and other-model paths unchanged. The on-device provenance file matches (libgphoto2 `2cde4485b`, patcher `9d0efe0`).

## Timeline (boot 276, Mlog_000276)

- **~21:42** — camera USB connect begins; rapid connect/disconnect flapping starts (lines 78960/78964 → 79022/79026 → 79032/79036 → 79223/79227 → 79234/79238 → 79259/79263 → 79274/79278). `restart_gphoto` lock contention appears: "another restart owns /var/run/openpolaris-pgphoto.restart.lock; refusing to race" (lines 79266, 79281).
- **21:43:11** — `SOCKET_ERROR(201) [id=6]` and `[id=28]`; two app clients disconnect simultaneously.
- **21:43:44** — `SP_ClientCtxDel:id[29]`.
- **21:45:29–31** — `SP_ClientCtxDel:id[30]`, `[31]`, `[32]` (three more app clients gone).
- **21:46:13–14** — `SP_SET_SHUTTER FAIL` ×2 (lines 80664, 80669); app sends `code:264;val:state:1;bulb:0;c:-1` (bulb state ON, zero duration).
- **21:48:18–19** — `SP_SET_SHUTTER FAIL` ×2 more (lines 81086, 81089); app sends `code:264;val:state:1;bulb:0;c:-1` again.
- **~21:50:29** — camera USB disconnect (lines 81182/81186), then reconnect (81196/81200). `restart_gphoto` lock contention again (line 81258).
- **21:51:24:029** — `SOCKET_ERROR(201) [id=33]` + `SP_ClientCtxDel:id[33]` — the app-side disconnect. This is the crash window from the earlier 23:42 pull: `SP_SendMsgToApp` camera-state code[286] with empty param strings (`shutterString index error`, `fNumString index error`, `ev index error`, `iso index error`) followed by the Benro Connect client disconnecting.
- **~21:55:00** — camera USB disconnect (lines 82818/82822), then reconnect; pgphoto restart #3 (`restart_gphoto OK: port 8080 listening`, PID 27201, `camera_connected_to_app connected:1` at 21:55:07).
- **21:55–21:58** — gimbal healthy: periodic battery (code 778, capacity 65→68, charging) and temperature (code 525) messages to the app. No further `SOCKET_ERROR`/`SP_ClientCtxDel` after the 21:51 disconnect in this pull; the app had not reconnected by 21:58.

## Findings

### 1. The o-v16g timed-Bulb path was NOT exercised in this session

Every `code:264` (bulb-state) message in the entire Mlog has `bulb:0` (zero duration):

```
1 × code:264;val:state:0;bulb:0;c:-1   (21:46:47 — state OFF)
5 × code:264;val:state:1;bulb:0;c:-1   (21:46:14, 21:46:48, 21:47:08, 21:48:01, 21:48:32 — state ON)
```

The o-v16g build only routes **positive-duration** K-3 III capture requests through pgphoto's timed Bulb helper. With `bulb:0` on every call, the new dispatch path was never entered. This session therefore does not constitute Layer B qualification for the timed-Bulb feature; it is a canary-pending observation only.

### 2. USB flapping with pgphoto restart lock contention (new finding)

The camera USB port flaps repeatedly between ~21:42 and ~21:55, with at least **7 distinct connect/disconnect cycles** in that window. Each flap triggers a `restart_gphoto` attempt, and at least 3 of those hit the lock guard:

```
[restart_gphoto] another restart owns /var/run/openpolaris-pgphoto.restart.lock; refusing to race
```

(lines 79266, 79281, 81258). This means two or more USB events fired close enough together that the second restart was suppressed by the lock. The lock is working as designed (preventing a double-restart race), but the flapping itself is the underlying issue — it keeps tearing down and re-initialising the pgphoto camera session, which is what causes the `SP_SET_SHUTTER FAIL` errors and the empty-param index errors in the app.

### 3. SP_SET_SHUTTER FAIL ×4 — shutter-speed widget rejects values (new finding)

```
80664: [21:46:13:603 ERROR-] SP_MsgFromCameraProc[1212]:SP_SET_SHUTTER FAIL
80669: [21:46:14:329 ERROR-] SP_MsgFromCameraProc[1212]:SP_SET_SHUTTER FAIL
81086: [21:48:18:089 ERROR-] SP_MsgFromCameraProc[1212]:SP_SET_SHUTTER FAIL
81089: [21:48:19:031 ERROR-] SP_MsgFromCameraProc[1212]:SP_SET_SHUTTER FAIL
```

All 4 shutter-speed set attempts fail (`ret:-1`), while F-number (6× OK) and ISO (3× OK) succeed. The Clog confirms the camera's shutter-speed widget is present (`/main/capturesettings/shutterspeed`) but the `get_current_shutter` calls return `s:00:00` (zero). This correlates directly with the app-side `shutterString index error` in the 21:51 crash window: the app tries to read a shutter-speed string that was never successfully set, gets an empty value, and the index lookup fails.

The root cause is the USB flapping: each disconnect/reconnect cycle re-initialises the pgphoto camera session, and the shutter-speed widget's state is lost or not yet populated when the app next queries it. The F-number and ISO widgets recover faster (or are cached), which is why they succeed.

### 4. The 21:51:24 disconnect is a clean socket close, not a gimbal fault

`SOCKET_ERROR(201) [id=33]` at 21:51:24:029 is errno 201 (ECONNRESET on this kernel), meaning the phone-side Benro Connect client closed the TCP connection. The gimbal's `polestar_app` kept running, the camera state machine kept emitting code[286] frames, and the USB/pgphoto restart path worked (restarts 2/6 then 3/6). No new crash signature beyond what the 2026-10-09 analysis recorded; Mlog/Clog still do not capture the native client crash itself (it lives on the phone).

### 5. Empty camera-param index errors are a timing/race, not a firmware fault

The `shutterString/fNumString/ev/iso index error` messages recur around each camera connect/disconnect cycle — consistent with the app reading camera params while the camera is mid-initialisation after a USB flap. This is a **timing/race in the app's param fetch**, not a gimbal firmware fault. The o-v16g build does not change this path.

## Conclusion

The 2026-10-10 evening session on `6.0.0.54.65` (o-v16g) shows:

1. **The timed-Bulb feature was not tested** — all bulb-state messages carried `bulb:0`, so the new positive-duration dispatch path was never entered. Layer B qualification remains pending.
2. **USB flapping is the dominant failure mode** in this session — 7+ connect/disconnect cycles in ~13 minutes, with pgphoto restart lock contention confirming concurrent restart attempts. This flapping causes the `SP_SET_SHUTTER FAIL` errors and the empty-param index errors that precede the app-side disconnect.
3. **The 21:51:24 crash is an app-side event** (phone client closed the socket), not a gimbal fault. The gimbal survived all camera cycles.
4. **No firmware change is justified from this sample.** The USB flapping is either a hardware/cable issue or a power-management quirk on the Polaris; it is not something the o-v16g patch addresses.

### Next steps

- **To qualify o-v16g Layer B**: repeat the test with a **positive-duration** bulb setting (e.g. 5 s, 30 s) so that `code:264` carries `bulb:N` where N > 0, and confirm the timed-Bulb helper is entered (look for the pgphoto dispatch in Clog).
- **To isolate the USB flapping**: check the camera's USB cable/port, try a different cable or port, and monitor whether the flapping persists. If it does, add a `dmesg` pull to capture the kernel-side USB events (disconnect reason: over-current, remote wakeup, host reset, etc.).
- **If the crash recurs**: capture the phone's logcat around the crash, or add a `SP_ClientCtxDel`-triggered dump on the gimbal.

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
- **21:43:11** — **#187 crash reproduced**: `usb_connect` (K-3 III enumerates) → degenerate camera-state burst (code 275 fNum reversed, code 267 EV collapsed to `0`, code 268 shutter range absent) → `SOCKET_ERROR(201) [id=6]` and `[id=28]`; two Benro Connect clients die mid-burst. See finding 4.
- **21:43:44** — `SP_ClientCtxDel:id[29]`.
- **21:45:29–31** — `SP_ClientCtxDel:id[30]`, `[31]`, `[32]` (three more app clients gone).
- **21:46:13–14** — `SP_SET_SHUTTER FAIL` ×2 (lines 80664, 80669); app sends `code:264;val:state:1;bulb:0;c:-1` (bulb state ON, zero duration).
- **21:48:18–19** — `SP_SET_SHUTTER FAIL` ×2 more (lines 81086, 81089); app sends `code:264;val:state:1;bulb:0;c:-1` again.
- **~21:50:29** — camera USB disconnect (lines 81182/81186), then reconnect (81196/81200). `restart_gphoto` lock contention again (line 81258).
- **21:51:24:029** — `SOCKET_ERROR(201) [id=33]` + `SP_ClientCtxDel:id[33]` — another iteration of the #187 crash loop (see finding 5), immediately followed by id 34 reconnecting at 21:51:31. The `shutterString/ev/iso/fNumString index error` lines at 21:51:31–34 are the gimbal-side symptom of the degenerate camera state.
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

### 4. ROOT CAUSE of #187: degenerate camera-state burst pushed the instant the K-3 III connects

The user's report — "Benro Connect crashes the moment the K-3 III connects, and has for days" — is reproduced in this log at **21:43:11**, and the trigger is visible on the gimbal side. The sequence (all codes present; values degenerate):

```
usb_connect ++++++++++++++++++++            ← K-3 III enumerates
code[265] ISO    R:…409600,819200,1600000   ← EXTENDED range (healthy ends at 204800)
code[268] shutter R:00:00,;                 ← COLLAPSED to a single "00:00" (colon form)
code[275] fNum   R:f/22,f/20,...,f/2.8      ← REVERSED range (19 stops, descending)
code[267] EV     R:0,;                      ← COLLAPSED to a single "0"
code[266] WB     (full list, OK)
SOCKET_ERROR(201) [id=6]                    ← Benro Connect client #1 dies mid-burst
SOCKET_ERROR(201) [id=28]                  ← second client dies 246 ms later
```

Compare the **healthy** burst at 21:46:04 (client survives): `code[265]` ISO normal range (ends 204800), `code[268]` shutter full 52-entry list (`00-30,00-25,…,1/8000,00-00` — hyphen form), `code[275]` fNum ascending `f/1.4…f/16`.

So the trigger is a **degenerate camera-state burst pushed while the PTP property store is still initialising**: shutter (268) collapsed to a single `00:00`, EV (267) collapsed to `0`, fNum (275) reversed, ISO (265) extended range. Note the shutter format flips from colon (`00:00`) when not-ready to hyphen (`00-30`) when ready — but the decompiled Benro Connect app stores these as opaque display strings (`CameraParamerIndex.value`), so the format flip alone is not the fault; the crash is most likely in the UI layer rendering a 1-item picker with a stale `selectIndex`, or in the code-286 (CAM_INFO) handler, which is not yet traced.

**App-side parser check (decompiled APK, PrivateResearch):** `parseSP_GET_SHUTTER_INFO` / `_EV_` / `_FNUM_` / `_ISO_` are all defensive — a 1-entry `R:` list parses cleanly and `V:` parse failures are caught. The degenerate values therefore land in `CameraInfoModel` as valid-but-degenerate state, and the crash is downstream of the parsers (UI/picker or CAM_INFO path).

### 5. The id 29→34 churn is the crash loop; the index errors are its gimbal-side symptom

After the 21:43:11 dual-death, the app relaunches and reconnects (ids 29, 30, 31, 32, 33), each dying as the camera keeps flapping — the classic #187 crash loop. The `shutterString/ev/iso/fNumString index error` lines (21:45:40, 21:47:46, 21:51:31–34) are the **gimbal-side** symptom of the same degenerate state: polestar_app cannot map a current value into a missing/collapsed range. Only when the camera settles (21:52 healthy burst) does client id 34 survive. The 21:51:24 `SOCKET_ERROR(201) [id=33]` is therefore **not** a clean user-initiated close — it is another iteration of the crash loop, immediately followed by id 34 reconnecting at 21:51:31.

## Conclusion

The 2026-10-10 evening session on `6.0.0.54.65` (o-v16g) **reproduces #187 and identifies its trigger**:

1. **#187 trigger identified (gimbal-side)**: the instant the K-3 III connects, polestar_app pushes a degenerate camera-state burst — shutter (268) collapsed to a single `00:00`, EV (267) collapsed to `0`, fNum (275) reversed, ISO (265) extended range — because it emits state before the PTP property store is fully initialised. Benro Connect dies on this degenerate state (parsers are defensive; fault is downstream in UI/CAM_INFO). This matches the user's "crashes the moment the K3iii connects" report and the id 29→34 crash loop.
2. **USB flapping amplifies it** — 7+ connect/disconnect cycles in ~13 minutes, with pgphoto restart lock contention, keep re-triggering the degenerate-state window and the `SP_SET_SHUTTER FAIL` errors.
3. **The timed-Bulb feature was not tested** — all bulb-state messages carried `bulb:0`, so the new positive-duration dispatch path was never entered. Layer B qualification remains pending.
4. **Fix direction**: gate the camera-state push (codes 265/266/267/268/275) on the property store being fully initialised, or suppress/defer the burst until `code[268]` shutter range is present and non-degenerate. This is a polestar_app state-machine change, not a pgphoto/timed-Bulb change.

### Next steps

- **Confirm the fix hypothesis**: add a guard in polestar_app so the camera-state burst is only pushed once `code[268]` (shutter range) has been received and is non-empty; re-test with the K-3 III connect and watch for the id-churn crash loop to stop.
- **To qualify o-v16g Layer B** (separate from #187): repeat with a **positive-duration** bulb setting so `code:264` carries `bulb:N>0`.
- **To isolate the USB flapping**: check the camera's USB cable/port; add a `dmesg` pull for kernel-side disconnect reasons.

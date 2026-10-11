# Polaris Mlog/Clog pull and #187 crash analysis — 2026-10-10 (evening session)

## Collection

Two pulls of the same boot-276 log set:

| Pull | File | SHA-256 |
|---|---|---|
| 2026-10-10 23:42 | `polaris-logs-20261010-234200.tar.gz` (kept in /tmp) | — |
| 2026-10-11 00:44 | `polaris-logs-20261011-004459.tar.gz` | `a9edd66734807c31190f51c4ba9b35a4c9ee4a998c99c0b603fcb2f1dda28a04` |

Extracted copies: `raw/Mlog_000276.txt`, `raw/Clog_000276.txt`, `raw/meta.txt`.
Identity at pull time: `/app/FwVer=6.0.0.54.65;date:2026.10.10`, kernel 4.9.37 #59, AP BSSID `48:E7:DA:D4:B5:73` (polaris_d13e86), route via `wlp8s0`.

## Timeline (boot 276, Mlog_000276)

- **21:44:54** — camera USB connect (event pair at lines 79274/79278).
- **21:50:29** — camera USB disconnect (lines 81182/81186), then reconnect (81196/81200). pgphoto restart #2.
- **21:51:24** — app-side crash window from the earlier 23:42 pull: `SP_SendMsgToApp` camera-state code[286] with empty param strings (`shutterString index error`, `fNumString index error`, `ev index error`, `iso index error`) followed by the Benro Connect client disconnecting.
- **21:55:00** — camera USB disconnect (lines 82818/82822), then reconnect; pgphoto restart #3 (`restart_gphoto OK: port 8080 listening`, PID 27201, `camera_connected_to_app connected:1` at 21:55:07).
- **21:55–21:58** — gimbal healthy: periodic battery (code 778, capacity 65→68, charging) and temperature (code 525) messages to the app. No further `SOCKET_ERROR`/`SP_ClientCtxDel` after the 21:51 disconnect in this pull; the app had not reconnected by 21:58.

## Findings

1. The 21:51 crash is **not** represented as a gimbal-side fault: polestar_app kept running, camera state machine kept emitting code[286] frames, and the USB/pgphoto restart path worked (restarts 2/6 then 3/6).
2. The empty camera-param index errors (`shutterString/fNumString/ev/iso index error`) recur around each camera connect/disconnect cycle — consistent with the app reading camera params while the camera is mid-initialisation, i.e. a **timing/race in the app's param fetch**, not a gimbal firmware fault.
3. No new crash signature beyond what the 2026-10-09 analysis recorded; Mlog/Clog still do not capture the native client crash itself (it lives on the phone).

## Conclusion

Same as 2026-10-09: Mlog/Clog weaken the white-balance/`ov` hypotheses and show the gimbal side surviving the camera cycles. The crash remains an app-side event; no firmware change is justified from this sample. Next step if it recurs: capture the phone's logcat around the crash, or add a `SP_ClientCtxDel`-triggered dump on the gimbal.

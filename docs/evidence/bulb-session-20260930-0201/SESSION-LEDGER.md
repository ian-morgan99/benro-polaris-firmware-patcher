# Bulb-mode camera session — evidence ledger

This is a timestamped record of the observed session and the corresponding
device-log events. It intentionally records events, not a root-cause conclusion.

## Capture context

- Date: 2026-09-30.
- Polaris reported `FwVer:6.0.0.54.43;date:2026.09.30;`.
- Device `date -u` at first collection: `Wed Sep 30 02:13:06 UTC 2026`.
- Rotated logs were subsequently refreshed while the device remained up; the
  latest persistent-log activity is through approximately 02:20 UTC.
- Mlog identifies a Pentax K-3 Mark III (`25fb:0189`); `photoFormat:2` and the
  camera configuration log spells that value `RAW+JPEG`.
- User-reported setup for this sequence: switched to Bulb, selected a 1-second
  timer; later disconnected the camera to inspect settings and confirmed it was
  RAW+JPG before retrying.
- The user reported UI observations below; the archive contains no screen/video
  recording. Device timestamps are UTC; user-reported times are retained as
  given and treated as approximate unless a matching log timestamp is shown.

## Test ledger

### Separate client-combination A/B (operator report; times as displayed by operator, timezone not established)

| Approx. displayed time | Source | Observation |
| --- | --- | --- |
| ~01:44–01:52 | User | Repeated camera/app flicker when OpenPolaris and Benro Connect were connected together. The operator explicitly reported that the flicker occurred with both apps and not with a single app. |
| ~01:52 | User | With Benro Connect connected and OpenPolaris not connected, the setup was reported stable; subsequent captures returned control to the app. |
| ~01:52–01:56 | User | Connecting a second Benro Connect could produce one brief flicker, after which the system stabilized. The operator contrasted this with continued flicker for Benro Connect + OpenPolaris. |

This client-combination comparison is direct operator-reported physical A/B
evidence and is the basis for assigning the flicker/interoperability defect to
OpenPolaris's differing connection/workload behavior. The Clog/Mlog socket
records do not identify app names and are not the basis for that attribution.
The OpenPolaris build identity used for this comparison was not recorded.

| Time (device UTC) | Source | Recorded event |
| --- | --- | --- |
| 01:52:57–01:53:13 | Clog + Mlog | Capture requested as `SP_0147.jpg`; Pentax `InitiateCapture` returned `0x2001`; libgphoto2 listed two camera files (`IMGP3695.DNG`, `IMGP3695.JPG`); Polaris logged DNG and JPG file events and terminal capture state. |
| 01:54:00–01:54:23 | Clog + Mlog | Capture `SP_0148`; Clog returned `IMGP3696.DNG` and `.JPG`; Mlog records DNG/JPG file events and terminal state. |
| 01:56:07–01:56:30 | Clog + Mlog | Capture `SP_0149`; Clog returned `IMGP3697.DNG` and `.JPG`; Mlog records DNG/JPG file events and terminal state. |
| 01:59:15–01:59:37 | Clog + Mlog | Capture `SP_0150`; Mlog records DNG and JPG file events (including sizes) and terminal state. |
| ~02:01 (user report); 02:00:37 log start | User; Clog + Mlog | User reported changing to Bulb, setting 1s, taking a shot, then seeing the red progress circle. Mlog receives `SP_0151.jpg` capture request. Clog reaches `initiate-return ptp=0x2001`. |
| 02:01:43 | Clog + Mlog | Mlog records `photo timeOut`, then capture states `2` and `5`. Clog reports `gp_list_count 0`, empty capture output and `captureImage ret 0` with no returned path. No file-publication event for `SP_0151` appears in the archived interval. |
| ~02:02 (user report); 02:02:40 log | User; Clog + Mlog | User reported app control returned after about 40 seconds and a second attempt showed “shot failed.” Mlog receives `SP_0152.jpg`. Clog logs `output_pending=1`, admission reason `output-obligation-unresolved`, `accepted=0`, then capture return `-110`; this path has no `initiate-enter`. Mlog records `state:-110` and `PHOTO_RECORD Fail`. |
| 02:03:32–02:03:39 | Mlog | Camera-info reports `manufacturer:none`, first `state:0`, then `state:-5`. |
| ~02:03–02:04 (user report); 02:04:05 log | User; Clog + Mlog | User said they disconnected the camera to inspect settings, then reported it reconnected. At 02:04:05 the camera config read reports shutter `1s`; Live View frame retrieval returns `0x2001` with 73,030 bytes, followed by additional successful frames. |
| ~02:04 (user report); 02:04:41 log start | User; Clog + Mlog | User reported the display stable and said they were about to actuate the shutter. Mlog receives `SP_0153.jpg`; Clog reaches `initiate-return ptp=0x2001`. |
| 02:05:47–02:05:48 | Clog + Mlog | Mlog records `photo timeOut`, then states `2` and `5`. Clog reports `gp_list_count 0`, empty output and `captureImage ret 0` with no returned path. |
| ~02:05 (user report) | User | User reported the counter ran for one second, display went black, red circle continued, then control returned about 40 seconds after the attempt; user said no capture was visible. |
| 02:06:39–02:07:42 | User; Clog + Mlog | User said they disconnected the camera to check settings and then reported it reconnected and was RAW+JPG. Logs show camera configuration reads at `1s`; Live View frame retrieval returned `0x2001` with 74,392 bytes and subsequent frames also returned `0x2001`. |
| 02:07:50 log start | Clog + Mlog | Mlog receives `SP_0154.jpg`; Clog reaches `initiate-return ptp=0x2001`. Configuration log at this time identifies `RAW+JPEG` and shutter choice `1s`. |
| 02:08:56 | Clog + Mlog | Mlog records `photo timeOut`, capture state `2`, then state `5` and app-facing state `0`. Clog reports `gp_list_count 0`, empty output and `captureImage ret 0` with no returned path. |
| ~02:08–02:09 (user report) | User | User reported a one-second countdown, Live View visible briefly, then black screen/red circle; later reported camera control returned and asked whether an image had been captured. |
| 02:10:43–02:10:44 | Mlog | An additional `SP_0155.jpg` request appears in the device log without a corresponding user observation in this record. Mlog shows request field `b:5000`, then capture state `-1` and `PHOTO_RECORD Fail`. Origin is not assigned here. |
| 02:10:56–02:10:57 | Mlog | An additional `SP_0156.jpg` request appears without a corresponding user observation in this record. Mlog records state `1`, then `-110` and `PHOTO_RECORD Fail`. Origin is not assigned here. |
| 02:11:05 | Mlog | Camera-info reports `manufacturer:none`, `model:none`, `state:0`. |
| 02:11:29 | Clog + Mlog | Additional `SP_0157.jpg` request. Mlog reports `bulb:0`; Clog reads shutter `1/1000s`, RAW+JPEG, then Pentax `InitiateCapture` returns PTP `0x2001`. |
| 02:12:33 | Clog + Mlog | The SP_0157 operation reaches `photo timeOut`; no camera files are listed or published for it in the log. |
| 02:13:13–02:13:26 | Clog + Mlog | Camera-facing state changes to 0, then app command 274 requests state 1; by 02:13:26 the camera is reported present again as Pentax K-3 Mark III, state 1. This precedes the later kernel USB-removal record. |
| 02:15:04 | Clog + Mlog | Linux netlink records USB `remove@.../1-1.2:1.0` and then device removal at `.../1-1.2`; firmware logs `usb_disconnect` and reports camera state 0. This is an actual USB detach event, unlike camera-info `state:0` alone. The user transcript does not establish whether this detach was intentional. |
| 02:15:11 | Clog + Mlog | Camera initialization reports `sp_Gphoto_Init ret -5` and “set the port prior to initialization”; this occurs after the recorded USB removal. No subsequent camera recovery is visible in the collected interval. |
| 02:13:06 | Collection record | First collection timestamp. Active `/app/Clog.txt` and `/app/Mlog.txt` were snapshotted; active Mlog was zero bytes. Rotated logs 177–180 are included in full. |
| ~02:20 | Collection record | Persistent rotated Clog/Mlog files were refreshed after the device continued running; Clog includes short client connect/disconnect traffic through ~02:20. |

## Related log observations (not interpreted here)

- Before and around the Bulb attempts, Clog contains repeated preview reads of
  `0xa008` with zero bytes after 30 attempts (~1.2–1.3 seconds). After the two
  camera reconnects, Clog records successful preview reads (`0x2001`, roughly
  70–76 KB).
- Mlog contains short-lived TCP client connections from `192.168.0.4` that send
  code `266` and close; the client count returns from 3 to 2. The logs do not
  identify those clients as Benro Connect or OpenPolaris.
- USB events are distinguished by evidence type: the 02:15:04 netlink `remove@`
  and `usb_disconnect` records prove an actual USB detach. Earlier camera-info
  `state:0` / `state:-5` records alone do not prove detach. User-reported
  unplug/reconnect steps at ~02:03 and ~02:06 are operator-directed and are not
  classified as spontaneous faults.
- No shutter request was issued by the log-collection commands.

## Raw files and integrity

All files under `raw/` are unedited device-log copies. The rotated files were
downloaded from `/app/sd/system/log/`; `Clog.txt` and `Mlog.txt` are active-log
snapshots from `/app/`. SHA-256 values are in `SHA256SUMS`. The active-log
snapshot was taken at the time recorded above; the device continued running.
`Mlog.txt` was empty at snapshot time. The rotated Mlog contains the application
events for this test window.

The archive contains complete rotated Clog/Mlog files 000177–000180, including
preceding same-session context, rather than excerpts. Logs 000176 and earlier
are outside this session's selected rotation window and are not represented as
part of this bundle. The refreshed 000180 files supersede the earlier snapshot
of those rotating logs; the active Clog remains a point-in-time snapshot and
can change while the device runs.

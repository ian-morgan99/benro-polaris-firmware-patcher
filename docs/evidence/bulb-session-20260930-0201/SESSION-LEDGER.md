# Bulb-mode camera session — evidence ledger

This is a timestamped record of the observed session and the corresponding
device-log events. It intentionally records events, not a root-cause conclusion.

## Capture context

- Date: 2026-09-30.
- Polaris reported `FwVer:6.0.0.54.43;date:2026.09.30;`.
- Device `date -u` at final collection: `Wed Sep 30 02:13:06 UTC 2026`.
- Mlog identifies a Pentax K-3 Mark III (`25fb:0189`); `photoFormat:2` and the
  camera configuration log spells that value `RAW+JPEG`.
- User-reported setup for this sequence: switched to Bulb, selected a 1-second
  timer; later disconnected the camera to inspect settings and confirmed it was
  RAW+JPG before retrying.
- The user reported UI observations below; the archive contains no screen/video
  recording. Device timestamps are UTC; user-reported times are retained as
  given and treated as approximate unless a matching log timestamp is shown.

## Test ledger

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
| 02:11:29–02:11:56 | Mlog | An additional `SP_0157.jpg` request appears without a corresponding user observation in this record. The archived Mlog ends without a terminal result for this request. Origin is not assigned here. |
| 02:13:06 | Collection record | Device UTC time was read; current `/app/Clog.txt` and `/app/Mlog.txt` were snapshotted. Active Mlog was zero bytes at collection. Rotated logs 177–180 are included in full. |

## Related log observations (not interpreted here)

- Before and around the Bulb attempts, Clog contains repeated preview reads of
  `0xa008` with zero bytes after 30 attempts (~1.2–1.3 seconds). After the two
  camera reconnects, Clog records successful preview reads (`0x2001`, roughly
  70–76 KB).
- Mlog contains short-lived TCP client connections from `192.168.0.4` that send
  code `266` and close; the client count returns from 3 to 2. The logs do not
  identify those clients as Benro Connect or OpenPolaris.
- No USB kernel disconnect evidence is asserted by this ledger. The camera-info
  `state:0` / `state:-5` events above are reproduced as logged; they are not
  relabelled as physical USB detach events.
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
part of this bundle.

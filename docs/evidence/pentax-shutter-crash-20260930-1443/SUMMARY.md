# Pentax shutter failure after manual shot — 2026-09-30 14:43 (operator/device clock)

## Result

This was a repeatable Polaris capture-owner failure, not an OpenPolaris idle
connection crash. The user reported the camera battery was replaced at 14:40,
and that OpenPolaris plus two Benro Connect clients were connected without a
crash before the manual shutter attempt.

At 14:43:03, Benro's Mlog recorded a normal M-mode request (`bulb:0`) for
`SP_0152.jpg`. Clog read the camera shutter as `1/1000s`, reported RAW+JPEG,
entered `gp_camera_capture`, passed Pentax preconditions (`PTP 0x2001`, 576
bytes), and received `PTP 0x2001` from `InitiateCapture`. No later candidate,
transfer, finalization, publication, or successful API-return boundary appears
for that request.

At 14:43:15, `polestar_app` logged that pgphoto had exited and restarted it. The
append-only `/app/stage2-crash.log` had a new SIGSEGV record with PC and fault
address `0xb5600af0`; its current handler does not save the ARM registers or
process map needed to resolve that address to a function. The operation remained
reported as active (`mode:1;state:1`) until `photo timeOut` at 14:44:07.

At 14:44:38, the camera still enumerated as `25fb:0189`, pgphoto was running
again, and the firmware identity remained `6.0.0.54.43` with embedded source
`fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`. The evidence therefore identifies
the Polaris pgphoto owner crash/restart; it does not establish a physical camera
USB detach or camera reboot during this shot.

Clock note: the operator's 14:40/14:43 timestamps match the log wall-clock
labels. At collection, device `date -u` said 14:44:38 while the host gate log
was 13:48 UTC; the device clock was approximately one hour ahead of host UTC.
This record therefore preserves operator/device time and does not use the
device's `date -u` label as an independently verified UTC timestamp.

The user's report that the camera shutter appeared to stay open for a while is
preserved as an observation. Device logs say this request was `bulb:0` and the
camera reported `1/1000s`; those facts do not match an intentional long Bulb
exposure. The physical appearance is not enough to override the logged request
and setting.

## Evidence files

- `raw/sd/system/log/Clog_000182.log` and `Mlog_000182.log`: complete rotated
  logs captured after the event.
- `raw/Clog.txt` and `Mlog.txt`: active logs at collection time.
- `raw/stage2-crash.log`: persisted crash entries, including the newest
  `0xb5600af0` record.
- `raw/device-state.txt`: firmware, USB enumeration, process state, recent
  kernel messages, and persistent log listing at 14:44:38 UTC.
- `raw/active-logs.tar.gz` and `raw/rotated-logs.tar.gz`: original compressed
  transfers. `raw/failed-combined-stdout.partial` is retained but invalid as a
  tar archive; the first collection accidentally mixed diagnostic text with
  tar bytes. It was excluded from this canonical bundle; the separated
  transfers above are the verified evidence inputs.

SHA-256 of the primary extracted records:

| File | SHA-256 |
| --- | --- |
| `raw/Clog.txt` | `f54c42e42931802e559333bad159bfbbc70dd34b0e748e59c24304c556222528` |
| `raw/Mlog.txt` | `e65aa94efa0db5054c5ebe880b1fe9ae9061bb0c5b427666095766a2c4a017e9` |
| `raw/stage2-crash.log` | `aec8c4f54a4fb35814aa71a41efbbcb8f87c10bd4dc693faa287b9b8fe049587` |
| `raw/sd/system/log/Clog_000182.log` | `d939c248b50e493f78fc2fe93ca01da296f44be961c4338645ceb5e6849d843e` |
| `raw/sd/system/log/Mlog_000182.log` | `8b2ea24065c9d96916d992f935e30310e3bc8813c39b9c5f5eaa569c01a81274` |

## Next implementation/test action

Preserve pre-shutter admission and the unresolved-output barrier. The immediate
instrumentation gap is the Stage-2 SIGSEGV record: add crash-time ARM LR/SP and
general registers plus `/proc/self/maps`, run the full offline gate, then build
one provenance-complete diagnostic FwPkt. Repeat one source-attributed M-mode
capture with no overlapping manual/scripted request; correlate `SP_0152`-style
request, InitiateCapture, crash map/registers, candidate/output events, watchdog
restart, and terminal API result. Do not classify PTP command acceptance as an
image capture.

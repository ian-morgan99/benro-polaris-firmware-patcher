# o-v12j live-camera regression evidence (2026-09-23)

Candidate: `6.0.0.54.20-o-v12j-lifecycle-lvoff`

Device identity was proved before collection: Polaris AP BSSID
`48:E7:DA:D4:B5:73`, route to `192.168.0.1` over the Wi-Fi interface, and
`/app/FwVer` reporting the candidate above. The attached K-3 III enumerated as
USB `25fb:0189`.

## First divergent operation

The archived logs show successful preview frames immediately before the app's
still-capture request. At device time `19:23:53.647`, Mlog/Clog record IPC code
264 for `/app/sd/normal/SP_0073.jpg`. Stage-2 then reads the camera's declared
format as `RAW+JPEG`, reports `numOfCaptureImage 2`, and enters exactly one
`gp_camera_capture(GP_CAPTURE_IMAGE)` call:

```
[stage2] capture[1]: enter type=0 mono=2334
```

There is no subsequent libgphoto2/Pentax capture transaction and no
`real gp_camera_capture returned` line. Instead, after `updateViewFinder`, the
process dies:

```
[stage2] *** CRASH sig=11 (SIGSEGV) si_addr=0x00000004 pc=0x00000004
```

The wrapper reports that address `0x4` is neither its slot region, its stub,
nor a current slot target. Therefore this run does **not** support an
image-count timeout diagnosis: capture dies before the RAW+JPEG reconciliation
logic can run.

## Fallout

After the crash, pgphoto restarts. The camera remains present in USB scans, but
every new initialization receives `OpenSession` `0x02ff` or `0x02fa`. The
three-attempt recovery sequence issues USB control resets and ultimately emits
`state:-10`; the cycle repeats at roughly 26-second intervals for the rest of
the captured log. USB enumeration alone therefore did not mean that the PTP
session had recovered.

## Candidate disposition and next isolation

o-v12j mixed the libgphoto2 capture-format work with patcher commit `a710c09`,
which changed connection-time Live View policy and wrote both
`pentaxpclvkeep=0` and `pentaxpclvmode=0`. The archived logs show the latter
write returning `-2`. This candidate is failed and must not be used for further
qualification.

The next candidate removes only the three runtime/test-file changes introduced
by `a710c09`, restoring the previously exercised keep-LV behavior while retaining
the same libgphoto2 commit. That is a clean A/B for the TA-requested isolation;
it does not claim that persistent Live View is the final thermal architecture.
Demand-owned Live View start/stop remains separate work.

## Files

- `raw/Mlog.txt`, `raw/Clog.txt`: current logs at collection time.
- `raw/sd/system/log/Mlog_000135.log`, `raw/sd/system/log/Clog_000135.log`:
  archived logs containing the first capture crash and restart loop.

SHA-256 values are recorded in `SHA256SUMS`.

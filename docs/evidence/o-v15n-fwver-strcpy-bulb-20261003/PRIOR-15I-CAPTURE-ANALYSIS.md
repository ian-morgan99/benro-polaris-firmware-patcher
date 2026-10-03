# Prior 15i capture failure analysis

This is the evidence that was available locally while investigating the
reported Manual/Bulb regression. It is **not** a claim that these files came
from the currently installed o-v15n runtime: `DEVICE-IDENTITY.txt` identifies
the archive as `o-v15i-pentax-bulb-matched` with libgphoto2
`6979070597ebddbaa5f1cff1e56b7597e4594ed2`.

## What the logs prove

At `14:29:13.467`, the app sent the normal Manual capture request:

```text
code:264; state:1; bulb:0; c:-1
```

The same request was logged with shutter `00:01`, image format `RAW+JPEG`,
and `numOfCaptureImage 2`. Therefore this failure was not caused by entering
Bulb mode and was not a test of a non-zero Bulb duration.

The lower-level capture path did reach the camera:

```text
gp_camera_capture: enter
preconditions-return ptp=0x2001 size=576
initiate-return ptp=0x2001
```

`0x2001` is the accepted InitiateCapture response. The failure happened after
acceptance, while waiting for the camera's output/capture completion. No
successful file publication is present in this capture window.

At `14:30:17.468`, the firmware watchdog reported `photo timeOut`. Two seconds
later the lower-level trace recorded `capture end -66249 ms`, `gp_list_count 0`,
and `get file to buffer -1 ms`. Despite that negative result, the app logged
`captureImage ret 0` and emitted `state:2` followed by `state:5` for
`SP_0177.jpg`. That is a false success/status mapping: an accepted shutter
request was converted into a late file/status message without a proven file.

During the wait, Clog contains repeated Stage-2 loader initialisation and
preview shim activity. Mlog also records an earlier `pgphoto is exit,reboot it`
and a competing restart-lock refusal at `14:27:56`. Those entries prove
session/restart churn existed around this test, but do not by themselves prove
which restart caused the capture loss.

## What this explains

The firmware-version change cannot explain this particular Manual failure: the
request carries `bulb:0`, and the captured archive predates the o-v15n exact
version candidate. The evidence instead points to a post-InitiateCapture
session/output lifecycle failure, compounded by the application reporting
success after the lower layer returned a negative capture result.

The release process allowed the regression because the candidate had passed
offline package and ABI checks, but the camera was not available for a live
Manual two-shot canary. The offline tests prove that a `state:1;bulb:0` frame
is formed; they cannot prove that the camera publishes the expected RAW/JPEG
outputs after `0x2001`.

## Remaining evidence boundary

The Polaris was subsequently unreachable, so the current o-v15n Mlog/Clog
could not yet be pulled. This report must not be used to declare o-v15n's
Manual or Bulb behavior fixed or regressed until the current device archive is
retrieved and its `/app/FwVer` and provenance are recorded alongside the logs.

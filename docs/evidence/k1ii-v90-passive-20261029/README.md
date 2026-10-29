# K-1 II v90 passive observation — 2026-10-29

This is a limited, read-only observation, not a physical qualification. The
camera remained owned by the existing pgphoto process. No camera control,
capture, process restart, firmware write or install was performed.

At approximately 22:28 UTC the host was associated with SSID
`polaris_d13e86`, BSSID `48:e7:da:d4:b5:73`, through `wlp8s0`; the route to
`192.168.0.1` also used that interface. The device reported:

```text
FwVer:6.0.0.54.90;date:2026.10.29;
build_id=6.0.0.54.90-o-v18m-k1ii-pgphoto-readiness-20261029
git_commit=63a894b0821a510fc40244c5cc4ef84a5220a91c
patcher_commit=f344e41261a886f8f6107b9467095bc90b3835a1
camera USB 25fb:0183, /sys/bus/usb/devices/1-1.2/speed: 480
pgphoto PID 16080; polestar_app PID 249; TCP 8080 LISTEN
```

USB `480` is the negotiated link speed in Mb/s, not a measurement of image
transfer throughput. It does not explain the operator's reported capture
timings by itself.

The pgphoto maps used the older-looking path
`/app/lib/libgphoto2/2.5.27.1/ptp2.so`, while the core came from Stage-2.
The running process had Stage-2 CAMLIBS/IOLIBS environment values. On-device
MD5s show the old-path and Stage-2 copies were byte-identical at observation:

```text
ptp2.so           0b08b092fcda26bcff75e2acb29e422a
usb1.so           1da867012dc9b429056a1aaa713c2b1b
libgphoto2.so.6   dfd14bc5b6d69d500d61dea4e557955a
libgphoto2_port   230b6fbc8cfe9190022c49d93febac45
```

This excludes a byte mismatch between these paired paths at that moment; it
does not establish performance or overall stack correctness. Commit `511b7dd`
is an ancestor of the v90 patcher commit and contains the generic empty-choice
guard. An earlier statement that this guard existed only in a dirty feature
branch and was absent from main was incorrect for v90; its presence does not
establish why Benro Connect crashed.

The observed Clog tail included valid preview-frame messages and repeated
`waitCameraIdle busy` lines around requests for shutter, aperture and other
controls. At `22:27:59` a 56-choice shutter response was logged, and a WB
choice response was logged at `22:28:04`. A busy message reflects pgphoto's
application scheduler; it does not identify the operation holding it or prove a
PTP or camera defect. No complete latency timeline was captured.

## Connection and evidence limitation

The documented `scripts/pull-mlog-clog.sh` was started to preserve the logs.
Its remote tar stream failed with `Input/output error` and `Unexpected EOF`;
the Polaris Wi-Fi association dropped during the transfer. The script cleaned
its temporary staging directory, so no complete archive was produced. The
transfer may have contributed to the drop; the available evidence does not
establish its cause. The operator was informed immediately. Subsequent Bluetooth
scan/connect and the documented wake script did not re-establish the link in
this session. Do not repeat a bulk transfer while the connection is fragile.

Prior operator-reported v90 failures and their timings are recorded in
[issue #253](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/253).
They remain unqualified and must not be represented as fixed by the 90-second
startup window. Use the preserved on-device logs, if accessible again, to trace
individual request boundaries and the first divergence before changing a
camera protocol path.

## Earlier v89 snapshot and candidate startup cost

An existing local snapshot, `/tmp/k1ii-polaris-logs.GpBKBK/Clog.txt`, has
SHA-256 `310d6011c88a8fc5384ff83c3a252f1443794537bde49799f843723696afc6d7`.
It is a temporary file and is not an archived v90 log. In one v89 startup the
last timestamp before a missing `autofocusdrive` report was 19:05:33.631; the
report appeared at 19:05:38.933. The Stage-2 guard reported `GP_OK without
widget for autofocusdrive; returning CAMERA_BUSY` in between, without its own
timestamp. This 5.302-second interval is not proof of any single PTP operation's
duration. The subsequent `updateCameraViewFinder` interval was 6.341 seconds
and ended with `ret:-1`; `updateCameraAutoFocus` then took 5.413 seconds and
also returned `-1`.

Offline disassembly shows `checkWidgetForName` calls `_find_widget_by_name`,
which invokes `gp_camera_get_single_config` and, for any nonzero result, calls
`gp_camera_get_config` to search the full configuration tree. This is a
candidate explanation for expensive repeat enumeration when a control is absent
or temporarily unavailable; the snapshot does not time the individual calls.
The lookup routine's 588 bytes at `0x0f26d0` are identical in the recorded v89
and v90 pgphoto artifacts (SHA-256
`122fe7132bc9ec154222bffcbb45bd4cec08dd8394ae864eaf3e8599d51ee961`). The
complete binaries differ. Do not infer that every v90 delay has this cause,
or skip a control without proving its model-specific availability and preserving
non-Pentax behavior. The detailed follow-up is on issue #253.

## v90 app-facing EV response after reconnection

The operator re-established the connection through Benro Connect on Android.
At 22:49 UTC the PC was again associated with the verified Polaris BSSID, and
the device still reported v90, the same camera and the same pgphoto and
polestar PIDs. Uptime continued, so the earlier Wi-Fi loss was not a reboot.
Only small filtered log tails were read; no camera request, capture, setting
change or daemon restart was sent by this investigation.

At 22:46:37.417 Clog shows pgphoto receiving the EV request. At 22:46:38.451
it logs `getCameraConfig from local configType 2 ret 0` and sends
`code[267],val[RD:0;V:;R:;]`; Mlog shows that same empty result forwarded to
the app. A 22:46:35.346 upstream request-to-response interval was approximately
3.1 seconds, including time queued behind other settings requests. These are
device log timestamps, not a measured Android gesture-to-screen latency.

In the pinned pgphoto binary, `deal_camera_control_handler` calls
`waitCameraIdle(500)`; the idle loop sleeps 2 ms per busy iteration. On timeout
the handler returns `-2110`. `getCameraConfig` recognizes that value and calls
`getLocalCameraParamInfo`, which returns a cache pointer for EV without checking
whether the fields have been populated. It then formats the returned fields as
a successful response. The approximately 1.034-second EV handler interval is
consistent with this path; it does not establish what held the busy status.

The private Benro Connect source shows that its EV parser treats `RD:0` as
available, defaults an unparseable selection index, and retains the range for
the picker. Its UI catches EV numeric-conversion errors and can retain an empty
entry. This explains an empty/invalid selector; it does not prove the earlier
app crash. Simply returning an error from `getCameraConfig` is not an established
fix: its caller sends the formatted response only after success, so the client
may instead receive no response. The first-divergence investigation and safe
unavailable/retry contract remain open in
[issue #253](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/253#issuecomment-6510351294).

## Interrupted direct-on-Polaris attempt

The operator subsequently authorised changes to the live session but could not
move the camera to the PC. A read-only direct-on-Polaris lookup was planned,
with pgphoto to be restarted afterwards. The diagnostic stopped verified
pgphoto PID `16080` at about 22:58 UTC, but did **not** run the gphoto2 lookup:
the device's BusyBox `timeout` requires `-t SECS`, and the diagnostic used the
host syntax `timeout SECS`. The same mistake prevented its cleanup from invoking
the restart helper. No direct-library EV result or debug trace was produced.

A manual call to the packaged `/app/restart_gphoto` then reported that another
restart already held its lock; that existing restart launched pgphoto PID
`29386`. By 22:58:41, TCP 8080 was listening and subsequent Clog messages
reported successful preview-frame transfers, with one earlier incomplete-frame
error. On restart, Clog reported an already-open Pentax session and an
observe-only state; full settings, capture, and app recovery were not verified.
In the resumed session Clog also recorded another empty cached WB response.
Do not treat the listener or frame-transfer messages as complete qualification.
No firmware files or camera settings were changed by the diagnostic.

The local diagnostic script was corrected to use BusyBox `timeout -t`, but was
not rerun: the user cannot physically recover the camera at present and a
further session interruption risks preserving or worsening a stale session.

## Prepared direct-PC build, no attached camera

The clean source checkout at libgphoto2 commit
`63a894b0821a510fc40244c5cc4ef84a5220a91c` was built into the isolated prefix
`/tmp/k1ii-v90-direct.AYgHxEM9/prefix`, with `ptp2`, `pentax`, `directory`,
`libusb1`, `usbscsi`, and Pentax research capture enabled. The host gphoto2
client reported libgphoto2 `2.5.34` using that prefix; loader diagnostics showed
the isolated core, port and `ptp2` module paths. The `--version` and camera
list checks did not open a camera. This is the same source SHA, not the same
binary build: host Meson dependencies and build options differ from the shipped
ARM/autotools build. The temporary prefix may not survive a system cleanup.

The first unfiltered Meson test run inadvertently included the upstream
`no-ci` hardware-oriented `test-gp-port`: it enumerated a host USB port and
failed with bad parameters before establishing an open device; 18 other tests
passed. A repeat explicitly excluded `no-ci` and all 18 selected tests passed.
No K-1 II was attached to the PC, so there is no direct EV result. When the
operator can attach it, verify the exact USB identity and loaded modules again,
run a single read-only generic EV lookup with debug tracing, and classify the
first failing operation before changing libgphoto2.

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

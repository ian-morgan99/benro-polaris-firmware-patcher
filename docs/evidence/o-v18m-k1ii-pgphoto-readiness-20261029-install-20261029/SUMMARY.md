# v90 installation evidence

## Identity

- Candidate: `o-v18m-k1ii-pgphoto-readiness-20261029`
- Display firmware: `6.0.0.54.90`
- Build ID: `6.0.0.54.90-o-v18m-k1ii-pgphoto-readiness-20261029`
- libgphoto2: `63a894b0821a510fc40244c5cc4ef84a5220a91c`
- Patcher artifact input: `f344e41261a886f8f6107b9467095bc90b3835a1`
- ZIP SHA-256: `829fd30e79a52b2155bd865e1fb584fc82f7785bfad31d4878de7fe31a01ab34`
- ZIP MD5: `4c005b0acf50676fa7e1d32ffbac9cd6`
- appfs MD5: `d1e290f5509cee93f7e2d1b9b5666c36`

## Deployment

The documented Bluetooth/Wi-Fi preflight reached `READY`. The supported
`scripts/release/release-fwpkt.sh` installer then:

- confirmed the target was v89 and idle;
- staged the extracted `FwPkt/` tree, not only the ZIP;
- verified all six firmwareInfo MD5s on-device;
- rebooted through the normal upgrade watcher;
- proved a real reboot by uptime reset from `3467` to `29` seconds;
- verified the installed build ID, display version, source provenance, and
  mandatory payload identity.

The device now reports:

```text
FwVer:6.0.0.54.90;date:2026.10.29;
build_id=6.0.0.54.90-o-v18m-k1ii-pgphoto-readiness-20261029
```

The installer receipt and status are published with the firmware packet in
PrivateResearch.

## Regression status

Offline and packaged gates remain green: 24 deterministic checks, 393 Python
tests, and 16 pre-release checks passed; one stock-manifest cross-check remains
a documented prerequisite skip because the stock input is held outside the
public checkout.

The post-deployment qualification runner was started, but it failed closed at
preflight before any shutter or setting operation:

```text
286@manufacturer:none;model:none;state:-5;storage:0;photoFormat:0;
ABORT: camera not in the attached state
```

This is **BLOCKED / UNRUN**, not a camera failure. The Polaris runtime was
healthy (`polestar_app` and `pgphoto` running), but no camera was present on
USB after the reboot. Attach and power the intended camera, verify its PTP USB
identity, then rerun `docs/POST-V90-REGRESSION-GATE.md` from Gate 2 onward.

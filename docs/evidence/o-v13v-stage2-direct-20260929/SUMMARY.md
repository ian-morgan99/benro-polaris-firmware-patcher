# o-v13v Stage-2 direct-capture candidate — 2026-09-29

## Superseding instability finding — 2026-09-29 15:18–15:26 UTC

The earlier statement that the camera was absent was true only before it was
powered on. With the camera attached and configured RAW+JPEG, one actual
capture request reached the Pentax `InitiateCapture` operation and received
PTP `0x2001`, but the operation did not complete: no DNG/JPEG for SP_0134 was
published, pgphoto segfaulted about two seconds after the request, and the
Benro app later timed out. This is a confirmed failed physical canary, not a
successful capture. A subsequent request was correctly rejected as camera busy
by the pre-shutter admission gate, so it did not send another shutter.

The core dump shows the crash in a progress-callback indirect call from the
PTP camlib. The callback pointer came from `PTPData.context`, a mutable field
shared by calls using the same camera; its value at the crash was not the
valid GPContext passed to the capture operation. The evidence strongly points
to concurrent/stale operation-context replacement as the crash cause. This is
an evidence-backed diagnosis, but hardware confirmation of the fix remains
required.

Fix: libgphoto2 `main` commit
[`fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`](https://github.com/ian-morgan99/libgphoto2/commit/fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd)
removes the shared PTPData context and binds each operation's GPContext to the
calling thread instead. The regression test proves that two threads using the
same camera owner retain separate contexts. The source build and all 14
deterministic libgphoto2 tests passed. A clean-source firmware release build
has not completed yet: the first attempt correctly refused to build because
this patcher checkout contained this updated evidence and local raw logs.

The failed-shot core is retained outside git at
`/tmp/pentax-core.glo9tv/core` (SHA-256
`865d355351d9b58f6dc81dbbe114bff7bda447319e02a3f6d299deb3df5a2c5c`). Raw
device logs remain local and ignored/untracked; their current hashes are
recorded in the work session rather than published because they contain
device/runtime identifiers. Do not send another shutter until the fix is
packaged, installed through the supported update path, and the camera/session
has been cleanly recovered.

## Plain-English result

One new firmware candidate was built from clean `main` sources. It fixes an
integration mismatch: the installed wrapper enabled an extra Stage-2 function
call around every still capture by default, even though the production policy
and regression test require capture to call the resolved libgphoto2 core
directly. The trace wrapper remains available only when explicitly enabled.

This is a plausible contributor to the reported failure, not a proven root
cause. The candidate is installed and its source/artifact/runtime identity is
verified, but the physical capture canary is blocked: after reboot the camera
is no longer enumerated on USB, the Benro control probe cannot connect to port
9090, and the `polestar_app` process is absent. Do not call this Pentax-
qualified. The known restart-durability gap for an accepted capture whose
output is not visible remains open.

## Source and artifact identity

- Patcher source: `24f64f5f6ce25fd7bba35cd597e0e3d43e96373f`, `main`, clean.
- libgphoto2 source: `718019fa0bb579cc5e8277ff2fa1f998a0fd37b4`, `main`, clean.
- Harness source: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`, `main`, clean.
- Build id: `6.0.0.54.41-o-v13v-stage2-direct-20260929`.
- Polaris / Benro Connect display value: `6.0.0.54.41`.
- Selected libgphoto2 camlibs: `ptp2,pentax`.
- Stock FwPkt SHA-256: `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`.
- ZIP: `out/o-v13v-stage2-direct-20260929/FwPkt.zip`.
- ZIP MD5: `db756a059830956ec4e66caeed706806`.
- ZIP SHA-256: `400d417c90a486ec15b9830b9773b8320b3693f0aa5a69259db126f92d428904`.
- appfs MD5: `c658bd37c3e70a13ea5f8b4535d8ff97`.
- PrivateResearch artifact commit: `dade1a7e7`, path
  `firmware-packets/o-v13v-stage2-direct-20260929/FwPkt.zip`.

## Changes

- The pgphoto wrapper now defaults `STAGE2_CAPTURE_TRACE=0`; an explicit
  environment override of `1` still turns on Stage-2 outer entry/return logs.
- The Stage-2 loader test verifies unset/zero preserve the exact resolved core
  capture function and explicit one selects the trace wrapper.
- The actual generated wrapper test verifies the shipped default is zero and
  explicit runtime selection of one is preserved.
- Recovery documentation and CURRENT-STATE record that strict admission and
  output ownership are still only process/session durable in libgphoto2; this
  candidate does not solve restart durability.

## Deterministic validation

- libgphoto2 release regression build/test: passed (build-release-candidate.sh
  exited successfully; the documented host-dependent `no-ci:test-gp-port` is
  excluded because this host has no supported DTR/CTS fixture).
- Patcher Stage-2 loader test: passed.
- Patcher pgphoto wrapper default/override test: passed.
- Patcher offline pre-release gate: 14 container checks + 24 Python checks,
  zero failures/skips.
- Package gate: FwPkt structure and firmwareInfo MD5 manifest passed.
- Test harness: `62 passed`.
- ZIP/appfs content proof: extracted appfs from the exact ZIP. SHA-256 matches
  the generated bundle for both core copies, both port copies, both ptp2 copies,
  Pentax camlib, both usb1 copies, `libpolaris_stage2.so`,
  `pgphoto.stage2ondisk`, and `/app/bin/pgphoto`. Embedded provenance exactly
  matches `build-source-provenance.txt`; packaged wrapper contains trace default
  `0`.
- Full-stack build note: StarShoot adapter compiled. iPolar/libuvc adapter
  compile was skipped because libuvc headers are absent; its frame-store
  component compiled. This does not claim functional UVC camera support.

## Physical state before installation

Read-only checks confirmed Polaris identity/route, current o-v13s runtime, and
Pentax USB `25fb:0189`. The first Benro probe during reinitialisation returned
`state=-5`; a later single read-only probe reported K-3 Mark III `state=1`,
storage 2, photoFormat 2. The supervisor logged a `none -> 1-1.2` USB identity
change and a pgphoto restart (`4/6` budget). No shutter was sent and no package
was staged. Full interpretation and raw-log hashes are in
[`live-read-only-20260929-1430`](live-read-only-20260929-1430/README.md).

Independent review is still pending, and restart-durable output ownership is
still open. The operator explicitly authorized installation and testing. The
candidate was installed through the sanctioned SD-card `FwPkt/` path on
2026-09-29. All six staged payload sizes and MD5s matched the candidate's
`firmwareInfo` before reboot. Post-reboot Polaris identity and provenance
matched the intended registry row:

- FwVer: `6.0.0.54.41` (build id
  `6.0.0.54.41-o-v13v-stage2-direct-20260929`).
- libgphoto2: `718019fa0bb579cc5e8277ff2fa1f998a0fd37b4`.
- patcher: `24f64f5f6ce25fd7bba35cd597e0e3d43e96373f`.
- Core and port MD5s match between `/app/lib/stage2` and `/app/lib`.
- `/proc/250/maps` confirms the running pgphoto loads both core and port from
  `/app/lib/stage2`; pgphoto listens on 8080.

The physical canary did not run. `scripts/canary-probe.py --probe` failed with
`ConnectionRefusedError` to port 9090. At the same check, `lsusb` showed no
Pentax `25fb` device, `/app/bin/polestar_app` was not running, and Clog
contained repeated `SP_sendMsg Fail ... code[295]`. The gimbal remains
reachable over its verified AP/SSH route, so this is not a router-identity
confusion. No shutter was sent. Collect fresh logs and restore camera/control
service before any physical capture attempt; do not retry a shutter blindly.

The post-install `./tests/run_prerelease_gate.sh --canary --expected-files 1`
run completed with 2 passed (14 container, 24 Python), 0 failed, and the live
device gate skipped. The skip reflects the 9090 probe failure; it is not a
physical canary pass. Clog had `SP_sendMsg Fail ... code[295]` repeating, while
`polestar_app` and Pentax USB were absent. Dmesg showed only the hub
enumeration, not a camera attach. I did not restart/kill device processes or
send a shutter. A physical camera reconnect alone may not restore the missing
9090 service; inspect fresh boot logs before attempting a canary.

Post-install matched-stack hashes observed on Polaris:

| Component | MD5 | Path |
| --- | --- | --- |
| libgphoto2 core | `4ef64d8950eee70d9200093286fb0f3b` | `/app/lib/stage2/libgphoto2.so.6` and `/app/lib/libgphoto2.so.6` |
| libgphoto2 port | `ad50e83594397aef48b63ed2375890cc` | `/app/lib/stage2/libgphoto2_port.so.12` and `/app/lib/libgphoto2_port.so.12` |
| ptp2 camlib | `1d94dfe84203b7210cb014267228a4af` | `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so` |
| Pentax camlib | `151750bae93f58801cd02176c6b38df9` | `/app/lib/stage2/libgphoto2/2.5.34/pentax.so` |
| usb1 port driver | `4423bba29bf8c5d899598841ec3e6310` | `/app/lib/stage2/libgphoto2_port/0.12.2/usb1.so` |

## Operator reboot follow-up — 2026-09-29 15:13 UTC

The operator reported getting Polaris to reboot after it initially would not
turn off. Bluetooth wake restored its AP, and identity checks again confirmed
SSID `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`, route via `wlp8s0`, and
FwVer/build provenance above. This time `polestar_app`, pgphoto, and TCP 9090
and 8080 were all present, so the earlier missing-control-service condition
was transient across the reboot.

The Pentax is still absent: `lsusb` shows no `25fb` device and the read-only
canary probe returned `manufacturer:none;model:none;state:-5;storage:0;photoFormat:0`.
Dmesg has no camera attach event. No shutter was sent. Physical test remains
blocked on the camera being powered on and reconnecting to USB while Polaris
stays powered on.

## Camera-absent stability spot check — 2026-09-29 15:14–15:15 UTC

After the operator reboot, I observed Polaris twice about 38 seconds apart,
then made one read-only 9090 probe. Across this short window the verified AP
and route remained available; `polaris_wifi_bt`, `polestar_app`, pgphoto and
the camera USB supervisor kept the same PIDs (`248`, `249`, `250`, `271`);
ports 8080/9090 remained listening; firmware/provenance remained o-v13v; and
Clog's `SP_sendMsg Fail` count remained zero. The 9090 probe completed and
reported no camera / `state=-5`, consistent with `lsusb` showing no Pentax.
This is a short post-reboot camera-absent stability spot check only, not a soak
test, capture test, or physical qualification.

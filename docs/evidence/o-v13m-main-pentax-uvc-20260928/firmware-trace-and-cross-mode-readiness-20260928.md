# Firmware trace readiness and cross-mode run status

## Candidate and trace verification

The existing registered v13m artifact is suitable for the planned capture
boundary trace; a rebuild is not required just to enable it.

* Patcher build source commit: `5f404ee8022337dda9791f88b3fb90fc67e805d3`
* libgphoto2 source: `caa3ca8343ba836928587f66ccbbce8dc9c1e04f`
* Build ID: `6.0.0.54.37-o-v13m-main-pentax-uvc`
* ZIP MD5: `dfdbf299bae3a82ce97ccc220abfcc82`
* ZIP SHA-256: `8645c5c02c3d27c796434b88c4b6d703d84590f3366d59dacc4f8a2f35a19b9c`
* appfs MD5: `1543fc470d8ab78fd2869a4c065fbfdb`

Read-only inspection of the actual packaged appfs confirmed:

* `/app/bin/pgphoto` exports `STAGE2_CAPTURE_TRACE=${STAGE2_CAPTURE_TRACE:-1}`;
* the packaged `libpolaris_stage2.so` contains `[stage2-trace] capture-enter`
  and `[stage2-trace] capture-return` markers.

This trace brackets `gp_camera_capture` entry and return. It does not by itself
identify a hardware PTP operation or reveal the internal native Astro/Panorama
scheduler in proprietary `polestar_app`.

## Harness and source regression results

* `benro-polaris-test-harness` `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`:
  **62/62 tests passed**. This validates recorded protocol/runtime contracts
  and synthetic generation/cancellation cases; it does not execute the
  firmware binary or model Pentax camera semantics.
* The newly scripted full libgphoto2 Meson suite was attempted on source
  `caa3ca834`. Result: 7 passed, 5 failed, 1 skipped. Failures were `test-gp-port`,
  `test-port-list`, generic `test-gphoto2`, generic `test-camera-list`, and
  `test-filesys` SIGSEGV; `test-pentax-aperture-alias` returned its documented
  skip status 77. This run is **not green** and must not be reported as such.
  The release script correctly stopped before building a new artifact.
* The already registered v13m package was previously through the patcher and
  package gates. It is not installed or hardware-qualified by this record.

## Physical run status

No physical comparison could be run in this session. The host was associated
with the home Ethernet route (`192.168.0.1 via 192.168.68.1`), not a Polaris
AP; SSH to `192.168.0.1` refused the connection. The prescribed Bluetooth
wake pulse did not establish a connection and no Polaris BSSID appeared. Thus
device identity and installed firmware could not be established; no capture
command was sent.

When the Polaris AP and route are available, first install/verify this exact
registered build using the sanctioned update procedure. Then collect separate
full-log runs in this order:

1. one ordinary still, then three ordinary consecutive stills;
2. a bounded native Astro intervalometer sequence, then one ordinary still;
3. Panorama and Pro Panorama separately, then one ordinary still.

For each: save Clog/Mlog, USB and process IDs, request/capture numbering,
`[stage2-trace] capture-enter/return`, libgphoto2/Pentax lifecycle and
InitiateCapture trace if emitted, file publication, and the next request. The
first error or disconnect ends that run; do not issue an automatic retry.

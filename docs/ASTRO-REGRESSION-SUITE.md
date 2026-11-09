# Astro regression and camera validation

The independent test-only suite is under `tests/astro_regression/`. It is
intended to be cherry-picked or merged into the Astro branch without changing
camera or firmware code. The suite's safety boundary is part of the test
contract: it can read link/state/site, upload a historic file to the explicit
test endpoint, and request a non-motor historic solve. It cannot capture,
move, calibrate, track, alter motor rates, or write EXIF.

## What it proves

The offline run validates:

- K-1 II (`25fb:0183`) and K-3 III (`25fb:0189`) identity metadata;
- the distinction between a live mount/WebUI and a published camera identity;
- the known K-3 III quarantined `state=-110`, `model=none` failure shape;
- the endpoint allow-list and historic solver safety flags;
- corpus hashes, dimensions, camera assumptions, and recorded reference/native
  result fields.

The live run validates the same contracts against the running WebUI and reports
camera identity failure separately from WebUI or mount availability. It uses
bounded requests and records the returned JSON. The historic-image run also
records an elapsed time and rejects a response that does not explicitly prove
`motor_control=false` and `exif_writeback=false`.

## Commands

```sh
bash tests/run_astro_regression.sh --offline
bash tests/run_astro_regression.sh --live --webui-url http://192.168.0.1:8090
bash tests/run_astro_regression.sh --live \
  --webui-url http://192.168.0.1:8090 \
  --historic-image /path/to/image.JPG \
  --solver reference --focal auto --sensor 23.3
```

The historic endpoint is for existing images only. Do not use it as a shortcut
for a physical camera test. Native results are comparison evidence and do not
qualify the native solver for release.

## Acceptance record for K-1 II and K-3 III

Run and retain one record per camera and candidate:

1. source commit, package hash, installed artifact hash, and catalogue/index
   manifest hash;
2. USB vendor/product and system path;
3. pgphoto startup, model publication, storage and battery reads;
4. settings read/write, focus, live view, capture completion and file transfer;
5. calibration and GoTo solve results, including repeated GoTo readings;
6. frame solve, EXIF writeback, target/rotation publication and drift result;
7. motor-rate adjustment only after its separate safety/hardware gates;
8. exact logs and operator-observed result.

The first four are not interchangeable: a USB device, a running pgphoto
process, a model string, and a transferred image prove different layers. A
successful historic solve proves neither the camera path nor motor safety.

## Known corpus evidence

`fixtures/images.manifest.json` records two external images by SHA-256 rather
than copying photographs into the repository. The K-3 III `_EVE4724.JPG`
reference solver result is a real positive; the native attempt timed out even
with a correct RA/Dec hint. `G7D9gnBg.jpeg` is an honest sparse-field negative
for the reference solver. The canonical benchmark evidence is recorded in
GitHub issue #255; native production qualification remains governed by #247 and
the native scale/index work in #287.

## Non-automated physical test checklist

The harness must not claim these from offline or WebUI historic tests:

- K-1 II and K-3 III are both physically recognized by the installed Astro
  candidate;
- capture and transfer work without stale restart-lock or rebind failure;
- live view and camera parameter behavior are correct on each model;
- Astro calibration, GoTo, drift correction, tracking and final photograph are
  safe and correct.

Those require a supervised Polaris window and the documented ZIP/Bluetooth-wake
deployment path. No SSH replacement or automatic flashing is part of this
suite.

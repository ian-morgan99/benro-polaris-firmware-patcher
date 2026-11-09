# Astro independent regression suite

This is a test-only, read-only qualification aid for the separate Astro
candidate. It deliberately does not replace the firmware release gates and it
does not send mount, camera, capture, tracking, or motor commands.

The suite has three layers:

1. Offline contract tests validate the camera identities, observed link
   snapshots, historic image metadata, endpoint allow-list, and fail-closed
   classification. These tests are deterministic and require only Python 3.
2. A live WebUI probe reads `/api/link`, `/api/state`, and `/api/site` from the
   supplied Astro WebUI address. A missing camera identity or quarantined
   session is reported as a failure even when the mount and WebUI are alive.
3. An optional historic-image probe uploads an existing image to the documented
   `/api/test/upload` endpoint and invokes `/api/test/solve`. The response must
   continue to declare `motor_control=false` and `exif_writeback=false`. It
   never calls a capture or movement endpoint.

The runner returns:

- `0` when every requested check passes;
- `1` when a requested check finds a regression;
- `2` when a requested live check is blocked because the WebUI is unavailable
  or the requested external fixture is absent.

## Quick start

From the repository root:

```sh
bash tests/run_astro_regression.sh --offline
```

For the Astro WebUI, with Polaris reachable on its private network:

```sh
bash tests/run_astro_regression.sh --live --webui-url http://192.168.0.1:8090
```

For an existing historic image, use a copy outside the firmware worktree when
possible. The probe is intentionally bounded and non-motor:

```sh
bash tests/run_astro_regression.sh --live \
  --webui-url http://192.168.0.1:8090 \
  --historic-image /path/to/image.JPG \
  --solver reference --focal auto --sensor 23.3
```

Use `--solver native` only as a research comparison. A native timeout or
failure must not be interpreted as permission to enable the native solver in a
release candidate.

## Corpus policy

The repository stores metadata and hashes, not camera photographs. This avoids
silently redistributing user photographs and keeps the test assets mergeable.
The known external corpus is recorded in `fixtures/images.manifest.json`.
Before accepting a new result, record the image SHA-256, camera model, pixel
dimensions, focal-length and sensor assumptions, solver, index/catalogue
identity, elapsed time, and the complete solved/failed result. A result from a
historic upload is not physical firmware qualification.

## Physical qualification remains manual

The following still requires a supervised test window and the documented
release/deployment process:

- USB enumeration and camera identity publication for both K-1 II and K-3 III;
- pgphoto session creation, restart/rebind, and recovery after disconnect;
- read-only settings, focus, live view, and capture completion;
- calibration, GoTo, repeated GoTo, and tracking safety;
- frame transfer, solve result, EXIF writeback, and target/rotation updates;
- drift measurement and any motor-rate adjustment.

The K-3 III stale restart-lock incident is represented by
`k3iii-link-quarantined.json`. It must remain a visible failure until the
accepted restart-lock fix is installed and the device layers are re-qualified.

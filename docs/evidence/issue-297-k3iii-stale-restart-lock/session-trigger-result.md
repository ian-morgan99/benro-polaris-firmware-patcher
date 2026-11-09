# Triggering a session after the lock fix — answers #297's open question

Requested on #297: "Something must ask pgphoto for a camera session post-restart, then
re-check /proc/<pid>/maps for pentax.so. If it loads, layer 3 was just 'nothing asked yet'."

## What was done

`GET http://192.168.0.1:8080/?action=stream` — the exact request `polaris-httpd` makes
itself (`polaris-httpd.c: sa.sin_port = htons(8080)` then `"GET /?action=stream HTTP/1.0"`).
Read-only; no settings written, nothing restarted.

## Result: the "nothing asked yet" option is refuted

pgphoto accepted the request and answered, so a client genuinely reached it:

```
http=200  bytes=22
body: --boundarydonotcross\r\n        (the MJPEG boundary, then nothing)
curl: (28) Operation timed out after 20001 ms with 22 bytes received
```

It emitted the multipart boundary and then produced **no frame**. While that connection was
established (`established_to_8080=1`, layer 4 PASS):

```
[FAIL] layer3-camlib -- a client is connected but no pentax.so/ptp2.so is mapped
                      -- gp_camera_init did not load a camlib
usb_fds=0
```

So something asked, pgphoto took the request, and `gp_camera_init` still never loaded a
camlib. Layer 3 is a real fault, not idle state.

## What this rules out

- **The library is present and loaded.** `/proc/10026/maps` contains
  `/app/lib/stage2/libgphoto2.so.6`, `libgphoto2_port.so.12` and `libltdl.so.7` — ltdl is
  the mechanism that dlopens camlibs. So this is not a missing-library problem.
- **The environment is correct on the live process**, read from `/proc/10026/environ`:
  `CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34`, `IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2`,
  and that directory contains `camlibs.manifest`, `pentax.so`, `ptp2.so`.

Narrowed to: libgphoto2 is loaded with a correct CAMLIBS, but the camlib `.so` files are
never dlopened — i.e. the abilities-list load either does not run or fails silently.

## Do NOT use /tmp/gphoto-debug.log as evidence for this

The device has `/tmp/gphoto-debug.log` and `/tmp/gphoto-debug2.log` that look directly on
point. They are not, and using them would misdirect the investigation:

- They were produced by **gphoto2 CLI 2.5.27.1**, not pgphoto's stage-2 libgphoto2 **2.5.34**.
- Their `CAMLIBS = '/app/lib/stage2/libgphoto2'` — no version subdirectory, unlike the live
  process env above.
- There is no `gphoto2` on PATH now (`command -v gphoto2` → nothing), so whatever produced
  them is not what is running.

They do contain one line worth noting as a *hypothesis only*, not a finding:

```
unlocked_gp_abilities_list_load_dir(2): Using ltdl to load camera libraries from '/app/lib/stage2/libgphoto2'...
unlocked_gp_abilities_list_load_dir(2): Found 1 camera drivers.
unlocked_gp_abilities_list_load_dir(2): Failed to load '/app/lib/stage2/libgphoto2/2': file not found.
```

"Found 1 camera drivers" then a failed load of a path ending `/2` is odd, and if the same
malformed entry exists in our `camlibs.manifest` it could explain a silent abilities-list
failure. Unverified — it comes from a different binary with a different CAMLIBS, so it must
be reproduced against 2.5.34 before being treated as a cause.

## Bug found in the diagnostic while doing this

Layer 4 matched `:1F90` only in `/proc/net/tcp`'s **remote** column. pgphoto is the *server*
on 8080, so established rows carry it in the **local** column. Measured against a live stream
request with two connections open:

```
$3 ~ /:1F90$/                          -> 0     (what the tool did)
($2 ~ /:1F90$/ || $3 ~ /:1F90$/)       -> 2     (correct)
```

The consequence was worse than a wrong count: layer 3's verdict is deferred on layer 4, so
under-reporting clients forced it to UNKNOWN when the truth was FAIL. Fixed, and both
reports above were produced with the corrected filter.

## Addendum: preview is already enabled, so lazy init is dead as an explanation

Read-only query of `polaris-httpd` (running as `/app/astro/polaris-httpd --port 8090`, so the
control API is on 8090 — port 80 is Benro's own `lighttpd`, which 404s on these paths):

```
GET http://192.168.0.1:8090/api/link
link status: up | wanted: True | rx: 9853 | opcodes cached: 31

opcode 292 (preview-state): state:1;            age_ms 15188  count 453
opcode 286 (camera-info):   manufacturer:none;model:none;state:-110;storage:0;photoFormat:0;
                                                          age_ms 15188  count 456
```

`preview-state = state:1` means the MJPEG stream on :8080 is **on**. So pgphoto was already told
to run preview, it is serving the endpoint, and `gp_camera_init` still loads no camlib. Combined
with the client-attached FAIL above, the "nothing asked yet" branch is closed from two directions:
an explicit stream request produced no frame, and the standing preview flag is set.

`camera-info` returning `state:-110` with `model:none` is the published symptom, refreshed every
30 s (count 456). Note this is exactly the shape the TA's #299 suite treats as quarantined —
`tests/astro_regression/fixtures/k3iii-link-quarantined.json` asserts `camera_state: -110` and
`model: "none"` under classification `camera_quarantined`. So the live device is currently sitting
in the state that suite's fixture describes, and that fixture is checked in as *not ready*.

`polaris-httpd` never sends opcode 291 (`set-preview`) itself — `grep plink_send(291` returns
nothing; it only polls 292. So preview was enabled by the Benro app, not by our httpd.

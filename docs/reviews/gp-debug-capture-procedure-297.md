# GP_DEBUG capture for #297 step 2 — and why it cannot run as specified

## The blocker, verified

`GP_DEBUG=1` will produce nothing from pgphoto's libgphoto2. Our shipped library has logging
compiled out.

Evidence, on the exact artifact the device is running:

```
local sha256:  cefa7b399b8c25ad8801a74bad6db3124f15187190528266b4b36116f13d2b62
device sha256: cefa7b399b8c25ad8801a74bad6db3124f15187190528266b4b36116f13d2b62
```

Identical, so the local inspection transfers to the device without guessing.

```
$ strings -a libgphoto2.so.6 | awk '$0=="GP_DEBUG"'  | wc -l   # device: 0, local: 0
$ strings -a libgphoto2.so.6 | awk '$0=="CAMLIBS"'   | wc -l   # device: 1, local: 1
```

`CAMLIBS` is the control: it is demonstrably read by this build (the live process env has it and
camlib resolution depends on it), so its presence proves `strings` finds env-var names in this
binary. `GP_DEBUG` is absent while `CAMLIBS` is present — that is a real difference, not a tool
failure. Corroborating: no `gp_log*` symbol is exported (`nm -D --defined-only` → 195 exports,
zero matching `gp_log`), and no string in the file contains `DEBUG`.

So step 2 needs the logging path restored before it can be run. Setting the variable on a
library that never reads it yields silence, which is indistinguishable from "init was never
reached" — the exact ambiguity we are trying to resolve. Do not run it and record the silence as
evidence.

## What is available instead

The loader (`libpolaris_stage2.so`, `LD_PRELOAD`ed) is ours, so it can be instrumented without
touching libgphoto2. Its env knobs, read from `stage2_loader.c`:

```
STAGE2_CAPTURE_TRACE            STAGE2_STORAGE_SHIM        STAGE2_STORAGE_FORCE
STAGE2_CAPTURE_GUARD            STAGE2_TETHER_CAPTURE      STAGE2_REASSERT_CRASH_HANDLER
STAGE2_PENTAX_PREVIEW_BACKOFF   STAGE2_SHUTTER_FALLBACK    STAGE2_CAPTURE_EMPTY_PATH_CHECK
```

`gp_camera_init` is already a wrapped slot (`stage2_shim_gp_camera_init`, line 868), so the
single most valuable measurement is whether that shim is entered at all. One unconditional
`fprintf(stderr, "[stage2] init: enter\n")` at the top of it answers the question directly:

- **line appears** → `gp_camera_init` is being called; the failure is inside libgphoto2's
  abilities-list load, and we need logging rebuilt to see why.
- **line absent** while a client is connected → pgphoto never calls `gp_camera_init` on the
  stream path, and #297 is a pgphoto-flow question, not a camlib question.

That is a decisive fork obtained from one line of our own code.

## Two traps to avoid when capturing

**1. `/app/Clog.txt` is continuously truncated.** It holds 106 lines for a process with
`etime` 171:24 emitting IPC chatter every ~3 s. Absence of a line there proves nothing — I nearly
concluded "the loader printed nothing, therefore init did not run" and that inference is invalid.
Redirect to a dedicated file, or read it immediately after the trigger.

**2. `/tmp/gphoto-debug.log` and `gphoto-debug2.log` are not ours.** gphoto2 CLI **2.5.27.1**,
`CAMLIBS` without the version subdir, no `gphoto2` on PATH now. Their
`Failed to load '/app/lib/stage2/libgphoto2/2': file not found` is fully explained and is a red
herring for our binary:

```
foreach_func: Found '/app/lib/stage2/libgphoto2/2'.
unlocked_gp_abilities_list_load_dir: Found 1 camera drivers.
```

With CAMLIBS pointing at the parent, `lt_dlforeachfile` enumerated the version **directory**
`2.5.34`, ltdl treated `.5.34` as an extension, and `lt_dlopenext("…/2")` failed. One "driver"
that is really a directory. Our live CAMLIBS is correct, so this never applies.

## Procedure once logging exists

Read-only throughout; nothing restarted, no settings written.

```sh
# 1. confirm the trigger still behaves as measured (pgphoto answers, emits boundary, no frame)
curl -sS --max-time 20 -o /tmp/stream.bin -w 'http=%{http_code} bytes=%{size_download}\n' \
     'http://192.168.0.1:8080/?action=stream'

# 2. while it is held open, confirm the client really attached and no camlib mapped
P=$(ps | grep pgphoto.stage2ondisk | grep -v grep | awk '{print $1}' | head -1)
awk '$4=="01" && ($2 ~ /:1F90$/ || $3 ~ /:1F90$/)' /proc/net/tcp | wc -l   # expect >= 1
grep -oE '/[^ ]*(pentax|ptp2)\.so' /proc/$P/maps                            # expect empty
ls -l /proc/$P/fd | grep -c 'bus/usb'                                       # expect 0
```

The connection filter must test **both** columns: pgphoto is the server on 8080, so `1F90` sits
in the local field. Matching only the remote field returns 0 against a live stream request that
has two connections open — this was a bug in `camera-layer-report.sh`, fixed in `81f8a6c`, and it
silently forced layer 3 to UNKNOWN because that verdict is deferred on layer 4.

## Where #297 stands

Layer 3 is confirmed a real fault, not lazy init: a client connected, pgphoto answered HTTP 200
with the MJPEG boundary and no frame, and `gp_camera_init` still loaded no camlib. Ruled out with
evidence — libgphoto2/port/ltdl all mapped; CAMLIBS/IOLIBS correct on the live process; both
camlibs export `camera_id` and `camera_abilities`; pgphoto is uid 0 so ownership is not a blocker;
no `CAMLIBDIR_PREFIX_ENV`, so `foreach_func`'s skip filter is inactive; capture guard off
(`STAGE2_CAPTURE_GUARD` unset).

The remaining unknown is why the abilities-list load never dlopens a camlib despite all of that.
Getting it needs either logging rebuilt into libgphoto2 or the one-line shim trace above.

# Bulb root cause — reverse-engineering the stock binaries (2026-10-05)

Device: `6.0.0.54.55` (o-v15r). Binaries analysed:

| file | size | notes |
| --- | --- | --- |
| `/app/bin/polestar_app` | 24 941 228 B | ARM EABI5, **not stripped, with debug_info** |
| `/app/lib/stage2/pgphoto.stage2ondisk` | 7 801 576 B | ARM EABI5, **not stripped, with debug_info** |

Host tooling note: plain `objdump`/`gdb` on this host have **no ARM target** and
silently disassemble ARM as x86. Everything below was produced with
`arm-linux-gnueabi-objdump` / `-nm`. A literal-pool scanner
(`/tmp/armstrings.py`) is required because ARM reaches strings with
`ldr rN,[pc,#N]` followed by `add rN,pc,rN`; a naive absolute-address scan
returns false negatives (it did, twice, before this method was built).

---

## 1. `bulb:N` is parsed, then used only as a *timeout*, never as an exposure

The 264 handler is `SP_MsgCameraFromAppProc` @ `0x49598` in `polestar_app`.
Its jump table starts at `0x495fc` with `index = code - 257`; code 264 →
handler `0x49718`:

```
49718:  ...  sscanf(payload, "state:%d;bulb:%d;c:%d;", &state, &bulb, &c)
49758:  mov  r2, #1000
4975c:  mul  r3, r2, r3          ; bulb_seconds * 1000 -> bulb_ms
49768:  cmp  r3, #0
4976c:  bne  497a0
        ; bulb == 0  -> SP_SetPhotoRecodeState(0, 0, 1, ...)   (plain capture)
497a0:  ldr  r1, [fp,#-28]       ; r1 = bulb_ms
497b4:  bl   SP_MakeNormalPhoto  ; (0, bulb_ms, c)
```

So the seconds value **is** read and scaled. `SP_MakeNormalPhoto` @ `0x74968`
forwards it unchanged into `SP_SetPhotoRecodeState` @ `0x57ac8`, where the
fourth argument (`bulb_ms`) is used in exactly two places:

```
57c74:  ldr r3,[fp,#-1068]       ; bulb_ms
57c78:  cmp r3,#0
57c7c:  bne 57cb4
        ; bulb_ms == 0 -> deadline = f(ctx+0x11c) * K + 30000 + 48
57cb4:  ldr r3,[fp,#-1068]       ; bulb_ms
57cb8:  add r3,r3,#30000
57cbc:  add r3,r3,#48
57cc8:  str r3,[r2,#384]         ; ctx+0x180 = bulb_ms + 30048
```

`ctx+0x180` is a **capture deadline / watchdog**, not a camera setting. The
`+30000` grace confirms it. `bulb_ms` is never handed to libgphoto2 and never
turns into a shutter-speed write.

**Conclusion: `bulb:N` cannot work in the stock path by design.** The duration
is consumed as "how long am I willing to wait for a file", which is why every
Bulb request exposes whatever the camera's shutter already happens to be (2.0 s
in our tests) and still reports success.

## 2. The stock Bulb capture function is dead code

In `pgphoto`:

* `captureBulbImage` @ `0x20604` (`gphotoMain.c:1430`) — **zero callers**.
* Its only callee `capture_image_with_Bulb` @ `0x101aac` (`gpManager.c:3185`)
  is called from `0x206e0`, which lies *inside* `captureBulbImage`
  (`0x20604`–`0x208af`; the next symbol `captureImage` starts at `0x208b0`).
* Globals `glob_bulblength` (`0x375e14`) and `bulb.11463` (`0x311c28`) are
  unreferenced.

This is why `captureBulbImage` appears in **no log on the device, ever**
(0 hits across `Clog_000240`–`000249`). `captureImage` and `captureBulbImage`
share the signature `int (SPC_Settings *)`, so the intended dispatch was a
drop-in swap that was never wired.

## 3. The real shutter-set command is **261 `s:<index>;`**, not 277

`pgphoto`'s message dispatcher is `camera_info_update_with_message` @ `0x16dac`;
jump table at `0x16e38` with `index = code - 258`. Decoded:

| code | handler | meaning | app payload (observed) |
| --- | --- | --- | --- |
| 258 | `setCameraConfig(0,…)` | ISO | `iso:6;` → `ret:0` |
| 259 | `setCameraConfig(1,…)` | aperture-ish | — (unused by app) |
| 260 | `setCameraConfig(2,…)` | EV | `ev:15;` → `ret:0` |
| **261** | `setCameraConfig(3,…)` | **shutter** | `s:33;` → `ret:0` |
| 262 | focus mode | | `mod:1;f:6;` → `ret:0` |
| 264 | capture | capture | `state:1;bulb:N;c:-1;` |
| 265/266/267/268/275 | `getCameraConfig` | ISO/WB/EV/**shutter**/f lists | `RD:0;V:33;R:1/8000,…` |
| **277** | `camera_set_aperture` | **aperture, not shutter** | — |

Two independent confirmations:

* The Benro Connect app's own traffic in `Mlog_*.log`:
  `code[261],val[s:33;ret:0;]` (and `s:0`, `s:1`, `s:2`, `s:19`, `s:23`,
  `s:24`, `s:27`, `s:28`, `s:30`, `s:31`, `s:34` …). It never sends 277.
* Reproduced live from the canary host: `TX 1&261&2&s:44;#` →
  `RX 261@s:44;ret:0;`.

By contrast our canary has always sent **277 with `shutter:`** (and later
`s:`). 277 is `camera_set_aperture` in `pgphoto` and `SP_SunMsgFromAppProc` in
`polestar_app` — the wrong command entirely. **"Command 277 never replies" was
our client bug, not a firmware defect.**

Note: `s:44;` and `s:54;` return `ret:0` but the 268 readback stays at `V:33`
(`1/4`). `ret:0` therefore means "accepted", not "applied" — the same
false-success class as Bulb. Whether the camera refuses long exposures in the
current mode is still open and needs the EXIF test in §5.

## 4. `bulb` is a real config name in the library

`getConfigName` @ `0x1df38` indexes a runtime-initialised 64-byte-stride table
(`base = 0x2f6ff8`, `+0xe5e70 + 0xbc0 + 8`), and `updateCaptureInfo` @
`0x1df94` case 4 lower-cases the incoming value and does
`strstr(..., "auto")` / `strstr(..., "bulb")` before `myAtol`. So the library
layer does know a `bulb` shutter value; it is the Polaris glue that never
issues it.

## 5. Not yet proven / next test

The acceptance test is still **requested duration → camera readback → captured
file → EXIF ExposureTime**. A `ret:0` is not evidence.

Blocked at the time of writing: after the 261 probes the camera began returning
`-110` (`ARG_CAPTURE_IMAGE -110`, `captureImage ret -110`) and a plain Manual
canary shot went `state:1 → -1005` in 1 s. That is the familiar PTP wedge; only
a camera power cycle recovers it.

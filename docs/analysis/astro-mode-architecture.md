# Astro Mode — Architectural lessons

Companion to [`astro-mode-overview.md`](./astro-mode-overview.md). Where that one is "what he built", this one is "what we can learn from how he built it" and "where exactly the code lives."

## Where the code lives

Everything astro-related is parked in a single sibling directory, **not** bolted onto the existing patcher:

```
container/astro/
├── ondisk/           ← 22 scripts/configs installed to /app/astro on the SD card
├── webui/            ← SPA (app.js + index.html + app.css ≈ 197KB)
├── gslshim/          ← BSD-3 GSL replacement (avoids GPLv3 gsl-an contamination)
├── polaris-httpd.c     (245KB)  — web server + Alpaca + INDI in one binary
├── polaris-prog.c/h    (50/19KB) — 8 programs unified (270/271/272/275/277/280/283/305)
├── polaris-astro.c/h            — astro session (mode 8, AHRS heartbeat, alignment, tracking)
├── polaris-mount.c     (42KB)  — wire protocol + astronomical calcs
├── polaris-jog.c/h              — lease-based jog, dead-man on server
├── polaris-link.c/h             — single-connection non-blocking link, cache, backoff
├── polaris-extract.c   (25KB)   — JPEG→star-list, EXIF focal, HFR, PGM, thumbnails
├── polaris-solve.c     (11KB)   — solver front end
├── polaris-skysim.c    (9KB)    — sky-field renderer for testing
├── polaris-sim.py      (33KB)   — test harness simulating the head
├── sim-verify.py       (14KB)   — diff script
└── test_prog.c         (27KB)   — unit tests for the program engine
```

The build entry point is `./build-astro.sh` at repo root — a single shell script, not Make/CMake. Output goes to `out/astro-bundle/COPY-TO-SD-CARD-ROOT/{astrometry/,polaris-astro/,site.conf}`. The user copies that one folder to the SD root and reboots.

The C side links together as **one binary**: `polaris-httpd.c polaris-link.c polaris-jog.c polaris-prog.c polaris-astro.c` → `polaris-httpd`. So you get web UI, Alpaca, INDI, jog, programs, astro session, and the link layer all in one process sharing one socket.

## The patterns we can adopt

### 1. Process boundary for licensing
Astrometry.net is GPL v2+, so the solver runs as a **separate process** and is never linked into the MIT-licensed patcher. Same trick for GPLv3 `gsl-an`: a BSD-3 shim (`gslshim/`) is linked instead, so the binary stays clean. This is the single most important decision and it shows up everywhere — `docs/PLATE-SOLVING.md` literally has "process boundary" as a layer in its architecture diagram.

**For us:** any time we want to add a feature that depends on a GPL-licensed library, default to running it as a separate process. Don't link it in.

### 2. One long-lived registered TCP session
Instead of a fresh socket per request, `polaris-link.c` opens one non-blocking connection to the head, registers with the app's protocol, and shares it across web UI, solver, Alpaca, and INDI. The link layer owns:
- 128-slot read/write cache
- Write queue (producers never block)
- Reconnect backoff 1s → 30s
- 60s re-register (`REREGISTER_MS`)
- 5s heartbeat

This is what makes wifi-drop recovery sane and what lets the head think it's still talking to the phone app.

**For us:** our current patcher tends to do one-shot `plink` calls. If we ever want to expose a long-running surface (web UI, polling status, sustained motors), the link-layer pattern is the right shape.

### 3. Dead-man on the SERVER, not the browser
`polaris-jog.c` inverts the usual web-by-jog pattern. Browser sends *intent* with a 400ms lease; the server runs its own 50ms repeat timer and **stops the motor the moment the lease lapses**. Phone lock, tab close, wifi hiccup, screen sleep — head STOPS. Lease renewal is the browser's job; ownership of motion is the server's. This is the right call for a device that can wreck a £3k lens.

```
JOG_PAN / JOG_TILT / JOG_ROT   — request a motion with a 400ms lease
JOG_LEASE_MS = 400             — lease duration
JOG_REPEAT_MS = 50             — server-side repeat cadence
JOG_SPEED 100..2500            — speed envelope
slow = latched 532/533/534     — one-shot start
fast = continuous 513/514/521  — repeat-while-leased
```

**For us:** adopt this any time we add motion. Web-by-jog without a server-side dead-man is a footgun.

### 4. Default-deny opcode allowlist
122 opcodes were catalogued from the decompiled app (`docs/APP-PROTOCOL.md`). Anything that moves motors or fires the shutter needs explicit confirmation. Contrast with our current patcher which tends to forward raw frames.

**For us:** if we ever expose more than the few opcodes we currently do, we should build an allowlist. The list and semantics are already documented upstream.

### 5. Boot hook chaining, not script replacement
The Benro firmware runs `/app/network_telnetd.sh` (or similar) at boot to enable SSH. blaineam doesn't replace it — he **renames the original** and runs his pre-astro hook first, then the original. Same pattern for any later hooks. Firmware updates don't clobber his work; his scripts slot in front of the existing chain.

```
[ original /app/network_telnetd.sh ]  →  /app/network_telnetd.sh.orig
[ new      /app/network_telnetd.sh ]  →  runs astro pre-hook, then .orig
```

**For us:** if/when we add a boot hook, use the same rename-and-prepend pattern so firmware updates remain safe.

### 6. Chained server binaries
`polaris-httpd.c` (245KB!) links together with `polaris-link.c polaris-jog.c polaris-prog.c polaris-astro.c` as **one binary**. Trade-off: simpler IPC (in-process function calls), harder to isolate bugs, but the alternative (multiple processes each opening their own TCP session) is exactly what the head won't tolerate.

**For us:** if we ever build a web UI, consider whether one process makes sense. If our use case is mostly short-lived CLI invocations, our current one-binary-per-feature pattern is fine.

### 7. Cross-compilation determinism via docker
`build-astro.sh` runs everything inside a single docker container, so the host distro doesn't matter:

```sh
arm-linux-gnueabi-gcc -O2 -std=gnu11 -mfloat-abi=soft   -Wall -Wextra -Werror  # appfs
arm-linux-gnueabi-gcc -O2 -std=gnu11 -mfloat-abi=softfp -Wall -Wextra -Werror  # solver
```

Werror turned on, so linting is enforced at build time.

**For us:** we could adopt this immediately. "Works on my machine" is the #1 reproducibility killer for this kind of patcher. `-Werror` is a debate for our own codebase.

### 8. Server-side thumbnails
`--thumb` flag in `polaris-extract.c` generates ~2KB 320px thumbnails on the patcher. The head has no thumbnail endpoint of its own, so this is the only sane way to populate a gallery without round-tripping full JPEGs over wifi.

**For us:** only worth stealing if we build a gallery/preview UI. Skip until we have one.

### 9. Dry-run by default
`AUTOSOLVE_DRY_RUN=1` and `GUIDE_DRY_RUN=1` are the defaults. The head gets correction *suggestions*; only when the user explicitly arms it do corrections flow to the live mount. This is the right safety story for unattended operation.

**For us:** any autonomous or "smart" mode we add should default to dry-run.

### 10. Test harness without hardware
`polaris-sim.py` (33KB) simulates the head's wire protocol well enough that the entire C side can be developed and verified with no device. `sim-verify.py` diffs expected vs. actual frame-by-frame.

**For us:** if we add a meaningful feature, insist on a sim before testing on a real head. The 33KB cost is cheap; the "I bricked my head" cost is not.

## Quirks worth knowing (the gotchas he hit)

- **530 (multi-step star alignment) is deliberately AVOIDED.** Aperion traces show it wedges the motors. So 530 is used only as a one-shot ARM trigger (`step:1`); the actual 3-point alignment is driven from the C side using lower opcodes.
- **`console_loglevel 1`** is set at boot to silence the wifi driver (`dhd_tcpdata_info_get 1056: No more free tdata_psh_info!!`) flooding the 115200-baud serial port under TCP load. Without it, the head hangs.
- **Timezone detection:** `TZ_OFFSET_SEC` is read from the app's 782 message (the app tells the device timezone once on connect, then transient in `Mlog.txt`) and cached so it survives log truncation.
- **Subsystem selector isn't constant** — 520 and 526 use sub=2 despite being 5xx, control=3, register=2. If you write code that assumes `sub = opcode/100`, you're wrong.
- **Azimuth on the wire is signed (-180, 180) westward**; UI uses 0..360. Convert at the wire boundary, not in the math.
- **518 is read-only and unaligned mounts never answer it.** The 5s cache in the old shell-out design exists because of this.
- **PATH-LAPSE reuses opcode 272** — each waypoint is `step:2` with gimbal pose in radians + cumulative arrival. Same opcode, different semantics.
- **HOLY GRAIL configures a day→night ramp** that the head applies during a lapse.

## Wire-format details (from `polaris-mount.c` and `polaris-prog.h`)

- **Frame out:** `1&<cmd>&<sub>&<k>:<v>;...#`
- **Frame in:** `<cmd>@<k>:<v>;...#`
- **Subsystem selectors:** register=2, control=3, app=4 (5xx apps use 2 not 5).
- **Azimuth on wire:** signed (-180, 180) westward. UI uses 0..360.
- **Program identifiers:**
  - 270 = FOCUS
  - 271 = PANO
  - 272 = LAPSE (also PATH-LAPSE)
  - 275 = VIDEO
  - 277 = SUN
  - 280 = HDR
  - 283 = PLC (keyframe timeline: photo events + camera params + motion pose)
  - 305 = HOLY GRAIL (day→night ramp during a lapse)

## Mount/astronomy constants (from `polaris-astro.h` and `polaris-mount.c`)

- **ASTRO_MODE = 8** — the app-side mode selector
- **AHRS heartbeat = 520** — pose/attitude
- **TRACK = 531** — sidereal/lunar/solar tracking
- **YAW = 527** — rotate base independently
- **HALF = 536** — half-frame trigger for path-lapse
- **Sidereal rate = 0**, **lunar = 2** — tracker rate enum
- **Altitude band 12..80°** — outside this, alignment is unreliable
- **Max align altitude 65°** — `1/cos(alt)` amplifies heading error near zenith
- **Max single slew 180°** — keep within a single wrap
- **Deep-sky targets 12..18km** typical; needs M31 framing
- **J2000 → apparent place** — IAU 1982 precession + nutation + aberration
- **Explicit lat/lon alignment** — required for accurate tracking

## What this means for our fork

**Steal directly:**
- Process boundary for any GPL-licensed component we ever add.
- Single-connection link layer with cache + backoff (split out of the astro-specific bits first).
- Server-side dead-man for anything that moves.
- Default-deny opcode allowlist.
- Boot hook chain pattern (rename + prepend, don't replace).
- `console_loglevel 1` at boot (if we ever touch boot hooks).
- Docker build for determinism.
- Dry-run defaults for anything autonomous.
- Sim harness before touching real hardware.

**Rethink before copying:**
- The 245KB single-file `polaris-httpd.c` is a maintenance liability. Split by concern if we adopt the pattern.
- One-binary-everything works because everything runs on-device; if we keep an off-device component, the IPC story gets harder.
- PATH-LAPSE reusing opcode 272 is clever but a maintenance trap for anyone reading the protocol later. Document the overload.
- The 60s re-register / 5s heartbeat cadence is tuned for the *original* app's behaviour; if Benro ever changes it, the whole link layer needs review.
- `-Werror` in the docker build is good practice but a debate for our codebase.

**Don't bother:**
- GSL shim — only worth it if we link GPL math. We don't.
- Thumbnail generation — only needed for a gallery UI. Skip until we have one.
- Full solver tree (astrometry.net 0.98) — GPL, ~hundreds of MB to vendor. Only adopt if we actually need plate-solving.
- Full web UI — its build is tightly coupled to the on-disk layout.

## Open questions for us

- Do we want a "no-astro" build profile that produces just the test sim + GSL shim, or always ship the full bundle?
- Can the dead-man jog pattern be applied to anything in our current patcher that moves motors?
- Is the single-binary-per-feature pattern worth breaking to adopt a single-binary-everything pattern?
- Should we adopt `-Werror` in our own docker build, or is that a step too far for our CI?
- Are we comfortable with the size of `container/astro/` if we merge it (~400KB of source + ~197KB of webui + the solver tree)?

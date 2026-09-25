# Astro Mode — Overview of blaineam's work since the fork

**Source:** `blaineam/benro-polaris-firmware-patcher@astro-plate-solving` (122 commits ahead of `main`, last commit 2026-08-28).
**Our fork point:** `b62c4079` on upstream `main`.
**Our branch:** `astro-mode-forks-review` (this worktree).

## TL;DR

blaineam has built an end-to-end astrophotography mode for the Polaris head. The work lives entirely on a feature branch (`astro-plate-solving`) — **none of it is on `main`**. The build is a single shell script that produces one folder the user copies to the SD card; no SSH, no manual file shuffling, no firmware rewrite. The patcher stays MIT-licensed by running GPL components as separate processes.

## What was added

### Install model
- **Single command:** `./build-astro.sh` produces `out/astro-bundle/COPY-TO-SD-CARD-ROOT/`.
- **Zero-SSH install:** optional `--astro-autostart` flag bakes the binaries into firmware via a boot hook, so the user just copies one folder to the SD root and reboots.
- **Default path** is the manual one: copy the folder, reboot, done.

### Source files (`container/astro/`)
- **`polaris-httpd.c`** (245KB) — entire web server + Alpaca + INDI in one binary.
- **`polaris-prog.c/h`** (50/19KB) — 8 different programs unified (FOCUS 270, PANO 271, LAPSE/PATH-LAPSE 272, HDR 280, PLC 283, SUN 277, HOLY GRAIL 305, plus more).
- **`polaris-astro.c/h`** — astro session lifecycle (mode 8, AHRS heartbeat, alignment, tracking).
- **`polaris-mount.c`** (42KB) — wire protocol + astronomical calcs (J2000→apparent, GMST/LST, az_to_wire signed-westward).
- **`polaris-jog.c/h`** — lease-based jog with dead-man on the server.
- **`polaris-link.c/h`** — single non-blocking TCP connection, 128-slot cache, write queue, 1s→30s backoff, 60s re-register.
- **`polaris-extract.c`** (25KB) — JPEG→star-list, EXIF focal reading, HFR metric, gray PGM export, ~2KB thumbnail generation.
- **`polaris-solve.c`** (11KB) — solver front end.
- **`polaris-skysim.c`** (9KB) — sky-field renderer for testing.
- **`test_prog.c`** (27KB) — unit tests for the program engine.
- **`polaris-sim.py`** (33KB) + **`sim-verify.py`** (14KB) — Python harness simulating the head for tests with no hardware.

### On-device scripts (`container/astro/ondisk/`, ~22 files)
Shipped to `/app/astro/` on the SD card:
- **`polaris-autosolve.sh`** (41KB) — main orchestration. Hooks 530 step:1 ARM, dry-run by default, auto-detects timezone from app's 782 message.
- **`polaris-astro-boot.sh`** (15KB) — boot hook chain, `console_loglevel 1` to silence wifi-driver flood, `site.conf` loaded after microSD mounts.
- **`polaris-autoalign.sh`** (16KB) — auto-alignment routine.
- **`polaris-guide.sh`** (9KB) — PHD2-style guiding.
- `site.conf`, `astrometry.conf`, plate-solving index lists, helper scripts.

### Web UI (`container/astro/webui/`, ~197KB)
- `app.js` (111KB), `index.html` (52KB), `app.css` (34KB) — single-page app for live view, plate-solving, mount control, program editor.

### Solver build (`container/astrometry/`, **not** in our checkout)
- Vendored astrometry.net 0.98 with license audit (`docs/LICENSE-AUDIT.md`).
- Cross-compiled `arm-linux-gnueabi-gcc -mfloat-abi=softfp`.
- Index files generated via `--no-indexes` flag; user supplies their own.

### GSL shim (`container/astro/gslshim/`)
- BSD-3 GSL replacement to avoid GPLv3 contamination from `gsl-an`.

### Documentation (`container/astro/docs/`, 5 files)
- **`PLATE-SOLVING.md`** (30KB) — feasibility analysis, hardware facts, licensing analysis, three-layer architecture.
- **`ASTRO.md`** (58KB) — user-facing canonical reference.
- **`APP-PROTOCOL.md`** (91KB) — 122 opcodes catalogued from decompiled app, the protocol-level truth.
- **`APP-FEATURES.md`** (123KB) — full app screen/feature inventory.
- **`HOW-IT-WORKS.md`** (25KB) — integration overview.
- **`LICENSE-AUDIT.md`** (8KB) — per-component license audit of the astrometry.net 0.98 tree.

## Hardware facts (from the docs)

- Polaris head has compass, IMU, **no absolute encoder on focus** (opcode 311 is relative).
- Astro mode requires the hardware "Astro Kit" (extended tilt range + cable port).
- Phone app holds one connection; we mimic that connection.
- **Wifi powers down 60s after last client disconnects.** A registered connection counts as a client, so the link layer's keepalive is free.
- Registering while the mount is unaligned is what makes the Benro app demand compass calibration — load-bearing for the `plink_open` decision.

## Architectural decisions worth highlighting

1. **Process boundary for licensing** — astrometry.net (GPL v2+) and gsl-an (GPLv3) run as separate processes / via a BSD-3 shim. The patcher binary itself stays MIT-licensed.
2. **One long-lived registered TCP session** — shared by web UI, solver, Alpaca, INDI. Non-blocking, 128-slot cache, write queue, 1s→30s reconnect backoff, 60s re-register, 5s heartbeat.
3. **Dead-man on the server** for jog — browser sends intent with 400ms lease, server owns 50ms repeat + automatic stop on lease lapse.
4. **Default-deny opcode allowlist** — anything that moves motors or fires the shutter is explicit.
5. **Boot hook chaining** — `/app/network_telnetd.sh` slot is shared; the astro pre-hook is moved aside and run first, then the original runs. Firmware updates don't clobber the work.
6. **Chained server binaries** — `polaris-httpd.c` links together with `polaris-link.c polaris-jog.c polaris-prog.c polaris-astro.c` as **one binary** sharing one socket. Different from our pattern of one binary per feature.
7. **Cross-compilation determinism via docker** — `build-astro.sh` runs everything inside a single container, host distro doesn't matter. `-Wall -Wextra -Werror` enforced.
8. **Server-side thumbnails** — `polaris-extract.c --thumb` generates ~2KB 320px thumbs. The head has no thumbnail endpoint, so this is the only sane way to populate a gallery.
9. **Dry-run by default** — `AUTOSOLVE_DRY_RUN=1` and `GUIDE_DRY_RUN=1`. Corrections are *suggestions* until the user explicitly arms them.
10. **Test harness without hardware** — `polaris-sim.py` simulates the head's wire protocol well enough that the entire C side can be developed and verified with no device.

## Quirks (the things that bit him)

- **530 (multi-step star alignment) is deliberately AVOIDED.** Aperion traces show it wedges the motors. So 530 is used only as a one-shot ARM trigger (`step:1`); the actual 3-point alignment is driven from the C side using lower opcodes.
- **`console_loglevel 1`** at boot silences the wifi driver (`dhd_tcpdata_info_get 1056: No more free tdata_psh_info!!`) which floods the 115200-baud serial port under TCP load. Without it, the head hangs.
- **Timezone detection:** `TZ_OFFSET_SEC` is read from the app's 782 message (the app tells the device timezone once on connect, then transient in `Mlog.txt`) and cached so it survives log truncation.
- **Subsystem selector isn't constant** — 520 and 526 use sub=2 despite being 5xx, control=3, register=2. If you write code that assumes sub=opcode/100, you're wrong.
- **Azimuth on the wire is signed (-180, 180) westward**; UI uses 0..360. Convert at the wire boundary, not in the math.
- **518 is read-only and unaligned mounts never answer it.** The 5s cache in the old shell-out design exists because of this.
- **PATH-LAPSE reuses opcode 272** — each waypoint is `step:2` with gimbal pose in radians + cumulative arrival. Same opcode, different semantics.
- **HOLY GRAIL configures a day→night ramp** that the head applies during a lapse.

## What's mergeable to our `main`?

**Trivially mergeable** (additive, MIT-compatible, no behaviour change for non-astro users):
- `container/astro/gslshim/` — BSD-3, drop-in GSL replacement.
- `container/astro/polaris-sim.py` + `sim-verify.py` — pure test infra.
- `container/astro/docs/PLATE-SOLVING.md`, `HOW-IT-WORKS.md`, `LICENSE-AUDIT.md` — informational.
- The `polaris-link` link layer pattern (would need splitting out of the astro-specific bits).

**Needs careful review** before merging:
- The boot hook chain — depends on which slot our patcher uses.
- `polaris-httpd.c` (245KB) — too large to drop in wholesale; cherry-pick the link/jog layers.
- Anything that registers a session while the mount is unaligned — affects how our `plink_open` decides.

**Don't merge:**
- The GPL-licensed solver and GSL — keep as separate processes / via shim.
- The web UI in full — its build is tightly coupled to the on-disk layout.

## Open questions for us

- Do we want a "no-astro" build profile that produces just the test sim + GSL shim, or always ship the full bundle?
- Can the dead-man jog pattern be applied to anything in our current patcher that moves motors?
- Is the single-binary-per-feature pattern worth breaking to adopt a single-binary-everything pattern?
- Should we adopt `-Werror` in our own docker build, or is that a step too far for our CI?

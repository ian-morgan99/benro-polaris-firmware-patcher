# Issue #271 — WP0: Baseline and provenance

Recorded 2026-11-07 against a live Benro Polaris Astro. Every value below was read
from the device or from this repository at the pinned commit; nothing is inferred.
Where something could not be determined it is recorded as **unknown**, not estimated.

## 1. Pinned identities

| Item | Value | How obtained |
|---|---|---|
| Patcher commit | `f8e602b6102b1838682d134369a100bbcb3bc93b` | `git rev-parse HEAD`, branch `feature/astro-native-platesolve`, pushed |
| Astro bundle build | `astro-v99-webui-controls` (build-only, tests passed) | `out/astro-v99-webui-controls/build-source-provenance.txt` |
| Display firmware | `6.0.0.54.97`, date `2026.11.06` | `/app/FwVer` → `FwVer:6.0.0.54.97;date:2026.11.06;` |
| Hardware | `1.1.1.2`; Astro Kit / axis `1.0.2.14` | web UI Settings → Device, read from the mount |
| `polestar_app` | `/app/bin/polestar_app`, sha256 `a5e58ffd76670cf9bdc76560a859d2e037ca4320d37bb3c2d93d482cf459ac02` | running as PID 248, cwd `/app/bin`; hashed via `readlink /proc/248/exe` |
| `polaris-httpd` | sha256 `b7c5fec2769a4cb8da9b736b6a843e3d2cad0b6c4c98e35b8334319b97330938` | on-device hash; running process verified by exe→inode match |
| `polaris-mount` | sha256 `751202fa05a66d75d2046eff21a471e65668eda7eeae323745c6893a630be348` | `/app/astro/polaris-mount` |
| `polaris-solve` | sha256 `8b45fc4777b1b94bca349e8e32d39aafd8f646e618a6144dd7ab6f93d62d0b54` | `/app/astro/polaris-solve` |
| MCU / OMS firmware | **unknown** | `getOmsFwInfo.sh` and `getFwInfo.sh` produce no output over SSH; not read. WP0 does not establish an MCU hash. |
| Camera at baseline | **absent** — `286: manufacturer:none;model:none;state:-5`, no `25fb:0183` on USB | live poll + `/sys/bus/usb/devices/` |

The MCU hash gap matters for WP1/WP4: #271 requires target-firmware opcode
verification, and the MCU side is currently unidentified. That must be closed before
any command-sequence claim.

## 2. Site configuration in force

`/app/sd/polaris-astro/site.conf`, uncommented assignments only:

```
FOCAL=70
FOCAL_MIN=8
FOCAL_MAX=3000
RANGE_TIMEOUT=240
SOLVER_BIN=polaris-solve
INDEPENDENT_CATALOG=/app/sd/polaris-astro/catalogue.polcat
```

Latitude/longitude are not set in `site.conf`; position comes from the web UI
(Settings → Observing site) instead. Any solve replay must record which source supplied
the site, because the two paths can disagree.

## 3. Deployed vs enabled — the distinction #271 asks for

All 25 scripts in `container/astro/ondisk/` are present in source **and** deployed to
both `/app/sd/polaris-astro/` and `/app/astro/`. Deployment is therefore not a
differentiator. What matters is what is *launched*.

### Running at baseline (started by boot)

| Process | PID | Started by |
|---|---|---|
| `polaris-trackwatch.sh` | 465 (ppid 1), child 469 | `polaris-astro-boot.sh:106` |
| `camera-death-watch.sh` | 471 | boot, gated on `CAMERA_WATCH:-1` |
| `wifi-watch.sh` | 486 | boot, gated on `WIFI_WATCH:-1` |
| `polaris-logwatch --out …/camera-roll.log` | 475 | boot |

PIDs 465 and 469 are **parent and child**, i.e. one logical watcher — not two motion
owners. Worth stating because a naive process listing looks like a duplicate.

### Not running; invoked on demand by `polaris-httpd`

`polaris-align.sh`, `solve-now.sh`, `polaris-goto-solve.sh`, `polaris-guide.sh`,
`autofocus.sh`, `polaris-apsta.sh`, `setup-wifi.sh`. These are reachable from the web
API, so they are *enabled* even though nothing runs them at boot.

### Deployed but launched by nothing in normal operation

| Script | Launched by | Reachable? |
|---|---|---|
| `capture-calibration.sh` | nothing | no |
| `aa_rehearsal.sh` | nothing (it launches `polaris-autoalign.sh`) | manual only |
| `inject_test.sh` | nothing (it launches `polaris-autoalign.sh`) | manual only |
| `polaris-autoalign.sh` | only `aa_rehearsal.sh`, `inject_test.sh` | manual only |
| `capture-app-connect.sh`, `polaris-frame-watch.sh`, `polaris-goto-watch.sh`, `polaris-autosolve.sh` | referenced by boot script | see §4 |

Four of these are named in #271's trace table as if they are live paths. Two
(`capture-calibration.sh`, `polaris-autoalign.sh`) are not reachable without someone
running a rehearsal/inject script by hand. WP1 should treat them as dormant.

## 4. Safety flags actually in force

Values in force on this rig, combining deployed script defaults with what
`site.conf` actually sets. `site.conf` **does** override several flags, so both
sources are listed:

| Flag | Value in force | Source |
|---|---|---|
| `AUTOSOLVE` | **1 (enabled)** | `site.conf:119` — overrides the `:-0` default. See F4: it never runs. |
| `AUTO_SOLVE_FRAMES` | 0 | `site.conf:87` |
| `GOTO_SOLVE_WATCH` | 0 | `site.conf:70` |
| `AUTOSOLVE_DRY_RUN` | **1** (dry-run) | `polaris-astro-boot.sh:321`, not overridden |
| `GUIDE_DRY_RUN` | **1** (dry-run) | `polaris-astro-boot.sh:334`, not overridden |
| `GUIDE` | **0** (guiding off) | `polaris-astro-boot.sh:334`, not overridden |
| `GOTO_SOLVE_APPLY` | 0 | deployed default |
| `GOTO_MODEL_APPLY` | 0 | deployed default |
| `FRAME_CORRECT` | 0 | deployed default |
| `INDEPENDENT_BLIND_FALLBACK` | 0 | deployed default |
| `CAMERA_WATCH` / `WIFI_WATCH` | 1 / 1 | boot gates; both watchers confirmed running |

So on this rig **no closed-loop correction writes to the mount today**. Every
correction path #271 is concerned with is either gated off or dry-run. That is the
correct safety posture and should be preserved, not "fixed" as a convenience — note
that `AUTOSOLVE=1` shows someone intended calibration auto-solve to run, and F4
explains why it does not.

## 5. Findings from WP0

### F1 — `polaris-autoalign.sh` defaults to live motion (latent, not active)

`polaris-autoalign.sh:94` is `DRY_RUN=${DRY_RUN:-0}`. Every other correction-capable
script defaults the opposite way: `polaris-autosolve.sh:37` and `polaris-guide.sh:32`
are both `DRY_RUN=${DRY_RUN:-1}`, and boot passes `AUTOSOLVE_DRY_RUN=1` /
`GUIDE_DRY_RUN=1`.

Line 93 sets `DRY_RUN=1` only when a frame argument is supplied, so the dry-run default
applies to one invocation shape and the live default applies otherwise.

**Scope of the risk:** `polaris-autoalign.sh` is not launched by `polaris-httpd` or by
boot — only by `aa_rehearsal.sh` and `inject_test.sh`, which are themselves never
launched automatically. So this is **not reachable in normal operation today** and is
not an active hazard. It is a latent inconsistency that becomes dangerous the moment
anything wires autoalign up, which is exactly what WP4/WP8 will be doing. Recommend
flipping line 94 to `:-1` before any of that work lands, so "unset" means safe in every
script by convention rather than by luck.

### F2 — MCU firmware identity is not obtainable by the current method

Both `/app/getOmsFwInfo.sh` and `/app/getFwInfo.sh` return nothing over SSH. #271
requires firmware-specific qualification (WP9 depends on it via #240). A working
method to read the MCU version must be found before WP4 or WP9 can make any claim
about command sequences being correct for *this* firmware.

### F3 — Camera-dependent baseline is not established

The body was off throughout, so no solve→pose→residual baseline could be captured.
WP1's "verify real target firmware opcode sequence against BenroConnect" and WP3's
replay both need a camera; WP0 cannot supply them.

### F4 — `AUTOSOLVE=1` is set, but autosolve dies at boot for want of a site position

This is the most consequential WP0 finding, because it means the calibration loop #271
is about is **enabled and silently not running**.

`site.conf:119` sets `AUTOSOLVE=1`, so boot takes the launch branch
(`polaris-astro-boot.sh:306`). The script then exits immediately:

```
/app/astro/polaris-autosolve.sh: line 206: LAT: set LAT
```

Line 206 is `: "${LAT:?set LAT}"; : "${LON:?set LON}"` — a hard requirement. Boot passes
`LAT="$LAT" LON="$LON"` from the boot environment, and `site.conf` has both commented
out (`#LAT=00.00000`, `#LON=000.00000`). So the guard fires and the process is gone
before it ever reaches a solve.

The failure is quiet: output goes to `/tmp/autosolve.out`, nothing surfaces in the web
UI, and no process remains to notice. A user who set `AUTOSOLVE=1` believing calibration
auto-solve was active would have no indication that it never started.

**Why this is subtle rather than a simple config error:** the web UI's Settings →
Observing site is the documented way to set position, and `site.conf` explicitly says
"leave these commented and set it in the web app instead". So the recommended setup
path produces exactly the configuration that kills autosolve. The two position sources
are not the same store, and nothing reconciles them. WP1 should establish where the web
UI persists site (not determined here) and whether boot can read it; until then
`AUTOSOLVE=1` is effectively inert unless `LAT`/`LON` are also written into `site.conf`.

Note this does **not** mean corrections were happening: `AUTOSOLVE_DRY_RUN` defaults to
1 anyway, so even a successfully started autosolve would only log what it *would* send.

### F4b — The other two watchers are genuinely off

`AUTO_SOLVE_FRAMES=0` (`site.conf:87`) and `GOTO_SOLVE_WATCH=0` (`site.conf:70`)
disable `polaris-frame-watch.sh` and `polaris-goto-watch.sh`. These are deliberate
opt-ins, not failures — unlike F4, which is a silent crash.

## 6. What WP0 does *not* establish

- No MCU hash, so no firmware-specific opcode claim.
- No camera attached, so no solve, pose or residual baseline; nothing here validates
  pointing accuracy.
- No motor command was sent, observed or acknowledged.
- Nothing in this document constitutes hardware qualification. Host/source inspection
  and a process listing are not evidence of tracking performance.

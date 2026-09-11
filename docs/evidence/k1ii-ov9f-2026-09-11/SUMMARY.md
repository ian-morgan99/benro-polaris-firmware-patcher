# K-1 II on-Polaris — o-v9f qualification, 2026-09-11 (evening)

Firmware: `o-v9f-stability-candidate` (libgphoto2 `a96aa9fc4`, patcher `1b021e9`).
Camera: Pentax K-1 II (`25fb:0183`, PTP mode). Installed 18:45 via the
sanctioned SD extracted-tree flow after discovering the earlier zip-only staging
was ignored by the watcher (issue #58).

## Context: the o-v9d window was misattributed

Between 15:17 and 18:44 the device ran **o-v9d** (`90de508a5`), not o-v9f,
because `/app/sd/FwPkt.zip` alone is silently ignored by `SP_EVENT_SD_SCAN`.
All morning/afternoon K-1 II failures (live-view flip-out, focus `0x02fa`,
shutter dead) were on o-v9d. See issue #58 and
`docs/evidence/k1ii-ov9d-2026-09-11/SUMMARY.md`.

## o-v9f results (clean boot, K-1 II attached at power-on)

| Gate | Result | Evidence (Clog 19:42–19:43) |
|---|---|---|
| Provenance | PASS | `/app/openpolaris-libgphoto2-provenance.txt` git_commit `a96aa9fc4` |
| Camera detect/state | PASS | `code[286] model:pentax k-1 mark ii;state:1;storage:2;photoFormat:2` |
| 8080 + 9090 listeners | PASS | both LISTEN ~45 s after boot (8080 binds late, not missing) |
| pgphoto stability | PASS | single PID, no restart loop once camera present at boot |
| manualfocusdrive | **PASS** | `command 29 info manualfocusdrive ret 0`; `getFocusInfo ret 0` — o-v9d's `0x02fa` failure is fixed by v9f |
| capturetarget | FAIL `-1` | `command 30 info capturetarget=1 ret -1`; `get_single_config failed: -2` |
| shutterspeed | FAIL `-1` | `command 29 info shutterspeed ret -1`; `get_single_config failed: -2` |
| ISO | FAIL (5 s poll) | repeating `get_single_config failed: -2` every ~5 s in Clog tail |

## Root cause (issue #59)

`-2` = `GP_ERROR_NOT_SUPPORTED`: the K-1 II's PTP implementation does not expose
capturetarget/shutterspeed/ISO device properties. libgphoto2 registers the
widgets unconditionally; pgphoto maps the error to `ret -1`, so the app shows
dead controls and polls every 5 s. Focus drive (the v9f target fix) works.

## Direct gphoto2 cross-check (pgphoto stopped)

`/app/bin/gphoto2 --port usb:001,004 --abilities` → "Pentax K-1 Mark II (PTP
mode)", USB yes, capture Image+Preview, config support yes. So the camera is
fully reachable at the PTP layer; the failures are in the per-item property
surface, not transport.

## Open items for the next agent

1. Issue #59 — model-aware capability probe / hide-unsupported-controls.
2. Re-test live view on o-v9f (the flip-out was observed on o-v9d only).
3. K-3 III regression pass on o-v9f (focus bounded-autofocus guards, capture
   candidate diagnostics) — the v9f target camera.
4. Camera-swap test (issue #57) now that v9f ships the debounced USB
   camera-identity restart: swap K-1 II → K-3 III and confirm clean re-init.

## Files

- `polaris-logs/Clog-current.txt`, `polaris-logs/Mlog-current.txt` — post-boot
  state (Clog rotates fast; the detailed 19:42–19:43 control lines were captured
  in-session and are quoted above).

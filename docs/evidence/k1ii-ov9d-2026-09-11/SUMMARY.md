# K-1 II on-Polaris test report — o-v9d, 2026-09-11 (morning)

**For the noon handover agent.** Firmware: `o-v9d-model-aware-focus`
(libgphoto2 `90de508a5`, patcher `af5d7d5`). Camera: Pentax K-1 II
(`25fb:0183`, PTP mode). Polaris reachable at 192.168.0.1 (root, key auth).

## TL;DR

| Area | Result | Notes |
|---|---|---|
| Boot / runtime integrity | PASS | o-v9d provenance verified on device (`/app/openpolaris-libgphoto2-provenance.txt` = `90de508a5`). pgphoto running, 64/64 slots resolved. |
| Model gate (keep-lv) | **PASS** | `[stage2] keep-lv: pentaxpclvkeep ON for this session` — the case-insensitive gate (`0953dde`) now engages on K-1 II. First time this has been observed. |
| Config tree enumeration | PASS | Full tree read: focus drives (near/far/old-near/old-far/manual), PTP opcode, all Pentax descriptors, Direct Shutter/ISO/Aperture, Focus Peaking, Card Writing Mode, Keep Live View. |
| ISO | **PARTIAL** | `Pentax ISO Descriptor` + `/main/status/pentaxdirectiso` (Direct ISO Speed) present and readable; status line shows `ISO=100`. But there is **no generic `imagequality`/`iso` control** — OpenPolaris clients speaking the generic name see nothing. (libgphoto2 #55 open.) |
| Live view | **FLAKY** | Worked for a while, then "flipped out" (operator). Consistent with #55 preview-retry behaviour; keep-lv now ON so PC-LV persists across requests — verify the backoff gate is actually bounding it. |
| Focus (262) | **FAIL** | `code[262] val[mod:1;f:N;ret:-1]` for f=2,4,5,6 — every focus parameter rejected by the camera. Same false-positive class as K-3 III #47 (pgphoto acks 311 with ret:0 but no physical movement / no `0x9017` dispatch log). |
| Shutter (264) | **FAIL** | No fire observed. K-3 III had the same class of failure: capture terminates `-110` (transfer candidate still pending) → `state:-1005` (#37). |
| Camera swap (K-3 III → K-1 II) | **FAIL — NEW ISSUE #57** | Stale pgphoto session: "Pentax session already open from a previous connection; observing camera state." New body enumerates but cannot claim USB; 8080 half-dead (`restart_gphoto FAIL`); only a full reboot or manual mode-toggling recovers it. |
| Bus stability | **FLAKY** | K-1 II "keeps dropping off the bus" (operator). Direct `gphoto2 --list-config` failed with `-53 Could not claim the USB device` while pgphoto held it — expected, but the drops suggest a deeper USB/PTP instability on this body. |

## Key log evidence (pulled 09:12 UTC, in `polaris-logs/`)

Clog (`Clog.txt`, 750 lines):
```text
[stage2] keep-lv: pentaxpclvkeep ON for this session (PC-LV stays running across preview requests)
Pentax K-1 Mark II (PTP mode)  usb:001,004
Pentax session already open from a previous connection; observing camera state.
Current: state=3; ... ISO=100; ... aperture=32/10; Tv-changeable=yes
code[262] val[mod:1;f:2;ret:-1]   (repeated, f=2/4/5/6)
```

Mlog (`Mlog.txt`):
```text
[restart_gphoto] FAIL: pgphoto stayed alive but port 8080 did not become ready
[checkGphotoTask] pgphoto is exit, reboot it
[restart_gphoto] stopping pgphoto (PID 714) / starting pgphoto via /app/bin/pgphoto
```

## What the noon agent should do (priority order)

1. **Recover cleanly first.** Full Polaris power-cycle (not just reboot) so the
   stale session from the K-3 III→K-1 II swap is gone. Verify: `lsusb` shows
   `25fb:0183`, pgphoto up, 8080+9090 listening, Clog shows a fresh
   `gp_camera_init` (not "session already open").
2. **Re-pull Clog/Mlog** after the power cycle and append to this directory —
   the 09:12 pull predates the operator's compatibility-mode toggle.
3. **K-1 II single-body matrix** (no swaps, no reboots between steps):
   - config read (ISO/shutter/aperture values + ranges)
   - live view start → 60 s stream (count JPEG frames, watch for flip-out) → stop
   - focus: try `manualfocusdrivenear`/`far` AND the K-1 II-specific
     `old-focus near/far` controls (the config tree exposes both; the generic
     ones may be routed to the wrong opcode — see #47 and the o-v9c→o-v9d
     "duplicate near/far registrations route K-1 II to K-3 III opcode" note)
   - shutter: single shot, then check for the `-110`/`-1005` stale-candidate
     failure (#37)
   - capture + download one image
4. **If focus still fails:** run direct `gphoto2` with pgphoto stopped
   (`killall pgphoto` first, or use the reversible on-disk path) to isolate
   libgphoto2 vs pgphoto adapter — same method as the K-3 III qualification in
   `docs/evidence/fwpkt-install/v9d-k3iii-qualification-2026-09-11/`.
5. **Camera-swap test (issue #57):** with K-1 II working, swap to K-3 III and
   record exactly which step breaks (USB claim? session? 8080?). This defines
   the acceptance evidence for #57.
6. **Record results** in this directory + update the o-v9d registry row status
   (currently "live view PASS; focus and capture FAIL" — K-3 III only).

## Open issues this report feeds

- **#57 (NEW)** — camera swap leaves stale pgphoto session; new body cannot claim USB.
- **#47** — 311→libgphoto2 focus adapter mapping (K-1 II `ret:-1` on all f: values).
- **#37** — capture `-1005`/`-110` stale transfer candidate (shutter FAIL class).
- **#55** — unbounded preview retry / radio starvation (live-view flip-out; keep-lv now ON, verify backoff bounds it).
- **libgphoto2 #55** — generic `imagequality`/ISO semantics (why "ISO is not available" to clients).
- **#34** — watchdog recovery after session disruption (8080 half-dead state).

## Environment notes for the agent

- Polaris: 192.168.0.1, `ssh root@` (key). AP BSSID `48:E7:DA:D4:B5:73`.
- gphoto2 CLI: `/app/bin/gphoto2` with
  `CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34 IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2 LD_LIBRARY_PATH=/app/lib/stage2`.
  It will fail with `-53` while pgphoto holds the USB device — stop pgphoto first.
- 9090 protocol codes: 262=focus (mod/f params), 264=shutter, 291/292=live view start/state.
- K-1 II = `25fb:0183`; K-3 III = `25fb:0189`.
- If the Polaris goes offline: BT wake pulse `bluetoothctl connect 48:E7:DA:D4:B5:72`,
  then wait for the `polaris_*` AP. If it does not come up, full power cycle.

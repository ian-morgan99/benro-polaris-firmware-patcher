# Camera never reaches a sleep state when attached to the Polaris (drains in ~1 h vs all night on a PC)

**Filed:** 2026-10-24
**Owner:** patcher/runtime (on-disk stage-2 + host USB power policy), with a possible libgphoto2 half
**Status:** PROPOSAL — measurement first, no behaviour change proposed as a default
**Subject:** the **camera's** battery
**Filed on GitHub under:** #147 (preview/LV workload ownership), cross-linked to #146. Supersedes the idle case never covered by closed #66/#119.

---

## 1. Observation

| Host | Camera attached, no user activity | Result |
|---|---|---|
| PC (plain `gphoto2`, nothing polling) | overnight | camera battery lasts all night |
| Polaris (patched firmware, `.68`/`.69`) | ~1 hour | camera battery flat |

Working hypothesis: **on a PC the camera is allowed to fall into its own sleep/idle state; on the Polaris it is not.** The camera is being held awake by something on our side, not by its own inactivity timer.

Prior camera-battery observations exist and are **all camera-side**, not gimbal-side:

- **#66** (closed, superseded by #146/#147) — "K-1 II battery drain / polling-restart churn evidence": pgphoto restarted ~15x in 2 h on o-v9h, each restart re-opening the PTP session and "waking the camera's sensor/USB"; when the battery flatlined the K-1 II stopped enumerating entirely (no `25fb:0183` in `lsusb`).
- **#119** (closed, superseded by #146) — its body says "the Polaris battery drains very fast while the camera is connected and previewing" and its Expected section says "No battery drain while previewing with a stable camera". **Operator clarification: #119 was always about the camera battery, not the gimbal.** The archived wording has been misread as gimbal-side; that misreading (including in my own earlier analysis) is corrected here.

Both of those correlate drain with *churn during preview*. This report is the **idle** case: no preview, no capture, no app interaction at all. Churn cannot explain it, so whatever holds the camera awake is a steady-state property of an idle Polaris session.

---

## 2. Why the PC and the Polaris differ — candidate mechanisms

Three independent layers can each prevent the camera from sleeping. They must be measured separately; fixing one does not imply the others are clear.

### L1 — Host USB runtime PM (most likely single cause)
A desktop distro usually ships with USB autosuspend enabled (`usbcore.autosuspend=2` and per-device `power/control=auto`). An embedded vendor kernel commonly ships with it **disabled** (`autosuspend=-1`, or every device pinned to `power/control=on`). If the Polaris host never suspends the camera's USB interface, the camera sees a live, claimed link indefinitely and cannot enter its sleep state — regardless of what our userspace does.

Nothing in this repo currently reads or sets any of:
- `/sys/module/usbcore/parameters/autosuspend`
- `/sys/bus/usb/devices/<id>/power/control`
- `/sys/bus/usb/devices/<id>/power/runtime_status`
- `/sys/bus/usb/devices/<id>/power/autosuspend`

There is **zero** power-management code anywhere in `container/ondisk/*` or `container/stage2_loader.c`. The only power-adjacent thing we touch is `printk` quieting (`pgphoto.wrapper.in:155-158`). So this is currently an unexamined surface.

### L2 — We deliberately keep PC Live View running forever
`STAGE2_PENTAX_KEEP_LV` defaults **ON** (`stage2_loader.c:924-930`), which pushes `pentaxpclvkeep=1` on every successful Pentax init (SHIM #4, `stage2_loader.c:435-520`). That sets `params->pentax.keep_live_view`, whose whole purpose is to make `camera_capture_preview()` **skip** its per-frame `d035` teardown — i.e. PC live view (`pentaxpclvmode`, PTP prop `0xd035`) stays **on** across requests instead of being torn down after each frame.

On a PC with stock `gphoto2`, `keep_live_view` is off: every preview ends with the `d035` restore, and the camera returns to normal idle. On the Polaris we explicitly opt out of that restore. A Pentax body with PC-LV asserted does not go to sleep. This is a real, first-class candidate — and it is *our* choice, made for #36/#55 reasons.

Important nuance: keep-LV is armed at **init**, not on demand. So even with no preview traffic, the toggle is set for the session's lifetime. Whether the camera treats "keep-LV armed but no frames requested" as awake is exactly what needs measuring.

### L3 — The PTP session is never closed
`pgphoto` is a permanent process under the `polestar_app` watchdog (`checkGphotoTask: pgphoto is exit, reboot it`). Once `gp_camera_init()` succeeds, the session and interface claim persist for the life of the process — hours. On a PC, `gphoto2 --capture-image` opens, works, and exits; the claim is released and the link can idle. An open, claimed PTP session is itself enough to keep many bodies awake even when L1 is fine.

### What is probably **not** the cause (measure before touching)
- The supervisor poll loop (`camera_usb_supervisor.sh:149-150`, `while :; do sleep 1; fingerprint`). `fingerprint()` only reads cached sysfs attributes (`idVendor`, `idProduct`, `busnum`, `devnum`). Those are kernel-cached and do **not** issue USB control transfers, so a 1 Hz loop should not wake the camera. Cheap to verify by raising `OPENPOLARIS_USB_POLL_SECS` for one overnight run — but do not "fix" this first on assumption.
- Gimbal-side app polling (codes 284/517 shooting-mode list, 266 capture state, 778 battery, 525 temperature). Those talk to the gimbal, not the camera, so they are not obviously a camera-drain path. Note also: **we have never had a specific gimbal-battery problem** — the camera battery is the consistent one — so treating gimbal polling as a suspect here would be chasing a non-issue.

---

## 3. Measurement plan (read-only, no firmware change) — do this first

This is the only step that should be attempted before any code change. It also directly serves testing: an overnight soak that flattens the camera battery is not a soak.

### M1 — Idle power snapshot probe
A read-only script run on the Polaris, sampling every 60 s for ≥ 8 h, appending to a **durable** log (not `/app/Clog.txt`, which is subject to #213 truncation):

```sh
# READ-ONLY. Writes nothing outside its own output file. No camera traffic.
for d in /sys/bus/usb/devices/*/idVendor; do
  v=$(cat "$d" 2>/dev/null | tr 'A-F' 'a-f'); [ "$v" = "25fb" ] || continue
  dev=${d%/idVendor}
  printf '%s %s ctrl=%s status=%s autosusp=%s active=%s\n' \
    "$(date -u +%FT%TZ)" "${dev##*/}" \
    "$(cat $dev/power/control 2>/dev/null)" \
    "$(cat $dev/power/runtime_status 2>/dev/null)" \
    "$(cat $dev/power/autosuspend 2>/dev/null)" \
    "$(cat $dev/power/runtime_active_time 2>/dev/null)"
done
cat /sys/module/usbcore/parameters/autosuspend
```

Run the **identical** probe on the PC with the camera attached and nothing else running. The expected discriminator: PC reports `runtime_status=suspended` within a couple of minutes; Polaris reports `runtime_status=active` forever. If both report `suspended`, L1 is ruled out and the answer is L2/L3.

### M2 — Is there really no traffic?
"No activity" from the operator's seat is not the same as "no PTP traffic". Capture a bounded window of USB traffic on the Polaris while idle (`tcpdump -i usb0`-equivalent or `usbmon` if available in the vendor kernel) and count control transfers per minute. If there is steady traffic with no user action, attribute it before changing anything.

### M3 — A/B keep-LV
One overnight run with `STAGE2_PENTAX_KEEP_LV=0` exported in the wrapper environment, camera otherwise untouched, battery read at t0 and t+8 h. This is a pure A/B against the legacy per-frame teardown path that already exists and is already tested (`container/test_stage2_init_nullcall.c`). If the drain stops, L2 is confirmed as the dominant term.

### M4 — Camera-side confirmation
Read `/main/status/batterylevel` through the existing PTP owner at t0/t+1h/t+8 h rather than trusting the camera's LCD, so the numbers are recorded and not eyeballed.

> **Do not use `scripts/battery-check.py` for this.** It is labelled "Query camera battery (code 778)" but **778 is the gimbal battery**. Mlog shows its producer directly:
> `GimbalUartRxMsgProcTask[378]:Voltage:12.16;capacity:97;ChargeState:1;` → `SP_SendMsgToApp ... code[778]`.
> The voltages across every archived Mlog (10.7–12.4 V) are a gimbal pack, not a Pentax D-LI (~7.4–8.4 V), and Clog never emits 778. So `docs/evidence/battery-log.csv` holds only **3 gimbal-side rows** (65 → 100 → 67) and there is **no camera-battery telemetry recorded anywhere in the repo** — which is precisely why M4 matters. The tool's docstring has been corrected. `batterylevel` must be read through pgphoto's existing session, not a second gphoto2 client (that contends with session ownership — same class as #206 B1/B2).

> **Blocking dependency:** #213 (Mlog/Clog retain ~30 s and truncate at restart). An 8-hour measurement is worthless if the log it lands in is truncated on the next pgphoto restart. The probe must write to a path outside the app's rotating logs, or #213 must land first.

---

## 4. Suggested rectifications

All fail-closed and env-gated, following the existing convention (`STAGE2_SHUTTER_FALLBACK=0`, `STAGE2_CAPTURE_EMPTY_PATH_CHECK=1` in `pgphoto.wrapper.in`). Namespace: **`STAGE2_*`** for shim behaviour — not `OPENPOLARIS_*`, which is reserved for supervisor/wrapper plumbing (paths, poll counts, log targets) and is never read by the C loader.

### R1 — Enable USB runtime PM for the camera device only (if M1 shows L1)
In the pgphoto wrapper, after the stage-2 tree is up, set `power/control=auto` **for the selected camera's sysfs node only** — never globally, never for the gimbal's own devices. Guard it so it is skipped entirely while a capture or preview is in flight, and restore `on` before any shutdown path. This is a bounded readiness condition in the same style as the #119/#121 guards, not a blanket policy change to the vendor kernel.

Risk: suspending mid-transfer is exactly the class of fault that produced the orphan-candidate latch (#172) and the refusal-vs-fallback contract question (#205). The guard must refuse to suspend whenever a transfer candidate exists or a shutter is unresolved.

### R2 — Idle PC-LV release (addresses L2) — constrained by #147's architecture rule
The *behaviour* wanted is: when the workload owner is genuinely idle, release PC live view so the camera can fall back to its own sleep, and re-arm on the next real request.

**Constraint, not a free proposal:** implementing this as a Stage-2 process-global idle timer in `stage2_loader.c` would be exactly the pattern **#147 forbids** — "A Stage-2 process-global timer/boolean is not a scheduler" and "the previously attempted process-global LV pseudo-scheduler and connection-time forced LV OFF are not approved architecture". So it must live at the persistent request/session-ownership layer with explicit generation, operation lane and cancellation — not as another heuristic governor.

Requirements on whichever layer owns it:
- Default off (`STAGE2_PENTAX_IDLE_LV_SECS=0`), so shipped images are unchanged until qualified.
- Must not fire while a candidate/output obligation is pending (same predicate the admission gate already uses).
- Must not fire during the #121 settle window.
- Re-arm must go through `stage2_pentax_enable_keep_live_view()` so the #124 NULL-resolution guard still applies.

### R3 — Idle session close/reopen (addresses L3; highest risk)
Close the PTP session after a long idle and reopen on demand. Only worth considering if R1+R2 are insufficient. It collides head-on with the stale-session/rebind work (#182, #172, the supervisor's quarantine state machine) and with the "never delete or shoot over a preserved candidate" rule. Do not attempt without an explicit design review.

### R4 — Explicitly do **not** slow the supervisor poll loop yet
`OPENPOLARIS_USB_POLL_SECS` is already tunable per-run for the M1 experiment. Changing the default on assumption would trade a possible battery win for slower rebind detection (#57/#119/#126). Measure first.

---

## 5. Why this matters beyond live use

Every long-duration test we owe is currently capped at roughly one hour of camera battery:

- **#217** — the K-1 II has no qualification evidence on any build since `.65`; an unattended overnight run is precisely what that needs.
- **Bulb duration (#173/#186/#219)** — requested-duration → readback → file → EXIF chains need long, quiet sessions.
- Soak/recovery work (`o-v16c` SOAK-30 and successors) is bounded by the same clock.

If the camera can be let to sleep when idle, an overnight soak stops being a battery race. That alone justifies landing R2 behind a default-off gate even if live-use qualification takes longer.

---

## 6. Ambiguity to resolve before work starts

1. **Subject is settled:** camera battery. #119/#66 were camera-side too (see §1).
2. **Was Benro Connect connected** during the 1-hour run? A connected app drives the 284/517 and 266 polling loops; a disconnected one does not.
3. **Which body?** K-3 III (`25fb:0189`) and K-1 II (`25fb:0183`) have demonstrably different live-view timing (the 8 s vs 2 s preview interval split), so they may differ here too.
4. **Was preview ever opened** earlier in that session? keep-LV is armed at init, but the camera's own state may differ if PC-LV was actually started and then left.

---

## 7. Acceptance criteria for closing

- [ ] M1 run on both hosts with raw output attached; L1 explicitly confirmed or ruled out.
- [ ] M2 traffic count recorded (or an explicit statement that usbmon is unavailable on this kernel).
- [ ] M3 A/B battery numbers, same body, same starting charge, ≥ 8 h each side.
- [ ] If a rectification lands: default-off env gate, wrapper-pinned in `pgphoto.wrapper.in`, unit test alongside the existing `container/test_stage2_*.c` set, no regression on the #172 latch or #205 refusal contract, and implemented at the ownership layer per #147's architectural rule (not a new process-global governor).
- [ ] Evidence written somewhere that survives a pgphoto restart (#213).

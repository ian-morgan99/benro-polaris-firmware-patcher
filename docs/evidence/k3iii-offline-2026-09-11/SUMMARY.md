# K-3 III "killed the Polaris" — offline event, 2026-09-11 (night)

## Status: OBSERVED, NOT YET LOG-CAPTURED

This is a **verbal/observed** report from the 2026-09-11 session. The Polaris was
powered off for the night, so no Clog/Mlog was pulled for this specific event.
Treat as a reproduction of the known #55 failure mode, pending log capture on
the next power-on.

## What was observed (operator report)

- Firmware under test: **o-v7** (preview shims; model-gate bug still active — see
  `k1ii-k01-ov7-fieldtest-2026-09-10`).
- K-3 III attached to the Polaris.
- Gimbal **activated via Bluetooth** (BT connect pulse reached it), but the
  Polaris **did not come up / did not connect** — no `polaris_*` AP visible,
  SSH (192.168.0.1:22) refused, 9090 refused.
- Operator summary: "the K-3 III has killed the Polaris again."
- K-1 II was flat (powered down); K-3 III is the body on the rig.

## Why this is expected under o-v7 (not a new defect)

The 2026-09-10 v7 field-test logs (`k1ii-k3iii-2026-09-10-v7/polaris-logs/`)
show, for the K-3 III:

```text
[stage2] compatibility shims: bypassed for non-R5-II camera   (x8)
gp_camera_set_abilities ... ('Pentax K-3 Mark III (MTP mode)')
... get_single_config (camera, name, widget, context) failed: -2  (repeated)
```

i.e. the **colon-prefix model-gate bug** (`stage2_model_uses_pentax_keep_lv`
gated on `strncmp(model,"Pentax:",7)`) was still active, so the keep-live-view /
preview-backoff shims (#36/#55) were **silently inactive** on the K-3 III. With
the unbounded preview retry loop live and no backoff gate, a K-3 III preview
session starves the Wi-Fi radio → SSH lockout (issue #55). This is the same
mechanism as the 2026-09-09 `k3iii-lockup` event.

## What fixes this (already built, pending install)

- **o-v8-modelgate** — patcher `46f3e67` adds `0953dde` case-insensitive
  Pentax/Ricoh/GX10 model gate → shims actually engage.
- **o-v9c-failclosed-source** (current candidate) — libgphoto2 `1ef21463b`,
  patcher `1bd7e78`. Carries: corrected model gate, reviewed generic
  `manualfocusdrive` (libgphoto2 #59), and the **persistent launch-lock
  recovery** (`5d6b59f fix: recover persistent pgphoto launch locks`) that
  addresses the 2026-09-09 lockup.

## Next actions (overnight agent)

1. Power on the Polaris; if it is up, pull Clog/Mlog **before** touching the
   camera and confirm whether this event left a launch-lock / radio-starvation
   signature (cross-ref `k3iii-lockup-2026-09-09`).
2. Install **o-v9c** by the sanctioned SD-card/cold-boot flow (do NOT copy
   runtime libs over SSH). Verify installed Stage-2 hashes + provenance.
3. Confirm `[stage2] keep-lv:` now logs on the K-3 III (proves the model-gate
   fix engaged) and that preview is bounded (no radio starvation).
4. Re-run the A/B/C physical matrix (K-01, K-1 II, K-3 III) per
   `docs/HANDOVER-2026-09-11.md`.

## Cross-links

- #55 — unbounded preview retry loop starves Wi-Fi radio → SSH lockout (this event is a reproduction).
- #34 — pgphoto/watchdog recovery after camera-session disruption.
- `docs/evidence/k3iii-lockup-2026-09-09/` — the persistent launch-lock failure + `5d6b59f` fix.
- `docs/evidence/k1ii-k01-ov7-fieldtest-2026-09-10/SUMMARY.md` — model-gate root cause.
- `docs/HANDOVER-2026-09-11.md` — current state + o-v9c install plan.

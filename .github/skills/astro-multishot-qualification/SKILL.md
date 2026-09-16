---
name: astro-multishot-qualification
description: Deterministically qualify repeated Pentax captures through OpenPolaris and the Benro Polaris, including identity proof, preview ownership, capture/file correlation, Wi-Fi counters, and fail-closed evidence collection. Use for Astro, interval, repeated-shutter, or preview-plus-capture testing on physical Polaris hardware.
---

# Astro multi-shot qualification

Use `scripts/test-astro-multishot.py`; do not reproduce its protocol with ad-hoc
socket commands. Read `.github/skills/polaris-debugging/SKILL.md` first. For a
new firmware install, also read and follow `.github/skills/fwpkt-update-flow/SKILL.md`.

## Preconditions

1. Prove the laptop is associated with the real `polaris_*` AP, route
   `192.168.0.1` through that Wi-Fi interface, and read `/app/FwVer` over SSH.
2. Record `/app/openpolaris-libgphoto2-provenance.txt`, the OpenPolaris commit,
   camera model, camera power/battery state, USB enumeration, and active 8080 /
   9090 clients.
3. Capture baseline `dmesg` counts for `No more free tdata_psh_info` and
   `Out of tdata_disc_grp`. Historical non-zero counts are not a new failure;
   growth during this run is.
4. Start from an idle camera with enough battery and storage. Do not delete an
   unknown camera or Polaris file to make the test pass.

## Run

Create an evidence directory outside the source tree or under
`docs/evidence/`. Run one ordinary shot before a sequence:

```bash
python3 scripts/test-astro-multishot.py \
  --host 192.168.0.1 \
  --bind <polaris-wifi-ip> \
  --shots 1 \
  --interval 10 \
  --shot-timeout 180 \
  --execute | tee <evidence>/ordinary-shot.log
```

Only after that passes, simulate Astro repeated shooting:

```bash
python3 scripts/test-astro-multishot.py \
  --host 192.168.0.1 \
  --bind <polaris-wifi-ip> \
  --shots 5 \
  --interval 30 \
  --shot-timeout 600 \
  --execute | tee <evidence>/astro-five-shot.log
```

The script authenticates, records the initial preview state, obtains exclusive
capture conditions, correlates each shutter with its capture lifecycle and
file event, and refuses to fire the next shutter until the preceding shot has
a positive terminal result. It exits non-zero on disconnect, negative state,
ambiguous completion, missing correlation, or timeout.

While it runs, preserve—not filter away—the full 9090 transcript, `/app/Clog.txt`,
`dmesg`, process/listener ownership, and Wi-Fi counters. Do not run a second
9090 controller during the qualification.

## Pass criteria

All must hold:

- every requested shutter has exactly one positively correlated completion;
- no shot is accepted merely because a fixed timer elapsed or state returned
  to idle;
- preview is restored to its initial state after the sequence;
- pgphoto and polestar_app retain their expected PIDs/listeners;
- no new Stage-2 negative return, crash loop, USB loss, or DHD pool exhaustion
  appears;
- output files are unique, non-zero, and attributable to the corresponding
  shot; and
- a final ordinary shutter still passes after the sequence.

Report `PASS`, `FAIL`, or `OUTCOME UNKNOWN`. `OUTCOME UNKNOWN` is a stop result,
not permission to continue shooting. Record the first abnormal transition and
the single recovery action used. Never combine cable reconnect, camera power
cycle, pgphoto restart, and Polaris reboot in one diagnostic step.

## Handoff record

Include the exact commands, UTC interval, device/build identities, camera,
OpenPolaris commit, per-shot correlated lifecycle/file, before/after Wi-Fi
counters, preview restoration, log paths, and first divergence. A harness pass
is not physical qualification unless this evidence comes from the named device
and camera.

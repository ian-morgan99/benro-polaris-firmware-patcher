# o-v18d (`.74`) install — VERIFIED 2026-10-27

Candidate: `o-v18d-shutter-list-always-populated` -> `FwVer:6.0.0.54.74;date:2026.10.27;`
zip md5 `307d8bd4ca4264973a16df0d0586de48`
Provenance: libgphoto2 `8db3785f7`, patcher `ffb2e50`

## Verdict: INSTALLED AND VERIFIED (behaviour unqualified — no camera attached)
- Pre-release gate GREEN: 11 passed, 0 failed, 1 skipped (transcript attached)
- All six `firmwareInfo` MD5s matched on-device before reboot
- Device went dark; **uptime reset 28668s -> 14s** proves a real boot
- `INSTALLED BUILD IDENTITY: PASS`; Mlog shows `SP_EVENT_UPGRADE_SUCCESS` then
  `SP_DelUpgradeFiles: remove /app/sd/FwPkt`
- Flashed `ptp2.so` contains both fixes (verified by string match on-device)

## What this candidate ships
1. **Timed Bulb duration from the measured hold** (#243). `.72` captured at the
   *previous* shot's duration because the pre-shutter admission probe reports the
   OLD timer. The measured hold is authoritative again; the body's report is kept
   as a diagnostic only.
2. **The shutter list is always populated** (#241). In B mode with no JPEG the
   camera returns an empty list, which the device forwarded to the app as
   `RD:0;V:0;R:00:00,;` — a one-entry list whose only entry is the bogus `00:00`.
   The body's own Bulb/seconds entries are now re-added when the list comes back
   empty, so it is never empty and never carries a bogus value. This is the
   Benro Connect crash in Bulb non-timed **and** on a mode-dial change — both
   share this one cause.

## Gate skip recorded (per AGENTS.md)
`SKIP: firmwareInfo manifest gate (no stock firmware/FwPkt.zip in repo)` — a
prerequisite gap, not a pass. The on-device MD5 verification in the install
transcript covers the same ground for this candidate.

## NOT qualified — no camera attached
`lsusb` shows only a hub (`1a40:0101`); no Pentax body is enumerated. Neither
fix has been exercised against hardware:
- timed Bulb duration must be checked against a selected second-count
- the non-timed B crash must be re-tested, and the mode-dial change too

The candidate is "installed, canary pending" — never "qualified".

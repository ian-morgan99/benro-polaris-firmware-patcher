# Release record — 2026-10-26 to 2026-10-27

Consolidated record of the Bulb work: what was built, what was installed, what
was proven, what was wrong, and what remains unqualified. Written after the TA's
review of the recent commits, so the corrections are part of the record rather
than lost in commit history.

## Candidate timeline

| version | candidate | libgphoto2 | patcher | state |
|---|---|---|---|---|
| `.71` | `o-v18a-diag-20261025` | `f95bc575` | `7d534319` | installed + verified; **superseded by `.74`** |
| `.72` | `o-v18b-bulb-duration-from-body-20261026` | `749d38f6` | `cd892ba` | installed + verified; **regressed the duration (#243)** |
| `.73` | `o-v18c-bulb-duration-measured-hold` | `27540e122` | `d5ba81e` | built + gated; never installed |
| `.74` | `o-v18d-shutter-list-always-populated` | `8db3785f` | `ffb2e50` | **installed + verified**; behaviour unqualified |

All four are registered in `docs/FWPKT-PROVENANCE-CONTRACT.md` with zip MD5,
SHA-256, appfs MD5, both source SHAs and the PrivateResearch artifact location.

## What was fixed

### 1. Timed Bulb second-count was refused (#239)
Selecting a second-count from the B list returned `-6` (`GP_ERROR_NOT_SUPPORTED`).
The camera-timed path was refused outright because the body runs its own
countdown and rejects a held shutter. `.71` replaced the refusal with a deferred
capture: the start edge records a timestamp and succeeds, and the matching stop
edge turns the measured hold into a shutter-speed write plus one ordinary
camera-timed capture.

**Verified on hardware:** the operator confirmed a file is produced and its
`ShutterSpeedValue` matches the selection.

### 2. Timed Bulb captured at the previous shot's duration (#243)
`.72` changed the duration source from the measured hold to the body's reported
`bulb_timer_seconds`. That was wrong: the value comes from the **pre-shutter
admission probe**, read before any shutter command is sent, so it still holds the
*previous* shot's timer. The stale value propagated verbatim to the stop edge and
was written as the shutter speed.

`.73`/`.74` restore the measured hold as authoritative and keep the body's
report as a diagnostic only, under a name that says what it is
(`bulb_action_body_reported_seconds`).

### 3. Benro Connect crash in Bulb non-timed and on a mode-dial change (#241)
Derived entirely from the already-captured corpus in
`docs/evidence/benro-connect-crash-20261010/` (60 MB, including the rotated
`system-log/` series) — no new capture was needed.

**The data that differs:** the Pentax Shutter/Bulb descriptor comes back with
`enum-count=0` — an **empty shutter list** — while every other Pentax descriptor
in the same dump has a real count. The cause is in the Mlog:

```
MsgFromCamera-->type[1],code[282],val[format:0;]
camera img format:0
camera format no include jpg        <-- ERROR
```

In B mode the body offers no JPEG, so the shutter list is empty. The device
forwards that to the app as `RD:0;V:0;R:00:00,;` — a one-entry list whose only
entry is the bogus `00:00` — and the app has nothing valid to select.

The correlation is exact: `camera format no include jpg` appears **only** in the
four logs whose shutter list is empty, and in none of the others. In
`Clog_000276` the list is `0` through 21:43:41 and becomes `56` at 21:44:46 as
the dial leaves B, with `pgphoto is exit` one second later.

`.74` re-adds the entries the body itself publishes in a populated list
(1, 2, 3, 4, 5, 6, 8, 10, 13, 15, 20, 25, 30 seconds) when the camera returns
an empty enumeration, so the list is never empty and never carries a bogus
value.

**This is not proven to be the crash cause.** The empty list is proven specific
to the no-JPEG/B state and to precede the exits; that it is *what the app
crashes on* is inferred. Benro Connect is closed and no captured log has an
app-side stack. #241 stays open.

## Corrections made to my own published claims

Recorded because the record is only useful if it includes what was wrong.

| claim | status |
|---|---|
| "25 of 35 app connections die after code 266" | **retracted** — 21 of those were single-frame probes whose only message is 266; the 13 real sessions end across seven codes with no concentration |
| "no stop = crash" | **retracted** — the control shows normal captures are equally "no stop"; the Bulb stop is code 265, not `264 state:0` |
| "stack overflow in the preview shim" | **disproven** — `sizeof(CameraAbilities)` is 2504, it fits in the 4096 buffer |
| "pgphoto segfaults in the non-timed session" | **wrong** — `CRASH sig` appears in zero captured `Clog_*`; the 60–107 re-init cycles are external `restart_gphoto` restarts |
| "the ASCII-`pc` SIGSEGVs are this session" | **wrong** — they are in `stage2-crash-20261008.log` and the 190-repro, different sessions and dates |
| "`.71` install status recorded" | **wrong** — the `sed` was a silent no-op; `.71` predates that wiring |
| "the gate was skipped" | **wrong** — the gate was wired in and ran for `.73` (11 passed, 0 failed, 2 skipped); the gap was that its output was not preserved |

## TA review findings and what was done about them

### #239 — fail-open exposure defect
> on the deferred STOP edge, `ptp_setdevicepropvalue(ShutterSpeed, ...)` may
> return non-OK, but the code logs *"capturing at the camera's current setting"*
> and still calls `camera_pentax_capture_internal(...)`. A requested `bulb:2`
> could produce a successful file at an unrelated pre-existing shutter speed.

**Fixed in `e7d0cf1dd`.** A failed write now returns a mapped error and
initiates **no capture**. A write that returns OK but did not change the
property is caught by a fresh readback; a mismatch also refuses to capture.

### #241 — the empty-list workaround was not a qualified fix
> the new branch runs for *every* supported model with an empty enumeration, but
> the 13 injected values were derived specifically from a populated **K-3 III**
> list. There is no model gate, no check that the camera is in the observed
> B/no-JPEG state, and no verification that those entries are writable there.

**Fixed in `e7d0cf1dd`.** Synthesis is gated by
`pentax_shutter_list_may_synthesise_bulb()`, which returns true only for
`PENTAX_MODEL_K3_MARK_III`. K-1 II, K-01, the Monochrome K-3 III, KP and K70 are
negative cases in the test suite. The camera's current value is also pointed at
the first synthesised entry, because the captured B-mode value is `0` (which
formats as "Auto") and `_get_Ricoh_ShutterSpeed` ignores the return of
`gp_widget_set_value`, leaving the radio with no selected entry.

### #243 — elapsed time is not a release-qualified duration contract
> the dispatcher already receives the actual `bulb:N` value as `r1`/`bTime`,
> whereas `ptp2_pentax_bulb_action(camera, enabled, ...)` receives only a
> boolean. Its `pentax_monotonic_ms()` interval measures when two calls arrived,
> not the user's requested N.

**Acknowledged, not yet fixed.** The explicit-N path exists but is **not** in
libgphoto2: the app sends `code:261;val:s:<index>` and the *device* resolves
that index against the shutter list it holds, then programs the camera. libgphoto2
only ever sees a boolean. So the measured hold remains the only duration
libgphoto2 can derive, and it is a **diagnostic**, not a release-qualified
contract. The fail-closed write + readback in `e7d0cf1dd` bounds the
consequence: a wrong duration can no longer be exposed silently, because the
write is verified before the capture starts.

### #239 — `.71` provenance blocker
> `docs/FWPKT-PROVENANCE-CONTRACT.md` still has **no `.71` row**, despite the
> PrivateResearch README pointing to that registry.

**Fixed.** The `.71` row is added with the verified zip MD5
(`170293f896c8ee1fadde4a9bb16533ac`), SHA-256
(`b634394d…d90c799d`), appfs MD5 (`78f4460e…`), both source SHAs, the artifact
location and its status. The libgphoto2 commit `f95bc575` now resolves from
`origin/main`; the patcher commit was built from the
`release-o-v18a-diag-20261025` branch, whose only change was build-failure
logging, not a change to the shipped payload.

## Release-process gaps found and closed

The process was documented but not enforced, so a build could deviate without
anything stopping it. All three gaps are now enforced by the tooling:

1. **The build refused its own tree.** The documented `TMPDIR` workaround puts
   scratch inside the workspace, but `.buildtmp/` was not gitignored, so
   `git status --porcelain` was non-empty and the build aborted with "patcher
   checkout is dirty" — *after* the version had been derived. Now ignored.
2. **The gate's SKIPs were never recorded.** AGENTS.md requires them in the
   release evidence, but the transcript only existed in the build log. The gate
   now writes `<candidate>/gate-transcript.txt`, fails the build if the gate
   fails, and prints the skip list explicitly.
3. **A stale `build/` in the libgphoto2 input was only found after a full
   build.** It is gitignored, so the dirty check cannot see it, but
   `container/build_ptp2.sh` copies the input with `cp -a` and the container
   reuses objects compiled before the `_Camera` padding, failing the fail-closed
   ABI check. The build now refuses such an input up front. Verified: the guard
   fires before any build work is done.

## Install verification (`.74`)

- Pre-release gate GREEN: 11 passed, 0 failed, 1 skipped (transcript attached)
- All six `firmwareInfo` MD5s matched on-device before reboot
- Device went dark; **uptime reset 28668 s → 14 s** proves a real boot
- `INSTALLED BUILD IDENTITY: PASS`
- Mlog: `SP_EVENT_UPGRADE_SUCCESS` then `SP_DelUpgradeFiles: remove /app/sd/FwPkt`
- Both fixes confirmed present in the flashed `ptp2.so` by string match on-device

## What is NOT qualified

**No camera was attached to the rig** (`lsusb` shows only a hub `1a40:0101`), so
neither fix has been exercised against hardware. `.74` is **"installed, canary
pending"**, never "qualified".

Outstanding:
- timed Bulb duration against a selected second-count
- the non-timed B crash
- the mode-dial-change crash
- the K-1 II matrix in `docs/pentax-physical-operative-runbook.md` (#217)

## Evidence index

| what | where |
|---|---|
| `.71` install | `docs/evidence/o-v18a-install-20261026/` |
| `.72` install | `docs/evidence/o-v18b-install-20261026/` |
| `.74` install + gate transcript | `docs/evidence/o-v18d-install-20261027/` |
| empty-shutter-list analysis | `docs/evidence/benro-connect-crash-20261010/analysis/SHUTTER-LIST-EMPTY-IN-NONTIMED-B.md` |
| crash corpus (60 MB, pre-existing) | `docs/evidence/benro-connect-crash-20261010/` |
| `.72` crash log loss | `docs/evidence/o-v18b-crash-20261026/` |
| stage2 crash logs (different sessions) | `docs/evidence/stage2-crash-logs/` |
| K-1 II qualification matrix | `docs/pentax-physical-operative-runbook.md` |
| install process | `docs/FIRMWARE-INSTALL-PROCESS.md` |

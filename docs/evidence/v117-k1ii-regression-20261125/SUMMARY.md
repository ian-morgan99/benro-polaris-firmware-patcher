# v117 on-hardware regression: the stage2 admission gate leaks its claim

Device: Polaris head, `FwVer:6.0.0.54.117;date:2026.11.25;`, installed and
identity-confirmed by `release-fwpkt.sh` on 2026-11-25 (MD5s verified on-device,
reboot confirmed by `/proc/uptime` reset 167967 s -> 28 s).
Camera: **Pentax K-1 II**, USB `25fb:0183`, bus 001 / device 003.
Also observed earlier the same day with a K-3 III (`25fb:0189`): same failure.

## What is NOT wrong

**Recognition works.** `/app/Clog.txt` records the body identifying itself:

```
recv_ipc_msg ... code[282],val[urer:ricoh imaging company, ltd.;model:pentax k-1 mark ii;state:1;storage:2;photoFormat:1;]
```

`state:1`, `storage:2`, `photoFormat:1`. The K-1 II is recognised, initialised and
vendor-enabled. The earlier "not recognised" report was a misreading of the symptom:
the app shows *connect the camera* because every operation **after** recognition is
refused, not because enumeration failed.

**pgphoto is not crashing.** `pidof pgphoto.stage2ondisk` returned one stable pid
(21008) with 7 threads, fd 9 open on `/dev/bus/usb/001/003`, and the supervisor
(pid 661) had been running continuously since boot. No core file, no restart storm.
The *connect the camera* message is a control-plane refusal, not a process death.

## The actual fault

Every refusal in the captured window is the same line:

```
[stage2] camera admission refused: site=100540 kind=2 owner_site=102cd4 last_owner_kind=0 generation=1 camera_present=1 budget=500
```

Aggregated over the 9 refusals in `Clog.clean.txt`:

| count | site | kind | owner_site | last_owner_kind | generation |
|---|---|---|---|---|---|
| 7 | 100540 | 2 (CONFIG) | **102cd4** | **0 (CONTROL)** | 1 |
| 2 | 100540 | 2 (CONFIG) | 100540 | 2 (CONFIG) | 1 |

Three facts follow directly from that table:

1. `generation=1` on every refusal. `stage2_loader.c` bumps
   `native_gate.generation` inside the wrapped `gp_camera_init`, so init ran exactly
   once and the gate was never re-armed for this session.
2. `owner_site=102cd4 last_owner_kind=0` persists across 7 consecutive refusals from
   a different site. A **CONTROL** operation acquired the claim at `0x102cd4` and
   never released it. `owner_tid` therefore stays non-zero forever, so every later
   `atomic_compare_exchange_strong(&gate->owner_tid, &free_tid, tid)` fails and
   `stage2_camera_claim()` returns -1 without ever retrying.
3. Two refusals show `owner_site=100540 last_owner_kind=2` — the config site owning
   its own claim, i.e. a nested re-claim of the same return address.

`stage2_camera_release()` is tid-gated:

```c
if (tid && atomic_load(&gate->owner_tid) == tid) { ... }
```

pgphoto is **multithreaded** (7 threads observed). If a claim is acquired on one
thread and the matching `setCameraStatus(0)` lands on another, the release is
silently skipped and the claim leaks permanently. That is the mechanism, and it is
consistent with all three observed states above.

## Why each reported symptom follows

One leaked claim explains everything the user saw:

- **Parameters do not stick.** Every config read answers the sentinel `-1`, then the
  head serves a hard-coded fallback list:
  ```
  recv_ipc_msg ... code[265],val[-1]
  getCameraConfig from local configType 0  ret 0
  send_ipc_msg_retry ... code[265],val[RD:0;V:1;R:100,200,400,...]
  ```
  The UI is displaying a **compiled-in default list**, not camera state. A write
  cannot land because the SET path needs the same gate. This matches "changing
  parameter values do not stick" exactly.
- **Liveview goes black then reconnecting.** `updateViewFinder enable:1 ret:-1` —
  preview admission is refused (`has_priority(PREVIEW)` is false while controls are
  waiting, and the claim is held regardless). Works briefly, then the leaked claim
  blocks it permanently. Explicitly **not garbled**, consistent with refusal rather
  than corrupt frames.
- **5 s bulb shot fails.** The countdown is driven by the app; the capture dispatch
  needs the gate and is refused, so nothing reaches the body.
- **K-1 II fails faster than K-3 III.** Both hit the same gate; the K-1 II's heavier
  control traffic acquires and leaks the claim sooner. Same root cause, different
  time to wedge.

## Regression window — this is a v115+ regression, not v117-specific

`git log -S native_claim_from -- container/stage2_loader.c` yields exactly one
commit:

```
fbfa133a13586cb4460a856ef5215d6dcb3a66f1  2026-11-22  fix(stage2): native camera claim via stage2_camera_claim gate
```

Testing that commit against every patcher pin recorded in `RELEASE-VERSION-STATE.md`:

| firmware | patcher pin | contains fbfa133a |
|---|---|---|
| `.114` | `87032af4e2dd…` | **no** |
| `.115` | `f67c6baf5f57…` | **yes** |
| `.116` | `65785529a873…` | **yes** |
| `.117` | `e0464f394603…` | **yes** |

So the gate — and therefore this regression — first shipped in **`.115`**. `.114`
predates it. That matches the user's statement that "all these parameters were
settable some time ago in some version": `.114` is the last version without the
gate, and it is the version currently reported as installed before today's flash.
v117 did not introduce this; it inherited it.

## What is proven vs. what still needs a device

Proven from evidence in this directory: recognition succeeds; pgphoto stays alive;
the gate leaks a CONTROL claim at `0x102cd4` and never re-arms (`generation=1`);
config reads return `-1` and fall back to hard-coded lists; preview enable returns
-1; the regression window is `.115`..`.117` and `.114` is clean.

Not yet proven, and deliberately not guessed:

- **Which thread pair leaks it.** Requires live `/proc/<pid>/task/*` tracing while a
  control op runs. The head went unreachable mid-investigation (see below), so this
  is untested.
- **The correct wire subtype for a parameter SET.** No script or doc in this
  repository records it; `send()` defaults to subtype 2 and only capture (`264`) has
  a documented subtype 4. I did not blind-write SET frames:
  `scripts/probe-b-list-and-held-bulb.py` documents that an earlier version of itself
  fired two real exposures by guessing. `scripts/probe-config-gate.py` is therefore
  read-only by construction.

## Superseded by [FINDINGS.md](FINDINGS.md)

This page was written from the first, partial log pull (9 refusals). SSH came back and a
full pull followed (`logs/`), which found **71** refusals in `Clog_000012.log` and two
distinct refusal signatures rather than one. The diagnosis below is directionally right but
incomplete: the leak has **three** causes, not one, and the largest group (24 of 71) is a
self-deadlock where the owner is the refusing site itself. Read FINDINGS.md for the
authoritative version and for the implemented fix.

## Investigation was cut short

`wlp8s0` dropped mid-session: full rescan returns no `polaris_*` SSID, `nmcli dev
wifi connect polaris_d13e86` reports *No network with SSID found*, SSH to
`192.168.0.1:22` is refused, and `192.168.0.1` still answers ping from a route via
`192.168.68.1` — i.e. something else holds that address now. The local bind address
`192.168.0.4` is gone with the interface, which is why `probe-config-gate.py` exits
with `Cannot assign requested address`. No further live testing was possible; the
K-1 II remains plugged in for whoever picks this up.

## Files here

| file | what it is |
|---|---|
| `Clog.txt` | raw `/app/Clog.txt` as pulled (ANSI escapes intact) |
| `Clog.clean.txt` | same, escapes stripped, greppable |
| `Mlog.txt` | raw `/app/Mlog.txt`. Contains **no** pgphoto/stage2/supervisor lines — mount-side logging does not cover the camera layer, so it cannot corroborate a crash |
| `openpolaris-libgphoto2-provenance.txt` | on-device driver provenance |
| `polaris-astro-boot.log` | astro kit boot log |

## Fix direction (implemented — see FINDINGS.md)

All three directions below were implemented, each with a mutation-checked test. Direction 1
became a reentrant claim with depth tracking rather than a claim token; direction 2 became
`stage2_camera_gate_reset()` called from `gp_camera_init`; direction 3 became a 120 s lease
with an injectable clock and a `leases_stolen` counter. The lease is deliberately long so it
cannot interrupt an operation that is genuinely running, and it disables itself if
`CLOCK_MONOTONIC` is unavailable rather than guessing.

The gate needs to survive the thread topology it is actually deployed in. Options,
in order of how much I'd trust them:

1. **Release by claim token, not tid.** Hand out a monotonically increasing claim id
   from `stage2_camera_claim()` and have `native_set_camera_status(0)` release that
   id regardless of which thread calls it. This removes the failure mode rather than
   papering over it.
2. **Re-arm on session generation.** `generation` is bumped in `gp_camera_init`, but
   a leaked claim from a *previous* generation still blocks the current one because
   the loop breaks out on the generation check instead of reclaiming. Reset
   `owner_tid`/`busy_word` when the generation advances.
3. **Bounded watchdog.** If `owner_site` is unchanged and no release arrives within
   N polls, force-release and log it loudly. Last resort — it can release a claim
   belonging to an operation genuinely in flight.

`container/test_stage2_native_admission.c` exercises same-thread acquire/release and
a competing preview, but has **no cross-thread release case**. Any fix must add one;
without it the harness cannot catch this class of bug, which is exactly how `fbfa133a`
shipped.

# Two gates, one wedge: correcting my own #177 diagnosis and finding the real one

2026-11-26, K-1 II rig (v118, `o-v18a`). This supersedes the mechanism I posted on #177 earlier today.
I was wrong twice; both corrections are below, with the evidence that refutes each.

## Correction 1 — the `-1005` is not libgphoto2, and a refusal cannot latch it

I claimed a bulb *refusal* latches `capture_output_pending`. It cannot: the set site is library.c:7230
(`if (!bulb_action_finalize) params->pentax.capture_output_pending = 1;`), which sits **after** the mode
guard at 7168 that returns early. The trace confirms it — capture=4 enters with `output_pending=0` and never
logs `boundary=initiate-enter`:

```text
[pentax] capture=4 boundary=camlib-enter transfer=0 recovery=1 output_pending=0
[pentax] capture=4 boundary=preconditions-return ptp=0x2001 size=576
----CAPTURE bulb start  -6
captureBulbImage ret -6
```

And the `-1005` I attributed to the camlib gate is emitted by **our stage2 shim**, not libgphoto2:

```text
[stage2] camera admission refused: site=100540 kind=2 owner_site=100540 last_owner_kind=2
    generation=1 camera_present=1 budget=500 tid=1014 owner_tid=2006 depth=1 held_ms=3315 stolen=0
```

## Correction 2 — the stage2 lease DOES work; I never waited long enough

I claimed the lease takeover is unreachable and that only a reboot recovers. A deterministic test with
production values refutes the first half:

```text
production lease_ms=120000
t+3s   : ret=-1 polls=500 stolen=0 owner=5     # lease not yet expired -> refused (correct)
t+121s : ret= 0 polls=  0 stolen=1 owner=7     # lease expired -> taken over on the first poll
```

`stage2_camera_claim()` evaluates the lease **on entry**, so a waiter arriving after 120 s recovers
immediately without polling. The `stolen=0` in all 212 logged refusals means no waiter arrived inside that
window — not that takeover is broken. The existing `test_lease_expires_a_leaked_claim()` covers this; it just
uses `lease_ms = 1000`, which is why the production interaction was never exercised.

## So there are two independent gates, and only one has a lease

| gate | location | liveness check | recovery |
|---|---|---|---|
| stage2 admission | `container/stage2_policy.c:186` | 120 s lease, checked on entry | self-heals after 120 s |
| camlib output obligation | `camlibs/ptp2/library.c:7230` | **none** | reboot only |

The stage2 gate is healthy. The wedge that survives 150 s is the **camlib** one, and it has no timer at all.

## Measured: the wedge persists well past the lease

Triggered deliberately on a clean boot — timed bulb from Manual (`-6`), then plain capture repeatedly:

```text
+   0.3s trigger state=-6
+   0.5s capture state=-112
+  30.2s capture state=-1005
+  60.2s capture state=-1005
+  90.2s capture state=-1005
+ 120.3s capture state=-1005     <-- stage2 lease already expired here
+ 150.2s capture state=-1005
```

During that window the camlib is entered and refuses on its own gate, while the stage2 gate logs almost
nothing:

```text
gate_refusals=1
pentax_lines=18
[pentax] capture=6 boundary=camlib-enter transfer=0 recovery=1 output_pending=1
[pentax-recovery] capture=6 path=recovery-probe reason=unsafe-activity ... field32=0x00000001 field36=0x00000001
[pentax] capture=7 boundary=camlib-enter transfer=0 recovery=1 output_pending=1
```

## The latch has no path back to zero once the camera reports unsafe activity

Only three sites clear it, and each requires a successful capture cycle:

- `library.c:6789` — inside `pentax_admission_apply_output_obligation()`, reachable only when
  `camera_reason == PENTAX_ADMISSION_BLOCK_NONE`. With `BLOCK_UNSAFE_ACTIVITY` the function returns at the
  guard above it, so this never runs.
- `library.c:7250` — on a failed InitiateCapture, but only when
  `!pentax_capture_initiate_response_ambiguous(ptpres)`.
- `library.c:7706` — after publication, gated on `pentax_capture_output_obligation_resolved(...)`.

Once latched with the camera reporting unsafe activity, none of the three can fire: admission is refused
before InitiateCapture, so there is no publication and no initiate-failure path. That is a genuine dead end,
and it is what #177's title describes — *"capture_output_pending has no path back to zero"* — reached via
unsafe activity rather than the idle-camera case the existing fix handles.

## What I did not do, deliberately

I have not changed the locking. The stage2 gate is demonstrably self-healing and the camlib gate's
fail-closed default is correct — a double publication is worse than a refusal. The missing piece is a
bounded liveness check on the camlib latch equivalent to the stage2 lease, and that needs a design decision
about what "the camera no longer owes this output" means when its own conditions word says unsafe. Guessing
at that in shutter-issuing code is how we got here.

## Corrections worth keeping

- `lsusb | grep -c pentax` is invalid on this busybox build (no product strings); use `grep -c 25fb` or sysfs.
- Killing pgphoto does not recover the rig — it breaks the app↔pgphoto IPC link and capture then returns
  `-1` in 0.0 s with no capture lines reaching pgphoto at all. Reboot is the only working recovery.
- `held_ms` across 350 refusals: min 61, median 3026, max 5911 ms against budgets of 500 polls (~1 s at the
  2 ms poll). Most refusals are legitimate contention; how many surface to the user as a failed capture is
  still unmeasured, and that number decides whether the budget needs changing.

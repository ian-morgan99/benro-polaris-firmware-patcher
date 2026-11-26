# v115-v117 camera-gate wedge: parameters stop sticking, live view dies, capture fails

## Symptom set reported on 6.0.0.54.117 with a Pentax K-1 II

- "It keeps periodically saying 'connect the camera'"
- "Liveview works for a moment, then goes black then shows reconnecting"
- "Changing parameter values do not stick"
- "Taking 5 second shot with bulb wheel shows 5 second countdown but shot failed"
- K-1 II fails faster than the K-3 III, but both fail

The camera is **recognized**. `/app/Clog.txt` contains:

```
recv_ipc_msg ... val[urer:ricoh imaging company, ltd.;model:pentax k-1 mark ii;state:1;storage:2;photoFormat:1;]
```

So this is not a detection/USB regression. Everything after that line is refused by our own
Stage-2 camera admission gate.

## Evidence

`logs/system-log/Clog_000012.log` (pulled with `scripts/pull-mlog-clog.sh`): **71 refusals** in one
window; the other 11 rotated Clogs contain none.

```
$ sed 's/\x1b\[[0-9;]*m//g' Clog_000012.log | grep -c "admission refused"
71
```

Refusal shape (all of them):

```
[stage2] camera admission refused: site=100540 kind=2 owner_site=102cd4 last_owner_kind=0 generation=1 camera_present=1 budget=500
```

Histograms:

```
owner_site/kind/generation:
     27 owner_site=101b0c last_owner_kind=0 generation=1
     24 owner_site=100540 last_owner_kind=2 generation=1
     15 owner_site=102cd4 last_owner_kind=0 generation=1
      5 owner_site=100540 last_owner_kind=3 generation=1

refusing site/kind:
     66 site=100540 kind=2   (CONFIG/SET, deal_camera_control_handler+0x60)
      3 site=100540 kind=3
      1 site=102cd4 kind=0
      1 site=101b0c kind=0
```

Two facts carry the diagnosis:

1. **`generation=1` on all 71.** `gp_camera_init` bumps the gate generation once per session. It
   never advanced, so the gate was wound up once and stayed wedged for the whole window.
2. **`owner_site == refusing site` 24 times** (`site=100540 owner_site=100540`). The owner of the
   claim is the same call site that is being refused: the thread is waiting on a claim it already
   holds. Nothing can ever free it.

Interleaved with the refusals, every parameter read returns `-1` and the app falls back to its
built-in lists:

```
recv_ipc_msg ... code[265],val[-1]
getCameraConfig[724]: ----getCameraConfig from local configType 0  ret 0
updateViewFinder enable:1  ret:-1
```

`val[-1]` is the refusal surfacing as a failed read; `from local configType N` is the app serving a
hardcoded list instead of the camera's real one. That is why values do not stick.

## Root cause

`container/stage2_policy.c`, introduced by `fbfa133a` ("fix(stage2): native camera claim via
stage2_camera_claim gate", 2026-11-22). Present in v115, v116 and v117; **absent from v114 and
earlier**, which is why parameters were settable before.

Three independent defects, each sufficient to wedge the camera permanently:

1. **Not reentrant.** `stage2_camera_claim()` admitted only when `owner_tid` was 0. A native handler
   that already held the claim and then reached a second `waitCameraIdle` on the same thread
   (`deal_camera_control_handler` -> `setCameraConfigWithCommand` -> wait) was refused by its own
   claim. Self-deadlock, matching the 24 self-owned refusals.
2. **Reinitialise did not clear the claim.** `gp_camera_init` did
   `atomic_fetch_add(&native_gate.generation, 1)` and nothing else. The bump invalidates *waiters*
   but leaves `owner_tid`, `owner_site` and the native busy word in place, so a fresh session
   inherits a dead session's claim. This is why every refusal reads `generation=1`.
3. **Nothing bounded a claim.** Release is tid-gated (`native_set_camera_status(0)` only frees when
   `owner_tid == gettid()`). pgphoto runs 7 threads; if the operation returns on a different thread,
   or bails before the status write, the key is never handed back and the wedge is permanent.

## Fix

`container/stage2_policy.{c,h}`:

- **Reentrancy.** A claim by the current owner is admitted and counted in `owner_depth`; release
  decrements and only the outermost release frees the gate. Other threads are still locked out.
- **`stage2_camera_gate_reset()`** clears owner, site, kind, depth, lease and waiter counts as well
  as winding the generation. Called from `gp_camera_init` in place of the bare generation bump.
- **Lease.** Every claim records `lease_started_ms`; a request that finds another thread's claim
  older than `stage2_camera_lease_ms` (default 120 s) takes it over and increments `leases_stolen`.
  Bounds the worst case from "forever" to one lease period without stealing from an operation that
  is genuinely running: 120 s exceeds any legitimate single native call. Disabled if
  `CLOCK_MONOTONIC` is unavailable, because guessing expiry could let two requests drive the camera
  at once. Set to 0 to opt out.
- Clock is injectable (`stage2_camera_set_clock`) so the lease is tested deterministically, no sleeps.

`container/stage2_loader.c`: the refusal line now also prints `tid`, `owner_tid`, `depth`, `held_ms`
and `stolen`, so a self-deadlock and a contention refusal are distinguishable in one glance.

## Tests

`container/test_stage2_policy.c` adds four cases, each mapped to one defect:
`test_reentrancy`, `test_reset_clears_a_leaked_claim`, `test_lease_expires_a_leaked_claim`,
`test_idle_admission_is_immediate`.

Mutation-checked -- removing each fix individually makes the suite fail:

| mutation | result |
|---|---|
| reentrancy early-return removed | `Assertion '0 && "preview must never wait..."' failed` (exit 134) |
| reset stops clearing the claim | `Assertion '!busy && !owner_tid && !owner_site' failed` (exit 134) |
| lease comparison never expires | `Assertion 'stage2_camera_claim(...) == 0' failed` (exit 134) |
| all fixes present | exit 0 |

Baseline at HEAD (before the fix) was green, so these are new failures caught by new tests, not a
pre-existing break.

Offline gate: `./tests/run_prerelease_gate.sh` -> **17 passed, 0 failed, 2 skipped**
(container harness 34, python suite 1016). Offline-qualified only; device gates are separate.

## Not yet proven

The exact native path that leaks the key (which of the nine `waitCameraIdle` callers returns without
`setCameraStatus(0)`, or on which thread) is not identified. The fix makes the wedge self-healing
rather than depending on that answer, and the new `tid=`/`owner_tid=`/`depth=` fields exist so the
next capture pins it down.

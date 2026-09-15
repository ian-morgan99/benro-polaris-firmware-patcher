# Pentax capture stability: causal test and experiment plan

## Purpose

This programme is intended to find **why the Pentax/Polaris camera path becomes unhealthy in the first place**, not merely make recovery from stale sessions more reliable.

Primary field umbrella: #82. Related evidence includes #36, #55, #57, #61, #70, #73, #77, #78, #80 and libgphoto2 issue #73.

Run the first diagnostic campaign **below OpenPolaris**, through the real Polaris `pgphoto -> staged libgphoto2 -> Pentax` path. OpenPolaris is an eventual end-to-end qualification layer, but adds UI/protocol/network/preview variables that make first-cause isolation harder.

A desktop/direct `gphoto2` path is useful as a control, not as the principal test path.

## Core rule

Do not infer camera completion from shutter duration alone.

Pentax capture duration depends on mode and camera-side work. Examples that must be measured rather than treated as timeout constants:

- normal capture: shutter + readout/processing;
- long-exposure noise reduction: approximately exposure + dark exposure + processing;
- Pixel Shift: multiple physical sensor exposures plus camera processing;
- Pixel Shift output semantics may consolidate physical exposures into fewer transfer candidates, e.g. DNG + JPEG;
- combinations such as Pixel Shift + NR must be observed on hardware rather than predicted by multiplying constants;
- Bulb/astro captures can legitimately last many minutes.

The driver must distinguish:

1. physical exposure sequence;
2. camera busy/processing interval;
3. resulting file/candidate set;
4. tether transfer/reconciliation lifecycle.

Requested mode and shutter duration establish **expectations**, not authoritative completion signals. Actual Pentax state/conditions plus transport health determine whether the operation is alive.

## Capture state model

Use an explicit lifecycle conceptually equivalent to:

```
READY
  -> REQUESTED
  -> CAMERA_ACTIVE
       -> EXPOSING / internal multi-exposure work
       -> DARK_FRAME? / other camera-side work
       -> PROCESSING / READOUT
  -> CANDIDATE_DISCOVERY
  -> TRANSFER
  -> RECONCILE
  -> READY
```

Do not hard-code `PixelShift = 4T` or `NR = 2T` as failure deadlines. They are useful hypotheses for experiments only.

A legitimate long-running state must not be declared dead simply because a fixed stopwatch expired. Conversely, genuine USB/PTP/process failure must not be hidden by an unlimited wait.

Separate three clocks/signals:

- **operation expectation**: requested shutter + mode informs plausible duration;
- **post-exposure/readout expectation**: starts only when exposure should have completed and measures candidate/processing progress;
- **transport/process health**: actual USB/PTP I/O failure, detach/re-enumeration, process exit/deadlock, impossible response, etc.

## Instrumentation required

Every test should produce a monotonic, machine-readable event trace containing where available:

- test/run ID;
- requested shutter duration;
- exposure/capture mode;
- image format;
- NR setting;
- Pixel Shift setting;
- command name/id and start/end;
- Pentax condition/state transitions;
- PTP/session identifier or session-open observation;
- candidate count and descriptors (format, quality, image size, filename/handle where available);
- first/last candidate appearance;
- transfer start/end/result;
- candidate reconciliation start/end/result;
- camera READY indication;
- `pgphoto` PID and restart/exit/signal events;
- USB VID:PID, bus/device/topology fingerprint;
- preview/config/focus/status request start/end;
- watchdog/reset/supervisor actions;
- 8080/preview health where relevant.

Keep paired Mlog + Clog for field correlation.

The important timestamp is the **first abnormal event**, not merely the later stale-session/reset symptom.

## Baseline characterisation matrix

Start cheaply, then increase duration.

### Normal capture

JPEG and DNG+JPEG where supported:

- 1 s
- 30 s
- 90 s
- 120 s
- 300 s

### Long-exposure NR

Compare OFF and ON at practical durations:

- 1 s
- 30 s
- 90 s
- 120 s
- 300 s

Measure actual camera-side states during the dark frame and processing. Do not assume the host can see each internal phase distinctly.

### Pixel Shift

Test JPEG and DNG+JPEG starting at 1 s then 30 s. Measure:

- actual elapsed camera-busy duration;
- visible Pentax/PTP conditions;
- candidate count;
- candidate descriptors;
- whether four physical shifted exposures are consolidated into one/two output objects or represented differently.

Do not infer candidate count from physical exposure count.

### Pixel Shift + NR

Where the body/settings permit it, start at 1 s then 30 s. Observe actual behaviour rather than assuming multiplication semantics.

### Bulb / manual long exposure

- 120 s
- 300 s
- longer only when needed to establish behaviour.

### Consecutive-shot requirement

For every important mode, perform at least two consecutive captures without reconnect/restart. A first capture that saves successfully is not a pass if it leaves state that blocks the next shutter.

## Adversarial experiments

Use A/B/A where possible: known-good baseline -> one stressor -> baseline. Change one variable at a time.

### E1: timer-boundary sweep

Discover all capture/watchdog/retry timeouts. Sweep immediately below/at/above each threshold. For the known 100 s capture-timeout concern, use approximately:

```
95 99 100 101 105 seconds
```

Repeat for normal, NR, Pixel Shift and Bulb as appropriate. A sharp failure cliff around a software constant is high-value causal evidence.

### E2: foreign-command injection by phase

Inject exactly one otherwise-valid command during controlled lifecycle phases:

- EXPOSING;
- NR/internal dark-frame period;
- Pixel Shift internal work;
- PROCESSING/READOUT;
- TRANSFER;
- RECONCILE.

Try independently:

- preview frame;
- config read;
- ISO/shutter read;
- focus request;
- status request.

Then repeat using normal polling cadence. Determine which commands are safe and whether pgphoto/libgphoto2 actually serialises camera ownership.

### E3: preview race sweep

Preview OFF is control. Then enable progressively increasing preview cadence. Start capture:

- immediately before preview request;
- while preview request is outstanding;
- immediately after preview response;
- near exposure completion/readout.

Look specifically for NoUpdateImage (`0xa008`), restore errors, Wi-Fi/8080 degradation and session contamination.

### E4: back-to-back capture spacing

Run identical captures with inter-shot delays:

```
10 s, 5 s, 2 s, 1 s, 0 s
```

Also issue the next shutter as soon as the first host API call reports completion. Run JPEG and DNG+JPEG.

This tests whether host completion precedes true Pentax candidate reconciliation/READY.

### E5: candidate lifecycle permutations

For multi-output captures, enumerate descriptors first. Safely test:

- transfer JPEG only;
- transfer both outputs;
- delayed transfer;
- query without transfer;
- retain/delete according to intended ownership policy.

Do not destroy a user's DNG for convenience. The intended product behaviour is to preserve full DNG on camera SD while transferring the JPEG to Polaris where appropriate.

Determine exactly which candidate handling leaves `GetAllConditions`/capture state contaminated for the next shutter.

### E6: long-exposure completion boundary

For 120/300 s exposures, inject one status/config/preview request:

- shortly before expected exposure end;
- at expected end;
- during post-exposure processing/readout.

Repeat with NR ON. The transition out of exposure may be more fragile than the exposure itself.

### E7: cancellation/abort semantics

Where safely supported, cancel/abort at early/mid/late exposure and during processing. Then inspect conditions and attempt a clean next capture.

Characterise camera-native cancellation before using process kill as a substitute.

### E8: pgphoto process interruption

After clean non-destructive baselines, deliberately stop/restart pgphoto separately during:

- READY;
- EXPOSING;
- PROCESSING;
- TRANSFER;
- RECONCILE.

Observe camera-side state before reconnection and what a fresh process inherits. This identifies when process replacement is a valid recovery boundary.

### E9: USB disruption matrix

Separately test camera disconnect/reconnect, camera power cycle and USB compatibility toggle at READY and selected non-READY phases.

Record whether VID:PID remains the same, bus/device changes, and whether the existing USB supervisor notices the transition. Distinguish physical USB disappearance from in-place PTP/session contamination.

### E10: camera-side state changes

With a session open, change settings that host code may cache, where practical:

- image format;
- NR;
- Pixel Shift;
- exposure mode.

Capture without host reinitialisation. Look for stale format/config assumptions, including `camera format no include jpg`.

### E11: resource/soak trend

Run 100+ short captures plus a smaller long-exposure series. Record per-shot:

- pgphoto RSS;
- file descriptor count;
- thread count;
- USB handles if observable;
- candidate state;
- per-shot latency;
- Wi-Fi/8080 health;
- restart count.

Analyse trend against shot number. This separates cumulative leaks/exhaustion from isolated races.

### E12: session-history matrix

Compare:

- fresh Polaris + fresh camera;
- fresh pgphoto only;
- camera reconnect without pgphoto restart;
- pgphoto restart while camera remains attached;
- preview previously used vs never used;
- previous failed capture vs previous clean capture.

Determine the minimum history required to produce `session already open ... observing camera state` and whether that message is benign or correlated with failure.

### E13: overlapping shutter requests

Issue a second capture request while the first is definitely active, then separately during processing/reconciliation.

Correct design behaviour is deterministic reject/queue without disturbing active session ownership.

### E14: upper-layer/network isolation

Repeat selected failures with no Benro Connect/OpenPolaris and no preview consumer, then add one consumer. Establish whether the initiating failure is intrinsic to pgphoto/PTP or induced by upper-layer/network/preview traffic.

### E15: direct libgphoto2 control

For signatures reproducible on Polaris, run the closest equivalent against the same K-3 III using direct libgphoto2/gphoto2 where possible and the same library SHA/settings.

If direct survives and embedded fails, ownership moves toward pgphoto/runtime/integration rather than the camera/Pentax driver itself.

## Concurrency invariant

There must be one deterministic owner of the camera command lifecycle. During a capture operation, no unrelated command may enter an unsafe Pentax/PTP state simply because a UI poll, preview loop or watchdog fired.

The tests should establish an allow/reject/queue policy for every command class in every capture phase. Do not delegate this decision to an LLM or heuristic runtime controller.

## Recovery contract

Recovery remains necessary, but is secondary to eliminating initiating failures.

A genuine session reset should conceptually:

1. stop preview and prevent new commands;
2. never abort a known legitimate long exposure merely because time elapsed;
3. after genuine failure/cancellation, boundedly reconcile only candidates positively associated with the initiated exposure;
4. close/exit PTP session where possible;
5. release camera/libusb resources;
6. clear cached abilities, explicit port/bus address and Pentax live-view/candidate/session state;
7. rescan current USB inventory;
8. create a fresh Camera/PTP lifecycle;
9. reapply model-specific setup;
10. resume control only after READY is proven.

If clean in-process teardown cannot be proven, prefer a fresh pgphoto process over pretending the old object is clean. Full Polaris reboot is the final fallback, not normal recovery.

## Failure fingerprint output

Every failure should be represented as a row/object with at least:

| Field | Meaning |
|---|---|
| experiment | E1-E15 + parameters |
| run_id | unique repeat identifier |
| first_abnormal_ts | monotonic timestamp |
| first_abnormal_event | first divergence from known-good lifecycle |
| camera_state | Pentax/PTP condition at divergence |
| active_command | command in flight |
| candidate_state | count/descriptors/ownership |
| pgphoto_state | PID/process/thread/restart information |
| usb_state | identity/topology/presence |
| later_symptom | stale session, 0xa008, -1005, disconnect, etc. |
| recovery_required | none/session reset/process restart/USB/power/Polaris reboot |
| reproducibility | failures/runs |

Cluster failures by **first abnormal event**, not by eventual symptom.

A later `session already open`, `disconnect`, `0xa008`, `-1005` or reset requirement is aftermath unless it can be demonstrated to be the first divergence.

## Initial priority

1. E4 back-to-back/candidate lifecycle — strong existing evidence.
2. E1 timeout boundary — fixed 100 s capture timeout is architecturally suspicious for astro.
3. E2/E3 command concurrency and preview races.
4. E6 long-exposure completion/readout boundary.
5. E12 session-history dependency.
6. E11 soak/resource trend.
7. E7-E9 destructive fault injection only after normal lifecycle is characterised.

## Exit criteria

The investigation succeeds when vague "stability poor" behaviour has been reduced to a small number of reproducible failure recipes, each with:

- a known first incorrect transition;
- a minimal reproducer;
- layer ownership;
- a deterministic fix;
- a regression test;
- proof that long legitimate Pentax operations are not mistaken for failure;
- proof that a genuine failure returns to fresh READY without requiring Polaris reboot.

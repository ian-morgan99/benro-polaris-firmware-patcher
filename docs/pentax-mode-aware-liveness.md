# Pentax mode-aware liveness semantics

## Problem

A requested shutter duration is insufficient to decide whether a Pentax capture has timed out.

Camera-side modes can legitimately keep the body busy after, or across multiple instances of, the nominal shutter interval. Examples include long-exposure dark-frame noise reduction, Pixel Shift processing, RAW/JPEG production and Bulb/astro use.

## Rule

Use mode and requested shutter duration to establish an **expected operation envelope**, never as the sole completion/failure signal.

A capture remains potentially healthy while:

- the camera/transport remains present;
- the process/session is responsive according to safe observations;
- Pentax conditions indicate legitimate camera-side activity or have not yet produced a terminal contradiction;
- no independently-proven process/USB/PTP failure has occurred.

## Do not conflate counts

These are independent:

```
physical sensor exposures != camera processing phases != output files != tether candidates
```

For Pixel Shift, multiple physical shifted exposures may be consolidated by the camera into a DNG and JPEG or another observed output set. The host must enumerate actual candidates after camera-side work rather than predicting candidate count from the mode.

## Suggested data model

```text
CaptureContext
  requested_shutter
  exposure_mode
  image_format
  nr_mode
  pixel_shift_mode
  started_at
  expected_operation_envelope   # diagnostic/expectation, not authority
  lifecycle_phase               # authoritative host state machine
  observed_camera_condition
  transport_health
  candidates[]                  # discovered, never guessed
```

## Timeout semantics

Replace a single `capture_timeout` concept at the orchestration level with distinct concerns:

1. **Expected operation envelope** — mode-aware; useful for diagnostics and deciding when additional safe observation is warranted.
2. **Progress/readout bounds** — phase-specific and only start when that phase is actually entered/expected.
3. **Transport/process failure bounds** — independent evidence that USB/PTP/process has failed.

Crossing an expected duration should generate telemetry such as `operation_exceeded_expectation`, not automatically `session_dead`.

## Concurrency

During camera-owned long operations, unsafe preview/config/focus/status commands must be rejected or queued deterministically. The E2/E3 experiment set determines the safe command matrix.

## Unknown modes

Unknown/uncharacterised modes should fail toward **patient, bounded observation**, not premature teardown. Observation still requires global safeguards against an actually dead process/transport; it is not an infinite wait.

## Validation

Hardware measurements from the K-3 III become the initial empirical model. Validate the resulting semantics separately on K-1 II before declaring them generic Pentax behaviour.

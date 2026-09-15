# Pentax stability implementation notes

## Instrument source transitions, not just wrappers

The Python/shell trace tools are scaffolding. Once source locations are known, emit structured events directly around the real pgphoto/libgphoto2 transitions so a wrapper cannot miss races or alter timing materially.

Useful event names:

```
capture_request
capture_enter
camera_condition
operation_exceeded_expectation
candidate_discovered
candidate_selected
candidate_transfer_start
candidate_transfer_end
candidate_reconcile_start
candidate_reconcile_end
camera_ready
preview_request
config_request
command_rejected_busy
ptp_error
usb_change
pgphoto_restart
first_abnormal
```

## Capture identity

Where possible allocate a host capture/run identifier at the moment a shutter request is accepted and carry it through candidate discovery/reconciliation. Candidate ownership should be proven by camera metadata/conditions and capture context, not merely by 'the next file we saw'.

## Serialization

Create one deterministic command arbitration point. Tests should first reveal the safe command matrix; implementation should then encode it explicitly. At minimum, a second shutter during an active capture must not create a second concurrent ownership path.

## Expectation vs failure

If a mode-aware expected duration is exceeded while transport/process remain healthy, log it. Do not silently convert that telemetry event into session teardown.

## Process restart

Record old/new pgphoto PID and reason. A restart that follows an earlier camera-state divergence is recovery; a restart/watchdog firing first may itself be causal and must be visible in the trace.

## Candidate reconciliation

Never solve a stale-candidate bug by blindly deleting every remaining object. Multi-output Pentax modes and DNG+JPEG require explicit ownership and preservation semantics.

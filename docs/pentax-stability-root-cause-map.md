# Pentax stability causal map

This map prevents the project from treating recovery symptoms as root causes.

## Candidate initiating causes

### A. Capture finalisation / candidate ownership
Evidence family: consecutive capture fails after apparently successful prior capture; multi-output capture leaves a transfer candidate pending.

Questions:
- Does host completion occur before all exposure-owned candidates are reconciled?
- Is DNG+JPEG/Pixel Shift output classification correct?
- Is a retained camera-side DNG being confused with a pending tether candidate?

Primary experiments: E4, E5.

### B. Legitimate long camera operation mistaken for failure
Evidence family: fixed capture timeout; astro exposure, NR and Pixel Shift can keep the camera legitimately occupied well beyond simple shutter duration.

Questions:
- Which timers/watchdogs fire while camera is still legitimately active?
- What Pentax conditions are observable during exposure/dark/processing?
- Is a timeout itself causing the first conflicting command/reset?

Primary experiments: E1, E6.

### C. Command concurrency / unsafe polling
Evidence family: preview NoUpdateImage loops, focus/preview interactions, app instability.

Questions:
- Can preview/config/focus/status enter while capture owns the session?
- Are commands serialized in one deterministic owner/state machine?
- Which exact phase/command pair causes first divergence?

Primary experiments: E2, E3, E13.

### D. pgphoto/process/runtime failure
Questions:
- Does pgphoto exit, deadlock, leak resources or get restarted before camera state becomes stale?
- Does process replacement clear state that in-process reset cannot?

Primary experiments: E8, E11, E12.

### E. Physical USB/transport transition
Evidence family: real detach/reattach/body swap and separate hub-flapping reports.

Questions:
- Did USB actually disappear/re-enumerate before session failure?
- Does the supervisor observe the relevant transition?
- Does PTP become unusable while USB fingerprint remains unchanged?

Primary experiments: E9, E12.

### F. Upper-layer/network/preview pressure
Evidence family: preview traffic can correlate with Wi-Fi/8080 degradation.

Questions:
- Does failure reproduce with no OpenPolaris/Benro Connect/preview consumer?
- Does adding preview/network traffic introduce the first abnormal event?

Primary experiments: E3, E14.

### G. Pentax driver vs embedded integration
Questions:
- Does the same camera/settings/libgphoto2 SHA reproduce via direct gphoto2?
- If not, what embedded pgphoto/runtime action differs first?

Primary experiment: E15.

## Common aftermath — do not automatically call these root causes

- `session already open ... observing camera state`;
- stale explicit `usb:BUS,DEVICE` selection;
- `0xa008` / NoUpdateImage;
- `-1005` app error;
- generic disconnect indication;
- 8080 boundary with no image payload;
- need for camera/USB/Polaris reset.

Any of these may become a root cause only if trace evidence shows it is the **first divergence** from a known-good run.

## Desired end state

Each real failure family should have a deterministic chain:

```
trigger -> first incorrect transition -> contaminated state -> visible symptom -> recovery
```

Fix and regression-test as far left in that chain as possible. Recovery remains a final safety net.

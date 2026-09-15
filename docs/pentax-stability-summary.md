# Pentax stability investigation summary

We are no longer treating "stale camera session" as the problem statement. It is often an aftermath state.

Current causal areas under test:

- incomplete capture/candidate finalisation poisoning the next shutter;
- fixed/mode-unaware timeout or watchdog activity during legitimate long Pentax operations;
- preview/config/focus/status command races with capture;
- pgphoto process/runtime lifecycle defects;
- stale in-process session/port state after genuine failure;
- true physical USB transitions;
- upper-layer preview/network pressure;
- Pentax libgphoto2 driver behaviour vs embedded integration differences.

Pentax-specific requirement: shutter duration is only part of expected operation time. Long-exposure NR, Pixel Shift, processing and Bulb must be accounted for, but mode-derived timing is not an authoritative completion signal. Physical exposures, processing phases and output candidates are independent quantities.

The campaign therefore measures hardware behaviour, deliberately stresses lifecycle boundaries, records the first abnormal transition and fixes failures as far left in the causal chain as possible. Recovery remains the final safety net.

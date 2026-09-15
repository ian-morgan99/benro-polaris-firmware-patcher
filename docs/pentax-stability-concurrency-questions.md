# Camera-command concurrency audit

Before changing locking/arbitration, locate every path that can issue camera/PTP work:

- shutter/capture;
- preview get-frame and restore;
- focus/manual focus/autofocus;
- config get/set;
- exposure/ISO/aperture/shutter reads;
- status/health checks;
- watchdog/reset probes;
- candidate transfer/delete/reconcile;
- init/reinit/session open/close.

For each path identify thread/process, lock/serialization mechanism, whether it can overlap command 264/capture, and what happens when camera reports busy/NoUpdateImage.

E2/E3 then validates the static source map against hardware. The desired result is one explicit deterministic ownership policy rather than accidental serialization through timing.

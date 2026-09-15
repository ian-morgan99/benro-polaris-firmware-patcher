# Observation vs control

Instrumentation should observe the production-relevant camera path without becoming a second controller.

The trace recorder therefore does not itself decide when to reset, retry, delete candidates or issue camera commands. Existing deterministic control code remains authoritative until evidence justifies a source change.

This separation reduces the chance that the test harness creates or hides the race it is trying to measure.

# What "fresh READY" means

Recovery is successful only when READY is proven, not when an init function merely returned success.

A fresh READY should imply, as applicable:

- current camera identity/port corresponds to the physically present body;
- no stale explicit removed-device port is reused;
- session ownership is known;
- no previous capture candidate blocks the next operation;
- preview/capture state is internally consistent;
- pgphoto process/session is responsive;
- next deterministic shutter/control operation succeeds.

The exact proof should be refined from hardware observations without using an unsafe probe during active capture.

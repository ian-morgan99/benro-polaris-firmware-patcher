# Pentax capture context concept

A useful deterministic implementation direction is one explicit `CaptureContext` per accepted shutter request.

It should carry, at minimum:

- capture/run ID;
- requested shutter;
- exposure/capture mode;
- format;
- NR/Pixel Shift settings as observed/requested;
- lifecycle phase;
- start/progress timestamps;
- expected-operation metadata (non-authoritative);
- actual camera conditions observed;
- discovered candidate descriptors and ownership state;
- transfer/reconciliation status;
- terminal READY/FAILED result.

The context owns the camera operation until terminal reconciliation. A second shutter cannot create another active context concurrently.

This is a design direction to validate against existing pgphoto/libgphoto2 architecture, not an instruction to duplicate state already represented correctly elsewhere.

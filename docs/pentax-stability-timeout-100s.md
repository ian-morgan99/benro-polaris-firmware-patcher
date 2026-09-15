# The 100-second capture timeout

Relevant libgphoto2 source currently contains `USB_TIMEOUT_CAPTURE 100000` (100 seconds). This is important because legitimate Pentax astro operations can exceed 100 seconds.

However, the constant's existence does **not** prove it caused Steve's field disconnect or any specific crash. E1 plus source-path audit must establish:

- which operation uses the timeout in our path;
- what happens on expiry;
- whether camera-side work can legitimately outlive it;
- whether expiry is the first divergence in a reproducible failure.

Treat this as a high-priority falsifiable hypothesis, not a concluded root cause.

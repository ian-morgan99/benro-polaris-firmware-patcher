# Long-exposure noise-reduction stability notes

Working expectation for hardware tests: Pentax long-exposure NR may take a dark exposure of roughly the same duration as the light exposure, followed by processing. Thus requested shutter `T` can correspond to roughly `2T + processing` of legitimate camera occupation.

This is not an authoritative timeout formula.

The important experiment is to determine what the K-3 III exposes through the existing PTP/libgphoto2 path during the dark/processing interval and whether any pgphoto/libgphoto2/watchdog/preview action mistakes that interval for a dead session.

A five-minute requested exposure can therefore plausibly remain legitimately busy for ten-plus minutes. The system must not destroy the session merely because a legacy fixed timeout expired.

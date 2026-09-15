# Pentax timeout/watchdog audit questions

For every timer found in capture/preview/session/recovery code, answer:

- Is it an I/O transaction timeout, operation expectation, retry delay, watchdog deadline or recovery trigger?
- What exact event starts it?
- What exact code executes when it expires?
- Can it expire while a legitimate long Pentax operation is still active?
- Does expiry issue another PTP command, close/reset the session, restart pgphoto or merely return an error?
- Is it mode-aware?
- Is it reset/extended by actual progress?
- Can it race another timer?
- Is its value observable in logs/tests?
- What hardware experiment discriminates whether it is causal?

Do not mechanically increase values. Classify semantics first.

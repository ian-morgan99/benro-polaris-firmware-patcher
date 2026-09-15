# Preserve evidence before recovery

When a test enters a bad state, capture the current structured trace, Mlog/Clog tail, pgphoto PID/process state, USB fingerprint and candidate/session observations **before** applying reset/restart/power recovery where safe.

Recovery can erase the evidence that distinguishes initiating cause from aftermath. Automate this snapshot step where practical.

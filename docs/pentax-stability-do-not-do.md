# Pentax stability anti-patterns

Do **not**:

- solve the problem by globally increasing one timeout;
- assume `T` means capture completes at `T`;
- assume Pixel Shift physical exposure count equals output/candidate count;
- delete all remaining camera candidates to force READY;
- allow preview/watchdog polling to bypass camera ownership rules;
- call every `ttyUSB` failure a camera USB failure;
- call every `session already open` message the root cause;
- treat one successful shot as proof of cleanup;
- add OpenPolaris to first-cause tests before the lower path is characterised;
- optimise recovery before capturing the first abnormal transition;
- put an LLM in the runtime control loop for session ownership, timeout decisions or candidate cleanup.

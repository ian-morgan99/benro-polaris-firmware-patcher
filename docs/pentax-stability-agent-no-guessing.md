# No-guessing rule

If an agent cannot observe whether the camera is in NR dark-frame, Pixel Shift processing or another internal phase, record the externally visible state as observed and the internal interpretation as unknown/inferred.

Do not manufacture a precise state machine from mode names. The purpose of the physical camera is to discover what is actually observable and design safe host behaviour around that evidence.

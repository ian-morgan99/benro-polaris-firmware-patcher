# Deterministic stability test oracle

A hardware test should not require an agent to subjectively decide whether the camera "looks stuck".

Where observable, evaluate explicit invariants:

- expected command accepted/rejected/queued outcome;
- ordered lifecycle events;
- no unexpected process restart/USB change;
- candidate descriptors/ownership reach terminal state;
- READY reached without forbidden recovery;
- next shutter succeeds;
- resource bounds remain within measured baseline.

Agent interpretation is used to investigate a failed oracle and propose the next discriminator, not to replace the oracle itself.

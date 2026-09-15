# Pentax mode observation protocol

For each uncharacterised mode (NR, Pixel Shift, combinations):

1. Start from fresh known-good READY.
2. Record full camera settings and format.
3. Use a short shutter first.
4. Start structured trace before shutter request.
5. Observe only through already-proven-safe mechanisms; do not add preview/config polling simply to obtain more data.
6. Record physical shutter/activity observations if the agent/test rig can establish them without interfering.
7. Record every visible Pentax/PTP condition transition.
8. Wait for camera-side terminal state without applying a mode-derived hard timeout.
9. Enumerate candidate descriptors/count.
10. Apply intended transfer/retention policy.
11. Prove reconciliation and next shutter.
12. Repeat before increasing shutter duration.

Populate `tests/pentax_mode_observations.csv` with measured facts. Leave unknown cells unknown rather than inferring them.

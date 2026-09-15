# Pentax stability data-safety rules

Candidate cleanup experiments must not trade stability for lost photographs.

- Treat DNG/RAW as user data unless a dedicated disposable test setup explicitly says otherwise.
- Enumerate and classify candidate metadata before transfer/delete decisions.
- Distinguish a camera-side file intentionally retained on SD from a tether-transfer candidate that must be acknowledged/reconciled.
- Never implement "delete all remaining candidates" as a generic stale-session fix.
- Record candidate descriptors and ownership decisions in the structured trace.
- If ownership cannot be proven, stop and preserve the object/state for analysis rather than guessing.

The target DNG+JPEG product behaviour is: preserve the full DNG on camera storage while transferring the required JPEG to Polaris, with the Pentax capture state still fully reconciled for the next shutter.

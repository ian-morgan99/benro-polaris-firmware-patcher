# Pentax capture phase model

See `tests/pentax_stability_phase_model.json`.

The phase model is deliberately **conceptual**. K-3 III hardware may not expose a distinct PTP condition for every internal operation such as NR dark-frame or individual Pixel Shift sub-exposures. Tests must record what the camera actually exposes rather than fabricate phase certainty.

The model's primary purpose is command ownership and trace correlation: from accepted shutter through candidate reconciliation, the capture lifecycle remains owned until READY or FAILED/recovery terminal state is proven.

# Pixel Shift stability notes

Pixel Shift is a key reason the host must not equate shutter duration, physical exposure count and output candidate count.

Working expectation for testing: the camera performs multiple shifted sensor exposures and then significant camera-side processing. With DNG+JPEG selected, the externally visible result may be consolidated to two outputs/candidates rather than exposing each physical exposure independently. It may also expose other semantics depending on body/settings.

Therefore:

- do not code `n=4` or `n=5` as a PTP candidate expectation;
- measure actual K-3 III conditions, busy duration and descriptors;
- treat `4*T + processing` only as a rough diagnostic expectation if hardware confirms four component exposures;
- enumerate candidates after camera-side work;
- preserve DNG according to data-safety policy;
- prove the next shutter succeeds.

Record actual observations in `tests/pentax_mode_observations.csv` rather than converting this note into an assumption.

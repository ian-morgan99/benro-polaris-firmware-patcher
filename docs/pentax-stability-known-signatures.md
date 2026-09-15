# Known Pentax/Polaris stability signatures

See `tests/pentax_stability_known_signatures.csv`.

The register deliberately separates **observed signature** from **causal status**. This is important because the same later symptom can result from several initiating defects.

In particular, do not equate `CheckTtyUsbTask` failure with the Pentax camera USB endpoint without correlated evidence, and do not treat `session already open` as root cause merely because it appears after a failed lifecycle.

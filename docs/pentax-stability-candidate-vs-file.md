# Terminology: exposure vs file vs transfer candidate

Use these terms precisely:

- **physical exposure** — a sensor integration performed by the camera;
- **camera processing phase** — internal work such as dark-frame processing/Pixel Shift combination/readout;
- **file/output** — an image object the camera ultimately stores or exposes;
- **transfer candidate** — an object/state the tether/PTP capture lifecycle expects the host to resolve;
- **transferred object** — data actually copied to Polaris;
- **retained object** — intentionally left on camera storage, e.g. full DNG according to product policy.

Counts can differ. In particular, four Pixel Shift physical exposures do not imply four transfer candidates, and DNG+JPEG may expose two outputs while only the JPEG is intended for Polaris transfer.

# Independent sky simulator

`polaris-skysim-independent.c` renders a JPEG directly from the Gaia-derived
`POLCAT01` catalogue. It is separate from the existing Astrometry.net-backed
`polaris-skysim`, allowing both solvers to be tested against a scene generated
without Astrometry.net indexes. The old Python/Pillow renderer remains a host
reference only; the build now packages the native renderer instead.

The native renderer is buildable for host and ARM. It does not yet model camera
response, saturation, vignetting, or optical distortion. Those are later
validation stages.

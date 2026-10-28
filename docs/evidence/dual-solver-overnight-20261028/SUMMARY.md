# Dual-solver same-frame smoke — 2026-10-28

## Result

PASS for the paired interface smoke. Both solver front ends solved the same
synthetic JPEG and the same extracted star list from the host-built binaries.
The independent leg used the deliberately paired regional catalogue generated
from that observation, so its zero residual is an interface/matching result,
not an independent all-sky accuracy result.

## Command

```sh
bash container/astro/compare-solvers.sh \
  --astro-dir out/dual-solver-host-tuned2/astro \
  --index out/.astro-src-cache/astrometry.net-0.98/bench/index-4215.fits \
  --outdir out/dual-solver-overnight-20261028 --timeout 45
```

The run used RA 84.5°, Dec -2.7°, roll 17°, 250 mm, 36 mm sensor width and a
4096×3072 frame. The retained result is in the ignored working artefact
`out/dual-solver-overnight-20261028/comparison.json`.

## Measurements

| solver | result | position | scale | matches/residual | measured solve time |
|---|---|---|---|---|---:|
| Astrometry.net | solved | RA 84.499322°, Dec -2.701854° | 7.250751 arcsec/px | 19 / log-odds 205.332 | 0.023 s |
| native independent C | solved | RA 84.500000°, Dec -2.700000° | 7.251497 arcsec/px | 19 / RMS 0.000 px | 0.03 s wall-clock |

The Astrometry.net result is the only fair roll measurement in this harness;
the paired catalogue is derived from the rendered pixel positions and reports
zero rotation by construction. The two scales differ by about 0.01%. On this
single host smoke Astrometry.net was marginally faster, while the native result
was exact against its paired catalogue. This does not select a production
default: real Gaia all-sky, false-solve, ARM-resource, device-capture and
physical-night evidence remain required.

## Qualification boundary

This is host-only. It did not install or flash firmware, contact a Polaris,
write a camera card, command a motor, or qualify K-3 III behaviour.


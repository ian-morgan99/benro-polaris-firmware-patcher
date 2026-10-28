# Dual plate-solver operation

This document is subordinate to the [master plan](PLATE-SOLVING-MASTER-PLAN.md).
The comparison harness is an offline research tool; selecting the independent
solver on a device does not mean it is production-qualified.

The Astrometry.net-based solver remains the default:

```sh
SOLVER_BIN=polaris-solve
```

The on-device scripts now select the solver by executable name. An alternate
solver can be installed beside it as:

```text
/app/astro/polaris-solve-independent
```

and selected without changing the firmware or deleting the baseline:

```sh
SOLVER_BIN=polaris-solve-independent sh /app/astro/polaris-align.sh frame.jpg 400
```

The same selector is used by `polaris-align.sh`, `polaris-autoalign.sh`, and
`polaris-guide.sh`. The simulator accepts the alternate explicitly:

```sh
python3 sim-verify.py --camera \
  --solve ./polaris-solve \
  --solver-independent ./polaris-solve-independent \
  --index /path/to/index.fits
```

`--solver-independent` overrides `--solve` for that run. The default remains
the Astrometry.net solver, so installing the selector changes no existing
behaviour until it is explicitly chosen.

The source tree now contains the native-C independent solver and native-C sky
renderer. Build output is intentionally not committed. The two methods can be
compared with:

```sh
container/astro/compare-solvers.sh \
  --astro-dir out/dual-solver-host/astro \
  --index out/.astro-src-cache/astrometry.net-0.98/bench/index-4215.fits \
  --outdir out/dual-solver-test
```

The harness uses one rendered JPEG and one extracted star list for both solver
front ends. Its first independent catalogue is deliberately synthetic and
derived from the known test scene, so the result proves the integration and
matching contract only. It does not prove an all-sky, catalogue-independent
solve. The next required comparison is a real Gaia regional catalogue, then an
indexed all-sky catalogue.

The native solver's triangle search uses the brightest 15 observations as
anchors by default and verifies against all accepted observations. The bound is
adjustable for experiments with `--anchor-stars N`; it is a performance knob,
not a substitute for the false-solve and sparse-field tests.

The Astrometry.net solver remains the only production default until the
independent path passes the gates in the master plan.

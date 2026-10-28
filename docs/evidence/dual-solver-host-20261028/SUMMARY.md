# Dual solver host comparison — 2026-10-28

> Historical note: this run used the first paired-catalogue generator, whose
> degree/cos(dec) approximation introduced an artificial scale distortion.
> Its independent scale figures must not be used for accuracy comparison.
> The corrected rerun is documented in
> `docs/evidence/dual-solver-tuned-20261028/SUMMARY.md`.

## Result

`HOST-PAIRED`: PASS for the first same-frame plumbing comparison.

One native Astrometry.net-rendered JPEG was extracted once and the same star
list was passed to both solver front ends. Both reported a solve with 19
matches.

This is not a production or all-sky qualification. The independent solver's
`POLCAT01` catalogue was generated from the known test scene so that the two
front ends could be exercised on the same observation. Its rotation output is
not comparable in this tier; a real Gaia catalogue is required for that.

## Ground truth and results

```text
scene centre:       RA 84.5 deg, Dec -2.7 deg
focal length:       250 mm
sensor width:       36 mm
image:              4096 x 3072
Astrometry index:   index-4215.fits, SHA-256 6962f44f1a689a397dbda141fa75189fe25e61388295e53f7929ead098874b3a

Astrometry.net:     solved=true, RA 84.499322, Dec -2.701854
                    scale 7.250751 arcsec/px, matches 19/19
                    solver time 0.020 s

Independent C:      solved=true, RA 84.49999178, Dec -2.70158904
                    scale 7.258873 arcsec/px, matches 19/19
                    RMS 1.851442 px
```

The Astrometry result is within about 7.2 arcsec of the commanded scene centre;
the independent result is within about 5.7 arcsec in Dec and 0.03% in recovered
pixel scale. Those are synthetic host results, not camera pointing accuracy.

## Reproduction

```sh
mkdir -p out/dual-solver-host
docker run --rm -u "$(id -u):$(id -g)" \
  -v "$PWD/container":/opt/patcher:ro \
  -v "$PWD/out/.astro-src-cache":/work/src \
  -v "$PWD/out/dual-solver-host":/work/out \
  --entrypoint /bin/bash polaris-patcher -c \
  'bash /opt/patcher/astro/build_solver.sh host /work/out/astro'

container/astro/compare-solvers.sh \
  --astro-dir out/dual-solver-host/astro \
  --index out/.astro-src-cache/astrometry.net-0.98/bench/index-4215.fits \
  --outdir out/dual-solver-test
```

## Artefact hashes

```text
polaris-solve:              a2a680f153d0c53fec13f46b81ef3df0675e1268f0891a661b22c51acc7d27bb
polaris-solve-independent:  dffb36684a3f9edb9c634d20d0d8083e50935d2eaed276b111e24bd593fbc655
polaris-skysim:             0f5b869ab678b82e3d906be5c411b3fb5760e82300c30338e856e1ef80589237
polaris-skysim-independent: a470ff32b0d28c0a6912c349a0996bc3fb463b281853166a0640fe653ceeec40
scene.jpg:                 61714e145847ed6a8376bbf36d2a164009798ca058344f5b36e4a031093c0c62
scene.stars:               f09cf49f96c95b1aa238e8ab05bc106ca5d627480b5ffb968e267c3b7489ce6f
paired.pcat:               095c9d5cd7e9672f619b4821cff04fc016134295b58165468016da9ff1f6da0c
comparison.json:           3df40b6400af722ba4796e2f87ca13b5213a2d2b1fb959e7d59b0bf2c16b2ba2
```

## Next gate

Repeat the comparison with the real Gaia regional sample, then test wrong
pointing hints, wrong focal lengths, sparse/noisy fields and false catalogue
candidates before considering ARM execution or device selection.

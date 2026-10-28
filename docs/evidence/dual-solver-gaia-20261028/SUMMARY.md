# Real Gaia regional native-solver check

**Date:** 2026-10-28
**Scope:** host-only synthetic JPEG rendered from an independently downloaded
ESA Gaia DR3 regional catalogue. This is catalogue-independence evidence, not
camera or Polaris hardware qualification.

## Input provenance

The catalogue came from the ESA Gaia DR3 TAP service using:

```sql
SELECT TOP 500 source_id,ra,dec,phot_g_mean_mag
FROM gaiadr3.gaia_source
WHERE CONTAINS(POINT('ICRS',ra,dec),
  CIRCLE('ICRS',84.5,-2.7,12))=1
  AND phot_g_mean_mag IS NOT NULL
  AND phot_g_mean_mag <= 10
ORDER BY phot_g_mean_mag
```

It was converted to `POLCAT01` with
`tools/build_independent_catalogue.py`:

| Property | Result |
|---|---|
| Gaia records retrieved | 500 |
| POLCAT01 records | 500 |
| POLCAT01 SHA-256 | `7f9c935e38e24232deb4f0ca6bc6ea23df20178279ac5453ada4e6c18752aac4` |
| Selection | `phot_g_mean_mag <= 10.0` |
| Epoch | 2016.0 |
| Tile | RA 84.5°, Dec -2.7°, 12° cone |

The generated artefacts are retained under the local, ignored
`out/gaia-region-84p5--2p7/` directory; the catalogue is not checked into the
source repository.

## Result

The native C renderer produced a 4096×3072 JPEG at RA 84.5°, Dec -2.7°, roll
17°, focal length 250 mm, 36 mm sensor width, background 7 and noise 0.8.
It contained 102 catalogue stars; the native extractor retained 40.

After the solver changed its fixed regional cap from arbitrary source-ID order
to the brightest stars in the hinted region, the native result was:

```json
{"solved":true,"ra_deg":84.50388325,"dec_deg":-2.69650146,
 "scale_arcsec_per_px":7.249880,"rotation_deg":16.986509,
 "parity":-1,"matched_count":21,"rms_px":1.010746}
```

Against the rendered truth, the centre error is approximately 13.4 arcsec,
scale error approximately -0.0223%, and roll error approximately -0.0135°.
The result passed the production-shaped host gate of at least 12 matches and
RMS no more than 3 px.

## False-solve finding and fix

Before the cap fix, the same image returned a wrong five-match candidate at
RA 81.6288°, Dec -9.7572°, scale 9.6483 arcsec/px, RMS 1.369 px. The gate
correctly rejected it as `no_verified_candidate` when `--min-matches 12` was
applied. This validates why a low residual alone is not enough.

The root cause was catalogue ordering: `POLCAT01` is stable source-ID order,
while the solver's 120-record regional working set was taking the first 120
records rather than the brightest 120. The native solver now selects the
brightest eligible regional records before triangle matching.

## Same-frame Astrometry.net comparison

The first local `index-4215.fits` reference index did not solve this Gaia
rendered field (`nfield=40`, `solved=false`) in 0.007 s. That was an
index-coverage/input-catalogue limitation, not a solver comparison.

The focal-specific Astrometry.net 4100 set selected by
`container/astro/fetch-indexes.sh` (4111–4115, 19.4 MB) did solve the exact
same extracted star list:

```json
{"solved":true,"ra_deg":84.502447,"dec_deg":-2.694254,
 "roll_deg":163.0631,"pixscale_arcsec":7.244961,
 "nmatch":32,"nfield":40,"solve_seconds":0.022}
```

The native C result took 3.79 s wall time and 2.0 MB peak RSS in the same host
run; Astrometry.net took 0.02 s and 9.2 MB peak RSS. The native result had 21
matches and 1.01 px RMS; Astrometry.net reported 32 matches and log-odds
279.335. The RA/Dec and scale estimates are close enough to confirm that the
real Gaia catalogue path is solving the same field, but this is one rendered
frame, one host, and not a device benchmark. Roll values use different parity
conventions and are not compared numerically without normalisation.

## Qualification decision

This advances the native path from synthetic scene-derived catalogue plumbing
to a real Gaia regional catalogue and catches a genuine false-solve failure.
It does **not** prove all-sky blind solving, camera distortion/noise behaviour,
ARM/GLIBC compatibility, or physical Polaris operation. The native solver
remains opt-in and Astrometry.net remains the default.

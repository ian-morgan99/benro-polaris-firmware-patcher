# Gaia prototype sample

The first real catalogue sample was retrieved from the ESA Gaia DR3 TAP
service for a 12-degree cone centred on RA 84.5°, Dec -2.7°:

```sql
SELECT TOP 500 source_id,ra,dec,phot_g_mean_mag
FROM gaiadr3.gaia_source
WHERE CONTAINS(POINT('ICRS',ra,dec),
  CIRCLE('ICRS',84.5,-2.7,12))=1
  AND phot_g_mean_mag IS NOT NULL
  AND phot_g_mean_mag <= 10
ORDER BY phot_g_mean_mag
```

The resulting `POLCAT01` artefact contains 500 records. Its SHA-256 is:

```text
7f9c935e38e24232deb4f0ca6bc6ea23df20178279ac5453ada4e6c18752aac4
```

This is a prototype-region sample, not yet the Polaris package catalogue. It
is retained as a reproducibility reference; the production catalogue still
needs all-sky coverage, documented quality cuts, Gaia acknowledgement, and a
spatial partition suitable for the device memory budget.

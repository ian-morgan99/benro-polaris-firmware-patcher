# Independent catalogue boundary

The prototype solver accepts a deliberately boring text catalogue:

```text
# source_id, ra_deg, dec_deg
gaia-dr3-123,12.345678,-45.678901
```

The catalogue is an input artefact, not part of the solver algorithm. Every
generated catalogue must ship with a manifest containing:

```json
{
  "format": "polaris-independent-catalogue-1",
  "source": "Gaia DR3",
  "release": "DR3",
  "epoch": "2016.0",
  "selection": "documented magnitude and quality cuts",
  "record_count": 0,
  "sha256": "...",
  "builder": "commit or release identifier",
  "licence_notice": "required Gaia acknowledgement"
}
```

No Astrometry.net index, SkySolver `SKYIDX04` file, SkySolver WASM, or copied
implementation is valid input to this solver. The text format is only the
host prototype format; the device format will be versioned after the solver
benchmarks establish the required spatial partition and memory budget.

Pointing is not a required camera input. Focal length is the normal geometry
input and constrains angular scale; RA/Dec is an optional speed hint. The
direct regional matcher returns `blind_search_index_required` without a hint;
the native search front end supplies the required all-sky spatial/triangle
index and remains bounded by an explicit attempt budget. A missing or
incompatible index fails closed rather than guessing a position.

The current Gaia research package uses Gaia DR3 records with
`phot_g_mean_mag <= 10`, epoch 2016.0, 10°×10° spatial tiles, and a separate
triangle-ratio index built from the 15 brightest records per tile. A shipped
package must retain the Gaia acknowledgement, query/selection provenance,
catalogue checksum, tile-manifest checksum, and index checksum together.

The host package builder is `container/astro/build_gaia_package.sh`. Its output
can be carried into an Astro bundle with `build-astro.sh --catalog-package`; the
bundle copies the tile directory, tile manifest, triangle index, and index
manifest under the names expected by the native search front end.

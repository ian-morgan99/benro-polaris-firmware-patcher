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
input and constrains angular scale; RA/Dec is an optional speed hint. A
no-hint solve must use an all-sky spatial/triangle index. The current regional
prototype returns `blind_search_index_required` until that index exists, rather
than treating a missing pointing hint as a solve failure or guessing a
position.

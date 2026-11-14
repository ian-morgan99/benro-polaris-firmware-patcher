# #344 — solver parameter sweep, measured on the head

`tools/bench-solve-params.sh`, run on 192.168.0.1 against the real `/app/sd/astrometry`
indexes (10 files, 44.1 MB) and the #341 frame. `polaris-solve` md5 `161b3d28…`,
`polaris-extract` md5 `0007e8c0…` (the post-hoist build). Blind search, no scale hint —
the same configuration the mount uses for an unaligned frame.

## Star count is the knob that matters, and it is not monotonic

| stars | solve_ms | index | logodds |
|---|---|---|---|
| 50 | **23842** | 4114 | 142.9 |
| 100 | 3434 | 4114 | 55.9 |
| **200** | **1568** | 4117 | 87.8 |
| 300 | 1812 | 4117 | 112.7 |
| 400 | 3456 | 4117 | 137.2 |

Solve time has a minimum near **200 stars**, not at the low end. 50 stars takes 15× longer
than 200 — with too few detections the solver exhausts its candidate quads and falls through
to a much wider search, so starving the field is far more expensive than feeding it extra
stars. This independently supports #341's choice of `max_stars=200`: it is not just "enough
stars", it is close to the fastest point on the curve.

Confidence rises monotonically with star count (55.9 → 137.2 logodds), so 200 is a genuine
speed/quality trade-off rather than a free win: 400 stars costs 2.2× the time for ~50% more
confidence.

## `--depth` is not a usable cost bound

Help text says "stop after the brightest N stars". Measured directly, repeated twice per cell:

| stars | --depth 0 | --depth 3 | --depth 4 | --depth 5 |
|---|---|---|---|---|
| 50 | solved, 23.5 s | **fail**, 0.33 s | **fail**, 2.2 s | **fail**, 6.5 s |
| 200 | solved, 1.63 s | solved, 1.64 s | — | — |
| 400 | solved, 3.47 s | **fail**, 1.03 s | solved, 3.51 s | solved, 3.65 s |

Three things follow, and none of them make `--depth` a knob worth building on:

1. **It is not inert.** `--depth 1` and `--depth 2` return in under 2 ms — the search exits
   immediately instead of searching. So the flag does reach `solver->endobj`.
2. **Its effect depends on the field, unpredictably.** At 200 stars `--depth 3` solves with
   timing identical to uncapped; at 50 and at 400 stars the same value fails outright. Nothing
   in the flag's documented meaning predicts that.
3. **Where it does take effect it can make things worse, not better.** At 50 stars, raising
   depth from 3 to 6 raised the failing runtime from 0.33 s to 8.9 s, and depth 8 and 10 blew
   through a 12 s `--cpulimit` entirely.

`nfield` in the JSON is always the full detected count (`starxy_n(field)`), so it cannot be
used to confirm whether the cap was applied — which is part of why this is easy to misread as
"working" when it is not.

**Consequence for #344:** do not plan on bounding quad-search cost with `--depth`. Star count
(`--max-stars` in the extractor) is the parameter that actually controls solve time, and
`--cpulimit` is the only reliable hard bound. The help text currently promises behaviour the
binary does not deliver consistently; that mismatch is worth raising separately rather than
papering over by choosing a depth value that happens to work for one pointing.


## Caveats
One image, one pointing. The star-count curve is real for this frame but the minimum's exact
location may shift with field density; #342's multi-image corpus would settle that. `solve_ms`
is the solver's own `timings_ms.solve`, which covers quad search plus verification — there is
no finer breakdown available inside astrometry.net's `solver_run()`.

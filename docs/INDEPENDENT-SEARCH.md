# Independent solver search policy

The solve request should carry the mount's approximate RA/Dec when available,
but that hint is not trusted as truth. The search policy is:

1. Try the hint and its local catalogue tiles.
2. If no high-confidence result is found, expand in deterministic corkscrew
   rings around the hint.
3. Enforce a hard attempt/time budget.
4. Reject weak, ambiguous, scale-inconsistent, or stale candidates.
5. If no hint exists, begin from all-sky tile centres and use the same gates.

`polaris-solve-independent-search.c` is the native bounded front end. It scans
the versioned `tile-*.pcat` directory, uses the native triangle-ratio index to
rank all-sky candidates, invokes the native C matcher without a shell,
and preserves the observable policy and failure result. The Python file remains
a host reference for policy tests only.

The native front end is opt-in as `SOLVER_BIN=polaris-solve-independent-search`.
It requires a tile manifest, a known focal length, a triangle index, and a hard
attempt budget; it does not make a regional catalogue into a fast blind solver.
The Astrometry path remains the default until the all-sky tile set, ARM runtime,
and physical capture gates pass.

The production-shaped defaults are 60 bright catalogue records per tile,
0.15 scale tolerance, at least 12 unique matches, and an early exit only at 20
matches with RMS no greater than 1.5 px. The front end compares successful
attempts and returns the strongest candidate, rather than accepting the first
low-residual false candidate.

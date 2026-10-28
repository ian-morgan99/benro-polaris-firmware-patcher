# Independent solver search policy

The solve request should carry the mount's approximate RA/Dec when available,
but that hint is not trusted as truth. The search policy is:

1. Try the hint and its local catalogue tiles.
2. If no high-confidence result is found, expand in deterministic corkscrew
   rings around the hint.
3. Enforce a hard attempt/time budget.
4. Reject weak, ambiguous, scale-inconsistent, or stale candidates.
5. If no hint exists, begin from all-sky tile centres and use the same gates.

`polaris-solve-independent-search.py` is the host reference wrapper. A native
implementation will move the tile selection and candidate queue into the
solver process, but should preserve this observable policy and failure result.

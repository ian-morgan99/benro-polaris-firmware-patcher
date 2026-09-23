# o-v12h recovery evidence — 2026-09-23

The K-3 III enumerated as USB `25fb:0189` and camera-info state 1. The first
RAW+JPEG capture completed in two seconds and published state 4. Benro then
sent its known late `-108` notification, causing the existing multishot harness
to stop before issuing shot two; a separate bounded second request reproduced
the fail-closed `-1005` without triggering an exposure.

o-v12h made the decisive recovery fields visible:

```
PTP=0x2001 size=576 +32=1 +36=1 +104=0 unsafe-mask=0x00109a03
```

Thus the conditions read succeeds and activity is idle, but a real transfer
candidate remains. In RAW+JPEG mode this is the delayed companion candidate.
The existing post-primary reconciler exits on its first empty sample before
that companion is published. The safe correction is to require a bounded
continuously empty settle window and drain any candidate that appears; the
recovery predicate must not be relaxed.

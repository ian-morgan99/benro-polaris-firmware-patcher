# Safe liveness probes

Do not assume a status/config call is harmless while Pentax is exposing/processing.

Use E2 plus `tests/pentax_stability_safe_probe_matrix.csv` to establish which observations can safely support long-operation liveness. Until proven, gate/queue uncertain probes rather than allowing watchdogs to issue them freely.

A probe that changes camera state, delays completion materially or increases failure rate is not a safe health check even if it normally returns a response.

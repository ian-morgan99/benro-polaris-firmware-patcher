# Pentax stability post-experiment triage flow

After a failed run:

1. Preserve trace + Mlog/Clog before recovery.
2. Identify first abnormal event.
3. Compare with previous baseline at same lifecycle point.
4. Repeat the smallest discriminating case.
5. If reproducible, update failure fingerprint/evidence registers.
6. Attribute the earliest owning layer conservatively.
7. Create/update a focused defect issue and cross-reference #82.
8. Locate source path/function before proposing behavioural fix where possible.
9. Write regression reproducer.
10. Apply deterministic fix and rerun A/B/A + adjacent baselines.
11. Only then assess whether recovery also needs modification.

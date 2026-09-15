# Stability review priority rule

When reviewing competing fixes, prefer the change that:

1. addresses the earliest proven incorrect transition;
2. is smallest/deterministic;
3. has the strongest pre/post reproducer;
4. preserves legitimate long-mode and user-data semantics;
5. improves observability;
6. leaves recovery as a safety net rather than normal control flow.

A patch that merely makes resets faster ranks below one that prevents the unnecessary reset from being triggered.

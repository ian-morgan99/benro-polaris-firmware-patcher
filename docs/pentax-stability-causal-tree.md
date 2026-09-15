# Pentax/Polaris crash causal tree

```text
capture/control request
 |
 +-- camera legitimately busy for mode/shutter?
 |    +-- yes -> did our timeout/watchdog/foreign command act first? -> timing/concurrency defect
 |
 +-- capture reaches output stage?
 |    +-- candidates fully reconciled? -> no -> candidate/finalisation defect
 |
 +-- pgphoto/process changed first? -> process/runtime/watchdog defect
 |
 +-- USB identity/transport changed first? -> physical USB/power/supervisor path
 |
 +-- preview/network request changed first? -> preview/integration pressure path
 |
 +-- direct libgphoto2 reproduces same first divergence? -> driver/camera path
 |    +-- no -> embedded pgphoto/runtime integration path
 |
 +-- later stale session/port/NoUpdateImage/-1005/reset requirement
      -> aftermath/recovery evidence unless proven earlier
```

Use traces and controlled experiments to choose branches; do not choose by intuition.

# What changed in the stability approach

Earlier emphasis: stale sessions and how to recover them.

Current approach:

- stale state is a real recovery defect but may be downstream;
- capture finalisation/candidate ownership is tested as an initiating defect;
- Pentax long-mode semantics are measured, not reduced to shutter duration;
- command concurrency/preview is explicitly adversarially tested;
- pgphoto process and USB state are independently instrumented;
- first abnormal transition is the grouping key;
- recovery is retained but evaluated after prevention/detection/containment;
- OpenPolaris is moved to E2E qualification rather than first-cause isolation.

# Why the first code is observability scaffolding

The repository now includes trace, analyser, matrix and validation code, but deliberately does not make a speculative camera-runtime behavioural change.

We currently have several plausible initiating defects. Changing timeout/recovery/locking before observing the first divergence could hide the actual cause and invalidate the baseline.

The first agent implementation should therefore wire structured events into the existing pgphoto/libgphoto2 paths with minimal timing impact, run the high-information experiments, and only then patch the earliest proven defect.

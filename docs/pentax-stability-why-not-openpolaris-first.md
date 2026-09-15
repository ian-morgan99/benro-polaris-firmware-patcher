# Why OpenPolaris is not the first diagnostic harness

OpenPolaris is useful and should ultimately exercise the finished capture contract. It is excluded initially because a failure through it includes additional variables: UI/state, protocol mapping, request cadence, Wi-Fi/network, HTTP preview and OpenPolaris-specific timing/retry behaviour.

The primary diagnostic path still exercises production-relevant Polaris pgphoto + staged libgphoto2, so it does not reduce the problem to an irrelevant desktop mock.

Once that path has a known-good trace, OpenPolaris becomes more useful: replay the same scenario and any new first divergence belongs to the newly added layer(s).

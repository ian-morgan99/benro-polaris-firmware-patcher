# Reintroducing OpenPolaris into Pentax stability testing

OpenPolaris is deliberately excluded from first-cause isolation because it adds protocol/UI/network/timing variables.

Reintroduce it after a lower-layer scenario passes through the Polaris pgphoto/staged-libgphoto2 path with a known lifecycle trace.

Then replay equivalent scenarios through OpenPolaris and compare the first divergence. If the lower path remains clean but OpenPolaris introduces extra preview/config/shutter requests or timing differences, attribute and fix at the higher layer.

OpenPolaris should ultimately become a valuable end-to-end qualification driver once the lower-level deterministic capture contract is established; it is not being rejected as a test platform permanently.

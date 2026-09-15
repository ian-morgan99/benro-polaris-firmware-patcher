# Pentax stability test stack

Use the narrowest layer that still exercises the suspected production code.

1. **Direct libgphoto2/gphoto2** — control/reference; useful for separating driver/camera from embedded integration.
2. **Polaris pgphoto + staged libgphoto2** — primary first-cause diagnostic path.
3. **Benro-facing protocol/preview path without OpenPolaris where practical** — integration qualification.
4. **OpenPolaris** — end-to-end replay after lower layers are known-good.
5. **Benro Connect / external field usage** — final compatibility/real-world soak.

A failure at a higher layer should be replayed one layer down before changing lower-layer code. A lower-layer failure does not require OpenPolaris to be present to be considered real.

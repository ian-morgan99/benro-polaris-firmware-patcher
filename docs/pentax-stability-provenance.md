# Hardware test provenance

Every stability run must record exact patcher SHA, libgphoto2 SHA, Polaris build, camera model/firmware and relevant lens/settings. Use `tests/pentax_stability_test_environment.csv` or the run manifest.

Without exact provenance, an apparent stability improvement cannot be confidently tied to a code change and is unsuitable for release qualification.

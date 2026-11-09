# Optional PC camera read-only probe

`pc_gphoto2_readonly.py` is the host-side complement to the Polaris WebUI
probe. It runs only `gphoto2 --auto-detect`, `--summary`, and status reads for
model, manufacturer, firmware, and battery. It never captures, writes a
setting, deletes a camera file, or talks to the mount.

Examples:

```sh
python3 tests/astro_regression/pc_gphoto2_readonly.py \
  --expected-model "PENTAX K-1 Mark II"
```

This is evidence about the PC USB/libgphoto2 layer only. It does not prove the
same camera is published by pgphoto on Polaris, and it does not qualify an
installed firmware candidate. Retain the command output with the candidate
source/package/installed hashes.

# HDMI patcher current contract

`container/hdmi_geometry_patch.py` remains the maintained static HDMI geometry
patcher. Its deterministic byte-pattern checks and companion tests remain in
this repository.

The evidence boundary is narrow: the static LIVE-site rewrite has source/build
validation, but the protected o-v9p camera firmware is not qualified as an HDMI
release and no current physical HDMI display result is claimed. DEAD-site and
dynamic transmitter work must not be inferred from the patcher's existence.

Historical reverse engineering, implementation plans and combined-build
narratives are preserved in PrivateResearch's issue 116 archive.

# v13j/v13k baseline divergence

The v13k diagnostic package was built from the genuine stock `FwPkt.zip` and
therefore did not preserve the v13j application filesystem.  This is a
material comparison, not a source-only rebuild:

| Candidate | appfs MD5 | Build ID | Physical result |
|---|---|---|---|
| v13j crash-boundary | `55bdc14a299b79e3f017785df29fd120` | `6.0.0.54.34-o-v13j-crash-boundary` | RAW+JPEG two-shot passed; Astro crash remained |
| v13k capture-trace | `eb7590d79b15674f03d8772a3636a136` | `6.0.0.54.35-o-v13k-capture-trace` | Astro-style first shot returned `-1005`, no file |

The v13j package also contains `FwVer`; v13k does not.  The v13j package was
reinstalled on 2026-09-28 using the sanctioned updater and verified on-device:

* `/app/FwVer`: `6.0.0.54.34-o-v13j-crash-boundary`
* libgphoto2 source: `e6cc1f8c8eeb95e4a9cb1652e804b9488167c4a4`
* patcher commit: `890d29d69fef7042875fbb58ba67215d7b696f24`
* stage2/core libgphoto2 MD5s match: `390194dd561de4bde4eb7ed701401507`
* stage2/stock ptp2 MD5s match: `25ad3be49f7b5aa169281236f0d901ae`

The v13k result must therefore not be attributed to the v13j source delta
until the application-filesystem difference is isolated.  Further physical
testing is paused at the v13j control baseline.

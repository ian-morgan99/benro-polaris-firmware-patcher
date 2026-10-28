# Native ARM Astro bundle — 2026-10-28

## Result

PASS for the source/package/staged-install/QEMU gates. This is still not a
Polaris post-boot or physical-camera qualification.

The bundle was rebuilt after the native C EXIF parser hardening:

```sh
bash build-astro.sh --image polaris-patcher-pentax --no-indexes \
  --out out/astro-bundle-native-exif-final2 \
  --catalog-package out/gaia-dr3-g10 \
  --src-cache out/.astro-src-cache
```

The ARM build passed the existing ABI, GLIBC ceiling, dependency and licence
guards. The relevant payload hashes are:

```text
polaris-extract                 fc1c12481197a2b88a28e9ab17e11a86ebcd39ecf4065b5d379446ac99709c4f
polaris-exif-solve              fac7f4327e2a24e3f9cb6967c7d051ca0e49827203eeaabce6687f3fd4c252f0
polaris-solve-independent-search
                                05f467eae60ebe20d4f41180f3bce531d10eeed96ec64b29b051457f962c9560
catalogue-tiles.ptri            b432e9d0ee7af86b8a5f412cf10f1f149f9b62942d38df9a22973de239b41601
```

A Docker staged install copied the native binaries and checked their execute
bits. The same ARM payload was run under the image's `/usr/bin/qemu-arm-static`:

- `polaris-extract --help` returned 0;
- `polaris-exif-solve` with no arguments returned the expected usage code 2;
- the EXIF writer enriched a 4096×3072 JPEG, preserved the JPEG end marker,
  and produced a valid Exif JPEG (241016 bytes in, 241123 bytes out).

## Boundary

No SD card was changed, no firmware was flashed, no mount command was sent,
and no physical K-3 III capture was performed. Installation provenance,
post-boot identity, local JPEG publication, and hardware qualification remain
open gates.


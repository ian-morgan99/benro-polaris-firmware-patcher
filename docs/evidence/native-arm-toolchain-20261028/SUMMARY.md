# Native solver ARM toolchain check

**Date:** 2026-10-28
**Scope:** cross-compilation and ELF inspection only. No binary was installed
or executed on Polaris.

## Result

The full `bash container/astro/build_solver.sh arm ...` gate still stops at the
existing Astrometry.net binary because the current host cross toolchain emits a
`GLIBC_2.38` dependency while the target firmware provides glibc 2.24.

The independent C matcher and native tile-search front end were also compiled
directly with the same ARMv7 softfp compiler. Source-level use of `fmod()` and
`hypot()` was removed from the search front end because that toolchain emitted
additional newer symbol versions. The latest standalone search ELF is 26,072
bytes and the matcher is 25,216 bytes; neither requests those newer math
symbols, but the compiler's startup object still requests
`__libc_start_main@GLIBC_2.34`.

Therefore the native source is cross-compiler-clean but the installed runtime
is not yet qualified. Completion requires an ARM sysroot/toolchain based on
glibc 2.24 (or a separately verified compatible startup/runtime strategy),
then `readelf`/DT_NEEDED checks, sanctioned package installation, post-boot
provenance, and physical capture tests. No hardware or firmware state was
changed during this check.

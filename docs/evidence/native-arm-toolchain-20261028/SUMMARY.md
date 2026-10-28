# Native solver ARM toolchain check

**Date:** 2026-10-28
**Scope:** cross-compilation and ELF inspection only. No binary was installed
or executed on Polaris.

## Result

The canonical Debian 9 build image (`polaris-patcher-pentax:latest`, GCC 6.3
family) now passes the full `bash container/astro/build_solver.sh arm ...`
gate. The Astrometry.net solver was linked with a reported glibc ceiling of
2.7 and the allowed `libc.so.6`, `libm.so.6`, and `libpthread.so.0` dependencies.
The independent matcher, native search front end, extractor, and simulator
were included in the same ARM build. The host Ubuntu compiler remains a useful
source check only: it emits `__libc_start_main@GLIBC_2.34` and must not be used
for the device package.

Source-level use of `fmod()` and `hypot()` was removed from the search front
end because the modern host toolchain emitted additional newer symbol
versions. In the canonical ARM bundle, the standalone search ELF is 22,644
bytes and the matcher is 17,596 bytes; their dynamic symbol versions are
bounded by GLIBC 2.7 and their dependencies are only libc and libm.

The bundled ARM executables were also started under the image's
`qemu-arm-static -L /usr/arm-linux-gnueabi` environment: their usage/help
contracts returned as expected. A solve under user-mode emulation was not used
as hardware qualification.

Therefore the native ARM source and package build are now ELF-qualified and a
staged `install_astro.sh` copy preserved all 648 tiles plus both manifests.
The installed device runtime is not yet qualified: it still requires a
sanctioned SD-card installation, post-boot provenance, and physical capture
tests. No hardware or firmware state was changed during this check.

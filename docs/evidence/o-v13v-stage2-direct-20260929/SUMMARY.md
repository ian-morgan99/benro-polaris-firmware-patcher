# o-v13v Stage-2 direct-capture candidate — 2026-09-29

## Plain-English result

One new firmware candidate was built from clean `main` sources. It fixes an
integration mismatch: the installed wrapper enabled an extra Stage-2 function
call around every still capture by default, even though the production policy
and regression test require capture to call the resolved libgphoto2 core
directly. The trace wrapper remains available only when explicitly enabled.

This is a plausible contributor to the reported failure, not a proven root
cause. The candidate has not been installed or physically tested. The known
restart-durability gap for an accepted capture whose output is not visible
remains open. Do not install until independent review approves the exact source
and artifact; do not call this Pentax-qualified.

## Source and artifact identity

- Patcher source: `24f64f5f6ce25fd7bba35cd597e0e3d43e96373f`, `main`, clean.
- libgphoto2 source: `718019fa0bb579cc5e8277ff2fa1f998a0fd37b4`, `main`, clean.
- Harness source: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`, `main`, clean.
- Build id: `6.0.0.54.41-o-v13v-stage2-direct-20260929`.
- Polaris / Benro Connect display value: `6.0.0.54.41`.
- Selected libgphoto2 camlibs: `ptp2,pentax`.
- Stock FwPkt SHA-256: `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`.
- ZIP: `out/o-v13v-stage2-direct-20260929/FwPkt.zip`.
- ZIP MD5: `db756a059830956ec4e66caeed706806`.
- ZIP SHA-256: `400d417c90a486ec15b9830b9773b8320b3693f0aa5a69259db126f92d428904`.
- appfs MD5: `c658bd37c3e70a13ea5f8b4535d8ff97`.
- PrivateResearch artifact commit: `dade1a7e7`, path
  `firmware-packets/o-v13v-stage2-direct-20260929/FwPkt.zip`.

## Changes

- The pgphoto wrapper now defaults `STAGE2_CAPTURE_TRACE=0`; an explicit
  environment override of `1` still turns on Stage-2 outer entry/return logs.
- The Stage-2 loader test verifies unset/zero preserve the exact resolved core
  capture function and explicit one selects the trace wrapper.
- The actual generated wrapper test verifies the shipped default is zero and
  explicit runtime selection of one is preserved.
- Recovery documentation and CURRENT-STATE record that strict admission and
  output ownership are still only process/session durable in libgphoto2; this
  candidate does not solve restart durability.

## Deterministic validation

- libgphoto2 release regression build/test: passed (build-release-candidate.sh
  exited successfully; the documented host-dependent `no-ci:test-gp-port` is
  excluded because this host has no supported DTR/CTS fixture).
- Patcher Stage-2 loader test: passed.
- Patcher pgphoto wrapper default/override test: passed.
- Patcher offline pre-release gate: 14 container checks + 24 Python checks,
  zero failures/skips.
- Package gate: FwPkt structure and firmwareInfo MD5 manifest passed.
- Test harness: `62 passed`.
- ZIP/appfs content proof: extracted appfs from the exact ZIP. SHA-256 matches
  the generated bundle for both core copies, both port copies, both ptp2 copies,
  Pentax camlib, both usb1 copies, `libpolaris_stage2.so`,
  `pgphoto.stage2ondisk`, and `/app/bin/pgphoto`. Embedded provenance exactly
  matches `build-source-provenance.txt`; packaged wrapper contains trace default
  `0`.
- Full-stack build note: StarShoot adapter compiled. iPolar/libuvc adapter
  compile was skipped because libuvc headers are absent; its frame-store
  component compiled. This does not claim functional UVC camera support.

## Physical state at build handoff

Read-only checks confirmed the Polaris AP and route, installed firmware still
o-v13s, and pgphoto alive. No Pentax `25fb` USB device was enumerated, so no
shutter was sent. No package was staged. After independent review, physical
testing requires the camera powered and enumerated, then sanctioned FwPkt
installation, cold reboot, runtime-loader/provenance verification, and a
bounded canary. The first canary must stop on any nonzero result; no blind retry.

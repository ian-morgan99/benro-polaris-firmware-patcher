# o-v13u review status — 2026-09-29

## Decision

Do not stage or install this artifact. The independent review found gaps in
output ownership under ambiguous PTP results and pgphoto restart. This artifact
is retained for audit/reproduction, not as the physical test candidate. A
follow-up source change is underway and is not contained in this ZIP.

## Exact artifact and sources

- Registry id: `o-v13u-output-obligation-20260929`
- Build id: `6.0.0.54.40-o-v13u-output-obligation`
- ZIP: `out/o-v13u-output-obligation-20260929/FwPkt.zip`
- ZIP MD5: `355146b8760824838c396a79ab1895bc`
- ZIP SHA-256: `f58adaac397a8a21864e0be85c70b4203ba65694ec916f136cf15167eed64001`
- appfs MD5: `032856903b1fb9e0e93b8efbc23b87b5`
- libgphoto2: [`30c1d8dab55e636ffc81cba86df012f39d4ebc78`](https://github.com/ian-morgan99/libgphoto2/commit/30c1d8dab55e636ffc81cba86df012f39d4ebc78)
- patcher source: [`49b69f9668695fb433d698ed1022ba7bf6c68202`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/49b69f9668695fb433d698ed1022ba7bf6c68202), `main`, clean at build
- test harness: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`
- PrivateResearch artifact upload commit: `dfe0b6813`

The final ZIP was unpacked and checked against the build outputs. `pgphoto`,
Stage-2, both `libgphoto2` cores, `ptp2.so`, Pentax camlib, USB iolib and the
camlib manifest matched the intended runtime bundle. The stage2 and stock copies
of the core/port/ptp2 components matched each other.

## Tests at build time

- libgphoto2 release regression subset: 13/13 passed; the no-CI serial test
  was excluded because its fixture is absent.
- Patcher offline gate: 14 container tests + 24 Python tests passed.
- Package/manifest checks: 4 passed, 0 failed, 0 skipped.
- Test harness: 62 passed.

Follow-up focused Pentax tests and the host `ptp2.so` build passed after adding
pre-shutter output-format validation and pre-command obligation latching in the
working tree. Those uncommitted changes are not present in o-v13u. A later full
Meson run had 12/14 pass; `test-gp-port` failed because the environment exposes
an invalid USB fixture, and `test-gphoto2` failed because it requests an
unavailable camera model. The four focused Pentax tests passed.

## Independent review findings

1. The output obligation was only latched after successful `InitiateCapture`;
   a lost response could leave a successful exposure untracked.
2. The obligation was in process memory only. A pgphoto restart could lose it
   when no camera candidate remained visible.
3. An abbreviated conditions response did not contain the output-format field
   at offset +524, but the helper interpreted that as zero companions.
4. Tests covered helper truth tables, not the actual capture lifecycle and
   process-restart boundary.
5. The provenance registry/evidence row was missing at initial review; this
   document and registry row backfill that audit gap.

The camera battery has since been replaced. At 2026-09-29 13:39 UTC, Polaris
identity checks passed (BSSID `48:e7:da:d4:b5:73`, route via `wlp8s0`, FwVer
`6.0.0.54.35-o-v13s-preserve-pending`) and the Pentax was enumerated as USB
`25fb:0189`. No shutter was issued and o-v13u was not staged.

## Required before a physical candidate

- Close all five review findings, including an explicit policy for restart
  recovery that does not mistake camera READY for output completion.
- Add deterministic tests that execute the production lifecycle transitions
  and the Stage-2/pgphoto restart boundary.
- Build a new, uniquely named candidate from clean `main` sources.
- Pass the independent source, test, registry, and exact-artifact review.
- Only then use the sanctioned staging/install and canary procedure.

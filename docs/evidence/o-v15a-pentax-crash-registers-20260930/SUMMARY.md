# o-v15a Pentax crash-register diagnostic candidate

Status: built and privately uploaded; **not installed or physically qualified**.

## Why this candidate exists

On 2026-09-30 at operator-reported 14:43, a manually requested M-mode capture
was accepted by Pentax `InitiateCapture` and then the Polaris `pgphoto` process
segfaulted before its capture/publication completion boundaries. The user
reported a long apparent shutter-open interval followed by a camera reload.
The camera remained enumerated after pgphoto restarted; the available logs do
not prove a physical camera USB disconnect or camera reboot. The reported
observation and the logs differ: logs recorded `bulb:0` and `1/1000s`, so this
event is not classified as a confirmed Bulb exposure.

The installed crash handler only retained the fault PC/address. That was
insufficient to identify the faulting call site in an ASLR-mapped process.
Candidate `o-v15a-pentax-crash-registers-20260930` adds ARM LR/SP and r0-r3/r12,
plus a bounded `/proc/self/maps` dump to the existing persistent Stage-2 crash
record. It does not change Pentax code, shutter admission, transfer, recovery,
watchdog, or timing policy. It is instrumentation to identify the crash before
making a behavior change.

## Source and package identity

- Patcher source: `9a2c1396f4a77b85b0f8e8f3f2ce16f3238e0980` (`main`, clean)
- libgphoto2 source: `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd` (`main`, clean)
- Build id: `6.0.0.54.44-o-v15a-pentax-crash-registers-20260930`
- Displayed firmware version: `6.0.0.54.44`
- Stock input: `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt.zip`
- FwPkt: `out/o-v15a-pentax-crash-registers-20260930/FwPkt.zip`
- FwPkt MD5: `64ccd4a4173d0d3364b4380ee73f4002`
- FwPkt SHA-256: `77c80c1fcc9a09d3e4018679e78179c951828a1c948b18a67d517de8938c5280`
- appfs MD5: `d9874445c9355eb173cf2d31eae8ef19`
- PrivateResearch artifact commit: `83a5fed1e`
- Registry: `docs/FWPKT-PROVENANCE-CONTRACT.md`

## Deterministic checks

- libgphoto2 Meson build: passed.
- libgphoto2 Meson tests: **14/14 passed**; serial DTR/CTS test skipped because
  the host has no supported control-line fixture.
- Patcher deterministic gate: **16 container + 24 Python passed**.
- Package structure and duplicate-file validation: passed.
- All six `firmwareInfo` manifest entries matched produced package bytes.
- The standalone `--build` gate's optional comparison with the stock archive
  skipped because the clean source clone does not contain `firmware/FwPkt.zip`;
  the release pipeline separately supplied the stock archive and validated its
  derived output manifest.
- The built ARM `libpolaris_stage2.so` contains the new register and process-map
  diagnostics; it is the packaged loader output, not merely a host compile.
- Hardware, installed-runtime, capture, cancellation, and post-crash recovery
  behavior are **not tested by this candidate build**.

## Next proof

After independent review of the diagnostic-only change, install only through
the registered extracted `FwPkt/` update flow. Do not send another shutter
until device identity, version, embedded provenance, component hashes, and
process ownership have been rechecked. Capture a bounded reproduction with the
same log evidence as the 14:43 event. The minimum intended result is a crash
record whose PC/LR resolve against the matching runtime maps and packaged
objects, followed by a separate root-cause fix and its deterministic tests.

The physical camera reported a long shutter interval at 14:43, but this
candidate intentionally does not claim it resolves that symptom or makes
capture safe. See patcher issue #145 and its evidence comment for the original
Clog/Mlog/crash-log bundle.

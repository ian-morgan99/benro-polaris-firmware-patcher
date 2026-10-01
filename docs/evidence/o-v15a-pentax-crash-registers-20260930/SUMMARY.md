# o-v15a Pentax crash-register diagnostic candidate

Status: **PHYSICAL FAIL / NOT RELEASE-QUALIFIED**, per the 2026-09-30
17:35 UTC review on #149. The installation probe below was read-only; later
physical app requests were refused before initiation with a persistent candidate.
The 14:43 accepted-shot crash described below was the preceding o-v13x build,
not proof of a new v15a crash. See the [current recovery audit](../pentax-orphan-recovery-20260930/SUMMARY.md).

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

Resolve safe orphan-output recovery and durable publication ownership before
another firmware/shutter test. Preserve strict admission and the candidate.
A direct exact-source PC baseline is required before changing library behavior.
Crash diagnostics remain useful on a later justified reproduction; package or
runtime verification does not qualify the camera.

## Installation and read-only runtime verification

Installed on 2026-09-30 through `/app/sd/FwPkt/` and the normal `/sbin/reboot`
watcher path. Before staging, the verified Polaris was on `polaris_d13e86`
(BSSID `48:E7:DA:D4:B5:73`), route `192.168.0.1` via `wlp8s0`, and reported
`6.0.0.54.43` / build `6.0.0.54.43-o-v13x-camlib-prep-20260930`. The SD
`FwPkt/` target was absent. The registered ZIP hash and appfs MD5 matched this
registry row; after transfer all six payload byte sizes and MD5s matched the
package `firmwareInfo` before reboot.

After reboot, device identity was rechecked by Polaris BSSID and Wi-Fi route.
`/app/FwVer` reports `6.0.0.54.44`; embedded provenance reports libgphoto2
`fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`, patcher
`9a2c1396f4a77b85b0f8e8f3f2ce16f3238e0980`, and the exact o-v15a build id.
`polestar_app` and `pgphoto.stage2ondisk` are alive. Environment paths select
the intended Stage-2 tree; core, port, ptp2 and usb1 Stage-2/stock-path hashes
match pairwise. The running loader contains the new `arm lr=` and `process maps
begin` diagnostic strings. Pentax `25fb:0189` is enumerated.

The read-only canary probe reported K-3 Mark III `state=1`, `storage=2`,
`photoFormat=2`; it did not send capture request 264. No physical shutter test
was performed. The reboot's kernel log includes a USB bus reset and then the
camera enumerated; this does not establish a post-install capture result. The
Mlog reported that the SD card had not been properly unmounted before reboot;
firmware files nevertheless passed all six manifest checks before reboot.
Full transcript: `INSTALL-VERIFICATION.md`.

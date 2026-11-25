# astro-v116-ptp-diagnosability-20261124 — build, gate, and handoff

## Artifact (built, gated, published; NOT installed)
```
FwPkt.zip            sha256 77ed82ccc9086c42ecbca48e81efaecd2ac2354cb656c19c70b08fe8a5e32987
                     md5    65c55b198bb3ce5b47b9d59111c91b75   size 68408628
astro-bundle.tar.gz  sha256 e542c632334603654c12ee241e40604ad7d7e40c074b83e9d933b783062bd774
fwver                FwVer:6.0.0.54.116;date:2026.11.24;
published            ian-morgan99/PrivateResearch firmware-packets/6.0.0.54.116--astro-v116-ptp-diagnosability-20261124
```
Published digest re-read from the remote equals the build digest byte-for-byte.

## Source binding
```
libgphoto2  be9da156f8adc0c1bf520c777636e50a712ea67a   (v115 pin 0f2f34e00 + exactly one commit)
patcher     65785529a87323e4ca19ba7d0b2f23410cedd5db
```

## Gate
Build-time gate: **23 passed, 0 failed, 4 skipped** (all skips are prerequisite gaps:
no stock FwPkt.zip in repo, no prior candidate manifest to diff, no built artifacts to
compare hashes against, ARM emulation not requested by the builder).

ARM emulation of Stage-2 was run separately afterwards, per the v115 handoff's
authoritative standard (`--require-arm-emulation --arm-harness-src`):

```
binary sha256  fcce947ff5525629...  matches install-manifest.json
loader result  pass
instructions   100000 of 100000 budget
relocations    265 resolved / 0 unresolved
stub calls     0
```
Identical numbers to the v115 ARM record, which is expected: `pgphoto.stage2ondisk`
is byte-identical between v115 and v116 (`fcce947f…`). v116 changes only the driver.

This check proves load, relocation and bounded execution only. It does not qualify the
candidate; physical K-1 II / K-3 III testing is still required.

## What v116 actually contains
- **Driver:** 32 unmapped standard PTP result codes now map to specific GP errors
  instead of generic `GP_ERROR`. Verified in the shipped ARM binary: `.text` grew by
  exactly 272 bytes (68 ARM instructions) with `.rodata` byte-identical to v115 —
  the signature of a numeric-only switch addition, so the packet genuinely carries
  the fix rather than being a rebuild of identical code.
- **Patcher:** reproducible widget-enumeration A/B tooling for the K-1 II read cost
  (issue #389), plus its regression tests. The 34.8x optimization itself lives in
  the harness, not the firmware.

## What v116 does NOT contain — read before deploying as a "K-3 III fix"
No K-3 III recognition fix is present, because no recognition regression was found:
- With the v115 driver on direct PC, the K-3 III (`25fb:0189`, fw 2.20) auto-detects,
  inits exact-model, and vendor-enables cleanly; harness gate 3 passed / 2 expected xfail.
- The K-3 III ability row and `pentax-utils.c` (model/PID gate) are byte-identical
  between the v114 and v115 pins. Only three code files changed v114->v115, none in
  the recognition path; `library.c` differs by log strings only.
- o-v9d (September) recorded K-3 III live control working on the mount, so recognition
  is not newly broken at the driver level.

### Packaging hypothesis: raised, then DISPROVEN
I suspected the port-module layout: v115/v116 ship `lib/stage2/libgphoto2_port/0.12.2/`
(`usb1.so`, `usbscsi.so`) plus a separate `lib/libgphoto2_port/0.12.0/`. Extracting the
v116 appfs (`ubireader_extract_files`) and comparing with the v114-era image — identified
positively by its driver containing the v114 log string "already open from a previous
connection" and not the v115 replacement — shows the layout is identical in both. K-3 III
recognition worked on the mount under v114-era builds, so an unchanged layout cannot be
the cause. Do not re-test this.

### Ruled out so far
| candidate | evidence |
|---|---|
| ability table row for `0x0189` | identical between v114 and v115 pins |
| `pentax-utils.c` model/PID gate | not among the files changed v114->v115 |
| `library.c` init path | differs by log strings only |
| stage2 binary | same sha256 (`fcce947f…`) in v115 and v116 — **but it changed v114->v115** (`f167e668…` -> `fcce947f…`), so this row does NOT rule stage2 out of the regression window. See the 2026-11-25 correction in CURRENT-STATE.md. |
| port-module packaging | layout identical to the v114-era image |
| driver recognising the body at all | works on direct PC with the v115 driver |

**Root cause is still unidentified.** The first thing to run when the mount is reachable
is `lsusb -d 25fb:` with the K-3 III attached: if the body does not enumerate on the
mount's USB host, this is a USB-path/hardware problem and no firmware release fixes it.

## Install status: BLOCKED (verified, not assumed)
`wlp8s0` is DOWN and a full rescan finds no `polaris_*` SSID. Per the identity rule no
install may proceed until real association is up and `/app/FwVer` reads over that
interface. The 192.168.0.1 that answers on the LAN route is the home router, which
AGENTS.md flags as a false positive.

## Reproducibility note (process defect worth fixing)
The build ran from throwaway clones under /tmp and I deleted them during cleanup,
destroying the only local copy of the build output. The packet was recovered from
PrivateResearch with a matching digest, but the durable lesson: build output belongs
under `out/` in the canonical tree, not `/tmp`.

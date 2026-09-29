# o-v13n main Pentax/display candidate

## Status

**BUILT, PRIVATELY PUBLISHED, PACKAGE-GATED; NOT INSTALLED.** The exact bytes
are ready for independent review. Per the release process, physical staging
must wait for that independent review. No camera or Polaris behavior is
qualified by these offline checks.

## Exact inputs

- Patcher `main`: `7c514e32851b478dc962455a78fb193f0caf423c`
- libgphoto2 `main`: `4bdbc75ebcea816a7ab47f81771f2efb53ca4f2f`
- Firmware base: `firmware/FwPkt.zip`
- libgphoto2 version: 2.5.34; port ABI: 0.12.2
- Packaged camlibs: `ptp2,pentax`
- Build ID in source provenance: `6.0.0.54.38-o-v13n-main-pentax-display`
- Package and appfs `FwVer`: `6.0.0.54.22`
- Display value is a test experiment; Connect's actual displayed result has
  not been confirmed on hardware.

## Fixes behind the test-suite recovery

- Generic libgphoto2 `gp_filesystem_append()` now treats `filename == NULL` as
  a directory announcement after ensuring the directory exists, instead of
  calling `strdup(NULL)`. The existing `test-filesys` exercises this path and
  now runs in the deterministic Meson suite.
- The filesystem test callbacks now compare paths while ignoring trailing
  slashes, matching the equivalent folder paths supplied by the filesystem
  API. This resolves the follow-on `Directory not found` test failure without
  changing camera-driver path behavior.
- The Meson host test setup includes the Directory Browse camlib required by
  `test-gphoto2`, and explicitly builds test targets before running them.
- `test-gp-port` remains tagged `no-ci`; it assumes a serial device supporting
  DTR/CTS. On this host it reports `get_pin: Unsupported operation`. The
  release script reports this as an explicit hardware-dependent SKIP and runs
  all deterministic tests fail-closed.

## Deterministic verification

- libgphoto2 Meson deterministic suite: **12/12 PASS**.
- libgphoto2 serial control-pin test: **SKIP**, `no-ci` hardware prerequisite
  (no supported DTR/CTS fixture); not counted as a pass.
- Patcher offline gate: **13 container + 24 Python PASS**.
- Benro Polaris test harness `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`:
  **62/62 PASS**. This is deterministic contract evidence only, not physical
  camera qualification.
- Built-package gate: **13 container + 24 Python + structure + firmwareInfo
  manifest PASS**.
- FwPkt structural validation: PASS; all six `firmwareInfo` payload entries
  match their shipped sizes and MD5 values.
- Re-ran the package gate against this candidate on 2026-09-29: **4 passed,
  0 failed, 0 skipped**. Raw output: `package-gate.txt`.
- Re-ran the libgphoto2 deterministic suite from clean source SHA
  `4bdbc75ebcea816a7ab47f81771f2efb53ca4f2f`: **12/12 PASS**. The test build
  is tied to that source directory; `test-gp-port` is tagged `no-ci` and is
  intentionally excluded because it requires serial DTR/CTS hardware.
  Transcript: `libgphoto2-meson.txt`.
- Re-ran the test harness at SHA `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`:
  **62/62 PASS**. Transcript: `harness-pytest.txt`.
- Extracted appfs content was byte-compared against the build's Stage-2 bundle:
  `bin/pgphoto`, restart helper, USB supervisor, Stage-2 loader, `libpolaris_stage2.so`,
  libgphoto2 core/port, `ptp2.so`, `pentax.so`, camlib manifest and `usb1.so`
  all match exactly.
- Repeated the appfs-vs-bundle byte comparison from the appfs extracted out of
  this exact ZIP: **11/11 runtime components byte-identical**. Transcript:
  `package-content-audit.txt`. The local ZIP and PrivateResearch ZIP also
  recompute to identical MD5/SHA-256 values.
- ZIP appfs SHA-256 and standalone built appfs SHA-256 match:
  `295689e6000d25d2641e5d16d5686f0f7434c37830873641210c08bc07306910`.
- `camlibs.manifest` SHA-256 entries:
  - `pentax.so`: `81fa3778f6d6a1daa4ee90d4ffe9ebeb31b01d1e620de0b77631771575780e36`
  - `ptp2.so`: `fff9e371250ff641607f765ff05425f6982ca94534aaa53d2590735b2c340514`

## Artifact and provenance

- Registry ID: `o-v13n-main-pentax-display-20260929`
- Private artifact:
  `ian-morgan99/PrivateResearch/firmware-packets/o-v13n-main-pentax-display-20260929/FwPkt.zip`
- Private artifact commit: `20ffc40cbfe29a6a480a2be4bb49e0e99411cda4`
- ZIP MD5: `f98c2aff47ab3c3a2a8bdccb6f709086`
- ZIP SHA-256: `97c1212da5aa35447da6494d516dfc050b8478d2b67b7778d3ea10760502be76`
- appfs MD5: `528b3c8dd42d480aea3b3d353bf8623a`

## Remaining acceptance

### Scope blocker: QHY/iPolar are not ready

The green 13n package gates are **not** QHY or iPolar driver gates. At the
exact patcher source SHA recorded above, direct ARM cross-compilation fails:

- QHY (`stage2_qhy5lii_adapter.c`): SDK headers require C++ `<functional>`;
  the C compile also reports `bool` undefined. Exit 1.
- iPolar (`stage2_ipolar_adapter.c`): `uvc.h` is unavailable. Exit 1.

Reproduction is saved in `uvc-adapter-compile-audit.txt`. The build script does
not compile the QHY adapter; the iPolar compile is conditional on libuvc headers
being present and otherwise only logs that its check is pending. The 13n
runtime manifest selects `ptp2,pentax`, and its packaged Stage-2 runtime has no
QHY/iPolar adapter objects. Thus these failures do **not** disprove the
Pentax-only candidate, but 13n must not be installed or represented as a QHY or
iPolar test candidate. Those drivers need their own correct language/runtime
integration, explicit fail-closed compile/link gates, and package-content proof
before any UVC acceptance test.

### Follow-up compile check: current uncommitted adapter sources

The working-tree edits now pass ARM EABI object compilation when supplied with
the local external inputs (QHY SDK headers and libuvc 0.0.8 headers): QHY via
`arm-linux-gnueabi-g++`, iPolar via `arm-linux-gnueabi-gcc`. This is a syntax/
object-build result only, not a link or runtime result. The QHY object exports
no symbols; the iPolar object has an unresolved `uvc_init`, and its open/stream
functions remain stubs. These dirty edits and external dependencies are not in
the 13n package or its provenance. Transcript: `current-adapter-cross-compile.txt`.

The proposed follow-up (“add both to `build_fullstack.sh`”) also names the wrong
source-list owner: that file only delegates to `build_ptp2.sh`; the Stage-2
shared library is linked in `container/patch.sh`. Moreover, these Stage-2
adapters are not libgphoto2 camlibs. Before linking or packaging them, resolve
the documented UVC classification for both devices against the QHY
vendor-protocol claim, implement real open/stream/frame publication rather
than compile-only stubs, and define the Polaris caller/ownership contract. A
compile-only object added to the firmware would not constitute camera support.

The Benro Connect source was adversarially checked: its `UgradeUtils` version
comparison splits on dots and proceeds only when **both** versions have
exactly four numeric components. With this candidate's five-component display
value (`6.0.0.54.22`), that comparison returns the no-update result. This does
not block the SD-card firmware updater, but app-based update availability is
not behavior-neutral and must not be represented as tested. Confirm the
displayed value on Connect and avoid using Connect's firmware-update flow for
this candidate.

After independent review, install only via the documented update flow, then
cold-boot and verify runtime provenance/loader hashes before a bounded
physical canary. Ordinary JPEG-only, RAW-only repeatability, native Astro,
Panorama/Pro Panorama, Pixel Shift completeness, cancellation, reconnect/rebind
and non-Pentax qualified-camera regression are not established by this offline
build and remain separate acceptance work. The candidate is a Pentax-focused
test packet, not a UVC/iPolar/StarShoot qualification build.

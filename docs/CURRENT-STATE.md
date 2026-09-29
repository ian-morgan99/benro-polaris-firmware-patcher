# Current repository state

## 2026-09-29 adapter hardening (o-v13p) — post-release fixes, awaiting TA guidance

Follow-up audit of the o-v13o adapter work found and fixed:

- **iPolar (#159):** `uvc_find_device` takes a reference on the returned device
  (verified in libuvc 0.0.8 source; upstream example calls `uvc_unref_device`
  after `uvc_open`) — the adapter now releases it, so no ref leak per open.
  Frame callback guards a missing sink buffer; streaming state is tracked so
  `close()` only stops an active stream and `stream_y16()` is idempotent.
- **StarShoot (#158):** `starshoot_adapter_stream_bulk_iso()` now returns the
  bounded handshake transfer result (0 / negative libusb code) instead of void,
  making the TA's hardware discriminator observable without a device on the bench.
  Opcode values re-verified against `Temp/qhyccdcamdef.h`.
- Both adapters compile clean with patch.sh flags (zero warnings); full symbol
  export verified via `nm`; offline gate GREEN.

Awaiting TA guidance on next step: hardware discriminator for #158 (handshake +
one frame from the attached 16c0:29a0) and linking the adapters into the stage2
build for a combined Pentax+UVC candidate.

## 2026-09-29 TA review response: adapter consolidation + bounded lifecycle

Technical architect comments on #158/#159 (2026-09-28) were addressed in the
working tree:

- **Consolidation:** removed the duplicate `container/stage2_qhy5lii_adapter.{h,c}`
  created earlier this session. The canonical #158 adapter is
  `container/stage2_starshoot_adapter.{h,c}` (build-wired via
  `container/patch.sh:426`; the file the TA reviewed by name). Both targeted
  `16c0:29a0`; only starshoot was referenced by any build path.
- **#158 bounded lifecycle (TA requirement):** `starshoot_adapter_open(vid,pid)`
  now enumerates, matches VID/PID, opens, claims interface 0 and selects alt
  setting 1; new `starshoot_adapter_close()` releases the claimed interface +
  handle; `ss_transfer_opcode()` provides bounded vendor control transfers with
  libusb error codes; `stream_bulk_iso()` issues the `IS_CAMARA_INIT` handshake.
  All paths fail-closed. Still owed per TA: hardware discriminator (handshake +
  one frame from the attached 16c0:29a0) — needs the device on the bench.
- **#159 per TA direction:** iPolar adapter now has a bounded Y16 frame sink
  (fixed buffer, monotonic generation identity), `reconnect()`,
  `set_exposure()`/`set_gain()` controls and `latest_frame()` for the common
  camera-source interface. No iPolar-specific polar-solving stack; the solver
  stays source-agnostic (`iPolar -> UVC/libuvc frame -> common camera-source
  frame -> plate solve -> polar-axis error`).
- **Compile status (patch.sh flags, zero warnings):** starshoot
  (`gcc -c -fPIC -O2 -std=gnu11 -Wall -Icontainer -I/usr/include/libusb-1.0`)
  and iPolar (`... -I/work/src/libuvc/include -I/work/src/libuvc/build/include`)
  both PASS. `patch.sh` iPolar check updated to include the CMake-generated
  `libuvc_config.h` root. libuvc 0.0.8 notes: Y16 = `UVC_FRAME_FORMAT_GRAY16`;
  device lookup via `uvc_find_device` (opaque `uvc_device_t`).
- **Classification:** both adapters remain skeleton/interface work until the
  hardware discriminator passes and the adapters are linked into the stage2
  build. o-v13n is still NOT a combined Pentax+UVC candidate.

## 2026-09-29 candidate: o-v13n

`o-v13n-main-pentax-display-20260929` is **BUILT, PRIVATELY PUBLISHED, AND
PACKAGE-GATED; AWAITING INDEPENDENT REVIEW BEFORE STAGING; NOT INSTALLED OR
PHYSICALLY QUALIFIED**. It uses patcher
`7c514e328` and libgphoto2 `4bdbc75eb`. The package and appfs FwVer are set to
`6.0.0.54.22`; the build identity `6.0.0.54.38-o-v13n-main-pentax-display`
is separately recorded in provenance. Connect's actual displayed version is
not yet verified.

The test failures encountered during packaging were addressed at their owners:
NULL directory append no longer crashes libgphoto2, its filesystem regression
test now passes in the deterministic suite, and the host Meson setup includes
the Directory Browse camlib required by its generic camera test. The serial
DTR/CTS test remains an explicit `no-ci` hardware prerequisite skip. Results:
libgphoto2 12/12 deterministic tests, patcher 13 container + 24 Python tests,
and package structure/firmwareInfo gates all PASS. Package contents were
extracted and byte-compared with the built Stage-2 bundle.

Adversarial recheck on 2026-09-29 reproduced the package gate (4/4), libgphoto2
tests (12/12), and harness (62/62), and verified all 11 embedded Stage-2 files
against the candidate build bundle and the PrivateResearch ZIP hashes. Raw
transcripts are in the candidate evidence directory. Caveat: Benro Connect's
version comparator handles exactly four dot-separated numeric fields; this
five-field display value returns “no update” in that comparator. This is an
experimental version-display candidate, not verified as neutral to app-based
upgrade checks. Do not use Connect's firmware-update flow for it.

Scope audit: the adapter sources at the recorded 13n patcher commit fail the
standalone compile checks, and neither adapter is part of 13n's packaged
runtime. Newer, still-uncommitted working-tree edits pass ARM object compilation
when local QHY SDK/libuvc inputs are mounted, but the QHY object exports no
symbols and iPolar retains an unresolved `uvc_init`; open/stream remain stubs.
The trace is in `evidence/o-v13n-main-pentax-display-20260929/`. Therefore 13n
is not a combined Pentax+UVC candidate and must not be installed for QHY/iPolar
testing. No installation is planned on this evidence.

Artifact hashes and the remaining physical acceptance matrix are in
`evidence/o-v13n-main-pentax-display-20260929/SUMMARY.md`; the registry entry
is in `FWPKT-PROVENANCE-CONTRACT.md`. v14 is unchanged. Earlier scenario gaps
remain open until exercised against this identified candidate.

## 2026-09-28 one-off scenario audit

The latest source-main package `o-v13m-main-pentax-uvc-20260928` is build and
offline-gate valid but remains **NOT INSTALLED / NOT PHYSICALLY QUALIFIED**.
Evidence in `evidence/o-v13m-main-pentax-uvc-20260928/SCENARIO-AUDIT.md`
shows earlier K-3 III RAW+JPEG and limited Astro-equivalent passes, but no
current-package proof for JPEG-only, RAW-only repeatability, native Astro,
Panorama/Pro Panorama, or a successful complete Pixel Shift output set.
Pixel Shift remains specifically unqualified: the recorded v12h experiment
was incomplete and v12m crashed after publishing its two outputs. Do not claim
the current package works across all scenarios or formats until that matrix is
run against an identified installed build.

This is the concise entry point for agents and maintainers. Read it before
searching historical handovers or raw evidence.

## 2026-09-28 current candidate: o-v13i (session-recovery)

`o-v13i-session-recovery-20260927` is **INSTALLED, RUNTIME-VERIFIED; stale-session
rebind works; capture canary FAILED (active-owner defect)**. In plain English: the
replacement `pgphoto` process now recovers from a retained Pentax session
(`0x02fa`/`0x02fd`/`0x02ff` -> ordered close/reset/reopen, libgphoto2
`e6cc1f8c8`), but the ORIGINAL capture owner is still terminated/replaced after an
operation that fails to complete. Next investigation boundary: the
pgphoto/polestar watchdog decision and the first blocked/failed production
operation before replacement. Do not add another USB retry or claim the capture
fixed.

Provenance: build id `6.0.0.54.33-o-v13i-session-recovery`, patcher `0746ed3`,
libgphoto2 `e6cc1f8c8`, harness `0355f6f64`. Full evidence and the remaining
physical acceptance (two-capture test after the active-owner fix) are in
`evidence/o-v13i-session-recovery-20260927/SUMMARY.md`.

## 2026-09-27 current candidate: o-v13g

`o-v13g-linked-publication-20260927` is **INSTALLED, RUNTIME-VERIFIED, AND
K-3 III RAW+JPEG TWO-SHOT PASS**. In plain English: the package crash found in
version F is fixed; one bounded capture passed, then two consecutive captures
also passed with distinct outputs and without issuing the next shutter early.
The bounded Preview-on, suspend, capture, and Preview-restore sequence also
passed with a complete RAW+JPEG output pair.

The installed build embeds libgphoto2 `8601460b3` and patcher `93e1898`, build
id `6.0.0.54.31-o-v13g-linked-publication`. Version F had omitted
`pentax-publication.c` from the Automake build and therefore crashed before
`InitiateCapture` on an unresolved helper. The source inclusion is corrected
and the patcher now rejects any package with unresolved internal `pentax_*`
symbols. Full provenance, hashes, install proof and physical results are in
`evidence/o-v13g-linked-publication-20260927/SUMMARY.md`.

This is a convergence candidate, not yet a blanket release qualification.
The separate #146 reconnect/rebind and external-change matrix, #147 Preview
interactions, #148 long-exposure/cancellation work, and unavailable regression
cameras remain explicit follow-on gates.

## 2026-09-27 restored-fixes candidate

`o-v13e-restored-fixes-20260927` is **BUILT, PRIVATELY PUBLISHED AND
PACKAGE-GATED; NOT INSTALLED; LIVE CANARY PENDING**. In plain English: the
missing Pentax fixes have been restored into one clean libgphoto2 line and the
resulting firmware package is internally consistent, but this exact package
has not yet been put on the Polaris or exercised against a camera.

The candidate embeds libgphoto2
[`564bdd070`](https://github.com/ian-morgan99/libgphoto2/commit/564bdd070cec3f4a366444a7d7e95605f90e30f3)
from PR [libgphoto2#94](https://github.com/ian-morgan99/libgphoto2/pull/94),
patcher `96b75902aae4473bfb7be56195fb3f9a079d73a9`, and harness
`a8b65817354dae04f997d1357d7d4914e396c42f`. It restores strict-only
pre-shutter admission, production-path publication ownership and deletion
semantics, exact long-exposure labels (for example 80s/90s rather than 1m/2m),
timeout restoration on every abnormal exit, and timeout-phase diagnostics.
It packages both `ptp2` and legacy `pentax` camlibs; this does not provide the
separate V4L2/UVC implementation needed by iPolar or Orion StarShoot.

Deterministic results: four focused Pentax production-path tests PASS;
firmware-patcher offline gate PASS (13 container + 24 Python); test harness
PASS (62/62); built-package gate PASS (13 container + 24 Python + structure +
firmwareInfo). The broader libgphoto2 Meson run was 10/13: the three failures
are existing environment/baseline failures (`test-gp-port`, generic-model
`test-gphoto2`, and `test-filesys` SIGSEGV), not suppressed green results.

Artifact: `out/o-v13e-restored-fixes-20260927/FwPkt.zip`; MD5
`5a3ae51583b4a46c02fd8120314a2bca`; SHA-256
`4b7982e28e361f0669eedc61103e75f16a3101af0e47d79c3fdf500a65631c8d`;
appfs MD5 `f8e70314b4bf9c25d12ff4eaba16a4b9`. Private artifact commit:
`ac518690b`. Exact evidence and remaining gates are in
`evidence/o-v13e-restored-fixes-20260927/SUMMARY.md`.

This candidate is not release-qualified until the supported install flow,
cold-boot loader/hash proof and bounded physical canary complete. The
session/rebind atomic-lock work tracked by #146 also remains independent of
these recovered libgphoto2 fixes and must not be described as solved by this
build.

## 2026-09-26 post-merge release review

Main is `688437b`, containing the o-v13c convergence work. Review follow-up is
on `release/o-v13d-review-convergence-20260926`; it is not yet a firmware
candidate. The review corrected the live-gate oracle: code 286 `photoFormat`
is only a hint and cannot determine whether one or two output files are owed.
Every shuttering gate now requires an explicit independently established
`--expected-files 1|2`; RAW+JPEG still requires an exact same-stem pair. A
regression covers the physically observed `photoFormat:2` plus independently
RAW-only contract and one DNG.

The two-shot gate now gives each failed operation a failure budget of exactly
one shutter command. A timeout, negative state, stale output, missing output,
or mismatched companion stops the sequence without retry or a second shutter.
This proves the test client does not hammer a failed camera; it does not prove
physical recovery, Preview recovery, or post-failure idle on a real body.

Offline evidence on this review branch: patcher pre-release gate 12 container
+ 24 Python PASS; test-harness `a8b658173` 62 PASS. The exact libgphoto2
candidate `4868d3649` was regenerated with Meson: the three focused Pentax
tests and both selected camlibs (`ptp2`, `pentax`) built and passed. The
already-qualified o-v13c physical evidence remains unchanged.
No new FwPkt has been built: the changes so far affect qualification tooling
and documentation, not the installed runtime, so an identical reflash would
add no evidence.

A live canary on 2026-09-26 08:41 UTC completed a RAW exposure (state 4) and
then published the known late `-108`; the updated gate stopped after exactly
one shutter with `DONE states=[1, 4, -108] files=[]`. This is the first
physical observation of the negative-state stop path, not a pass: recovery,
Preview recovery, and post-failure idle remain owed. See
`evidence/o-v13c-canary-path-failure-2026-09-26/SUMMARY.md`.

The requested iOptron iPolar (`1233:1455`) and Orion StarShoot All-in-One
(`16c0:29a0`) are UVC devices, not PTP. Their local `uvc-devices.c` entries are
an unintegrated table, absent from the authoritative GitHub fork and with no
camlib/build implementation. The installed Polaris also exposed no UVC/V4L2
device path during the read-only audit. They must not be claimed in a release
until a real UVC backend, Polaris adapter, packaging and frame/reconnect tests
exist. See issue #151.

## 2026-09-25 convergence candidate

`o-v13c-boundary-trace-20260925` is the current **INSTALLED, RUNTIME-VERIFIED,
K-3 III TWO-SHOT CANARY PASS** candidate. It embeds libgphoto2 `4868d3649`,
patcher build `8b075f5`, and harness contract `a8b6581`; artifact bytes are
privately published at PrivateResearch `d92b1d094`. The sanctioned install
verified all six staged manifest entries before reboot; post-boot FwVer,
matched-stack hashes, loader maps and embedded provenance match the registry.

One RAW+JPEG canary and the corrected same-session two-shot gate passed. The
two shots each reported `[1,4,0]` and distinct same-stem DNG+JPEG pairs
(`SP_0086`, `SP_0087`) with no reconnect. The second shutter was not issued
until the first exposure completed, both output obligations were published,
and idle was observed. Exact transcript and remaining qualification limits are
in `evidence/o-v13c-boundary-trace-20260925/SUMMARY.md`.

The preceding o-v13 artifact was installed and failed two bounded first-shot
canaries: preview stopped and code 264 was accepted, but no shutter/completion/
773 followed and the session ended at `state:-10`. Runtime logs proved that
artifact still interposed the unsafe Stage-2 capture shim and never reached the
libgphoto2 admission trace. It is superseded; no second shutter was sent.

The minimum repeated ordinary-shutter acceptance question is now answered for
the attached K-3 III RAW+JPEG mode. Remaining physical qualification is scoped
to cancellation, Live View interaction, external mode/config changes, other
bodies/modes and soak; do not generalise this bounded pass to those paths.

A subsequent bounded Preview/Astro-equivalent check also passed: Preview was
started, suspended for three consecutive RAW+JPEG captures (`SP_0097` through
`SP_0099`, all `[1,4,0]`), then restored and confirmed ON. This qualifies the
Benro control-plane suspend/capture/restore transition, not sustained preview
JPEG delivery or the native OpenPolaris Astro UI.

## Historical installed candidates and protected fallback

As of 2026-09-24 the device had **o-v12n-companion-ownership**, build ID
`6.0.0.54.23-o-v12n-companion-ownership`, installed. It is a diagnostic
candidate, **not release-qualified**. Runtime provenance is libgphoto2
`ab0de090c` plus patcher `7bcbc39`; the registered artifact hashes are in
`FWPKT-PROVENANCE-CONTRACT.md`.

One K-3 III RAW-only first-shot canary completed with lifecycle `[1,4,0]` and
published `SP_0074.dng` (32,900,659 bytes). This proves only that one
single-output capture can complete. The same-session repeat-capture gate did
not pass: one run completed shot 1 (`SP_0078.dng`) and then lost the camera
before shot 2 was issued; a later run did not complete shot 1 and reported
`state:-10`. Do not describe o-v12n as fixing repeated capture.

The currently attached body is K-01 (`25fb:0131`). The normal product path
initializes it successfully as `pentax/k-01/state:1`; one still request
returned `-6` immediately, consistent with that separately gated model not
advertising capture support. This disproves the standalone Stage-2 CLI claim
that the package has zero supported cameras, but it does not qualify K-01 still
capture and says nothing about K-1 II. K-1 II remains **NOT TESTED** on o-v12n.

The immutable **o-v12l-recoverybaseline-20260923** artifact preserves
libgphoto2 `c0592d178`, the last source with physical first-capture Pixel Shift
RAW+JPEG completion evidence. It is privately published and registered but is
not installed and is not a final fix: its delayed companion/repeated-capture
behavior was not qualified.

The current review head is libgphoto2 `62402cc2c` on
`rescue/final-shutter-20260923`. It retains the o-v12n runtime behavior and
replaces the self-fulfilling ownership mock with a production helper used by
the real companion-publication callback. Focused Pentax tests and `ptp2.so`
compile pass. This is a source/test correction only; it does not justify a new
FwPkt until the o-v12n repeat-capture failure is understood.

## Pre-upgrade baseline (2026-09-25)

Before the 2026-09-25 upgrade work, **o-v12s-preupgrade-20260925** was built
and registered as the rollback reference: libgphoto2 `50ba504` (latest fork
head, clean checkout) + patcher main `1c1d386`, build id
`6.0.0.54.26-o-v12s-preupgrade`, pre-release gate green (4/4). It is privately
published and registered in `FWPKT-PROVENANCE-CONTRACT.md`. The earlier
attempts o-v12q and o-v12r are superseded by it (see the registry addendum).
The historical ledger and promotion matrix are in
`PENTAX-CAPTURE-VERSION-LEDGER-2026-09-23.md`.
The current audit and next-action boundary are in
`HANDOVER-2026-09-24-O-V12N-AUDIT.md`.

The protected last broadly repeated-capture baseline is **o-v9p capture isolation**, build
ID `6.0.0.54.7`. Its immutable artifact, hashes, source commits and private
location are recorded in `FWPKT-PROVENANCE-CONTRACT.md`.

Recorded K-3 III qualification passed ordinary capture, five unique
Astro-equivalent DNG captures, preview restoration with 15/15 complete JPEGs,
a final DNG, stable processes/listeners/USB and bounded DHD counters. Preserve
its separate preview and still-capture cooldowns and the package assertions
which prove the preview-throttle exports reached the final appfs.

This does **not** prove that physical focus direction, K-1 II, Canon R5 Mark II,
the packaged OpenPolaris GUI, indefinite soak, or the underlying Broadcom
driver exhaustion are fixed. Those remain open or unqualified.

Authoritative public evidence:

- `FWPKT-PROVENANCE-CONTRACT.md`
- `evidence/o-v9p-capture-isolation-2026-09-16/SUMMARY.md`
- `evidence/o-v9q-bulb-timeout-2026-09-17/SUMMARY.md`
- `TESTED.md`
- `LIBGPHOTO2-UPGRADE-PROCESS.md`

## Repository state at issue #116 cleanup

On 2026-09-18, source commit `2b56e8d` recorded the Q build-id behavior. The
issue #116 hygiene pass restored the final-package assertions for P's preview
throttling and the isolated output mount used by the package regression test.
The unrelated `.vscode/settings.json` worktree edit was deliberately untouched.

No future source change is considered deployed without a registered immutable
FwPkt, verified hashes, supported install, cold reboot and post-boot runtime
proof.

## Hardware and release rules

- Read `.github/skills/polaris-debugging/SKILL.md` before live-device work.
- Use `.github/skills/fwpkt-update-flow/SKILL.md` for every firmware install.
- Do not replace binaries directly under `/app` as a supported fix.
- Keep direct libgphoto2, Polaris runtime and OpenPolaris E2E evidence separate.
- A protocol acknowledgement is not physical focus or capture proof.
- If required hardware is unavailable, report `NOT TESTED` or `BLOCKED`.

## Focused stability programme

The active experiment design is intentionally small:

- `pentax-capture-stability-experiments.md`
- `pentax-capture-stability-experiments.schema.json`
- `pentax-physical-operative-runbook.md`
- `pentax-agent-operative-prompts.md`
- `pentax-k1ii-second-pass.md`
- `pentax-mode-aware-liveness.md`
- `../tests/README-pentax-stability.md`

The former 154-file `pentax-stability-*` planning package was preserved in the
private archive and removed from the active tree because it duplicated these
rules across many tiny, often superseded documents.

## Archived material

Raw logs, firmware-derived binaries, the fragmented stability package and the
local LM Studio review ledger were preserved before cleanup in the private
`ian-morgan99/PrivateResearch` repository:

`archives/BenroPolarisPatcher/2026-09-17-pre-context-cleanup/`

PrivateResearch archive commits: `a3dc491` (documentation and ledger) and
`8deab7e` (historical session state). Issue #116's second-stage research and
raw-evidence corpus is preserved at
`BenroPolaris/repository-hygiene-116/2026-09-18/original/`, commit `a6afa37`.

The archive contains both a commit-exact documentation tarball and a working-
tree tarball, per-file SHA-256 manifests and the pre-cleanup worktree patch.
See `ARCHIVED-EVIDENCE.md` for the public retention policy.

# Camera session questionnaire and issue-derived test gate

Prepared 2026-11-14 from the open issue trackers, their latest evidence
comments, local handoff/session ledgers, the current libgphoto2 operative cards,
and a read-only Polaris inspection. This is a preparation record, not camera
qualification.

## Current Polaris baseline

Read-only inspection at 2026-11-14 09:52 UTC reached the mount at
`root@192.168.0.1`.

```text
FwVer: 6.0.0.54.108
date: 2026.11.13
build_id: astro-v108-starved-extract-20261113
patcher_commit: 4a412fff06df7cb04597d70f75a21a77a5340e40
embedded libgphoto2 commit: 51f636d825013dcb87bab972a329114f12a7063a
selected_camlibs: ptp2,pentax
legacy_usbscsi: 1
provenance file SHA-256: b23257ac578a67d39c31e06e26192e6568ab2f94830fca69f428da09157e7e54
pgphoto.stage2ondisk SHA-256: f167e66864479060af82f012891a9df5145d14cbcb735b66a0d2317a22a082ec
libpolaris_stage2.so SHA-256: 92e2cc54036b8ac99f6ec535b840f4363aec6fc4d3a7856f31af15603743ad18
polestar_app SHA-256: a5e58ffd76670cf9bdc76560a859d2e037ca4320d37bb3c2d93d482cf459ac02
polaris-httpd SHA-256: 76c421fc1e8ba170bf89c2bf4d9a3456cdce998aba45c2bb88d2b67acd1ebac8
USB: hub 1a40:0101 and xHCI only; no 25fb:* camera
pgphoto: alive; ports 8080/8090/9090 listening
camera-info: manufacturer:none;model:none;state:-5
published camera state: Disconnected
preview-state: 1, but no camera session/camlib mapped
```

This is a useful pre-camera integration baseline. It is not a camera failure and
does not justify changing libgphoto2. The v108 embedded driver is not the
current libgphoto2 camera-code baseline `1bf8ba51a83144f16872fa8cdca6d386bc9d191f`.
Do not describe a v108 result as current-driver qualification unless a new
candidate is built with an explicit current pin and its installed bytes are
verified.

## Prepared artifacts for this morning

The direct-PC candidate has already been built and tested from clean LibGphoto2
main. The run-scoped details are:

```text
source SHA: fc1599552c268bdf863106cf3505d609ea158edc
camera-code baseline: 1bf8ba51a83144f16872fa8cdca6d386bc9d191f
build/prefix: /tmp/pentax-host-check.neyQN1VX/prefix
ptp2.so SHA-256: b9536dc8f0568237adb1f8784490994fa441fcd15854de622d44e8953acd9461
libgphoto2.so SHA-256: 9f464c7a1b51148857dbfff17d84e44431e3e9219a9a179f9570c3b8b92a30a6
PC evidence root: /tmp/pentax-window-20261114-k1ii-pc
Polaris evidence root: /tmp/polaris-window-20261114-k3iii
Polaris preflight report: /tmp/polaris-window-20261114-k3iii/layer-report.txt
K-3 III Bulb probe: /tmp/pentax-k3-probe.kExEGAYg/build/tests/pentax-bulb-qualification-probe
Bulb probe SHA-256: 2a434b0f8ac66f3921694f3f7469dc670eb22116f96ac910d4db85d3fa3ca2e2
```

The PC no-device preflight loaded the prepared `CAMLIBS` and `IOLIBS` paths and
found no Pentax attached. The Polaris preflight reached the head and found
pgphoto alive with no camera USB identity or camlib mapped. These are readiness
results, not camera results.

For the PC session, set `LD_LIBRARY_PATH` to the prepared `prefix/lib`,
`CAMLIBS` to `prefix/lib/libgphoto2/2.5.34`, and `IOLIBS` to
`prefix/lib/libgphoto2_port/0.12.2`; the first debug log must show those exact
paths before any K-1 II operation.

## Questions to answer before connecting a camera

The operator should answer these in plain language before any write, preview,
focus, capture, or cable move. An unanswered item is a gate, not an assumption.

### Camera and physical setup

- Which body is being tested first: K-1 Mark II or K-3 Mark III?
- What exact body firmware version is displayed in the camera?
- What is the camera serial number, if available, and current battery percentage?
- Is the camera externally powered, freshly charged, or running only on battery?
- Which lens is fitted, and is it safe to move focus?
- Is the memory card present, writable, and expendable? How much free space?
- Is the camera connected to the PC or Polaris for this phase?
- What exact USB personality is selected?
  - K-1 II must enumerate as PTP `25fb:0183`.
  - K-3 III must enumerate as MTP `25fb:0189`.
  - K-1 II MSC `25fb:0182` is a hard stop, not a test result.
- Is a hub, extension, or different cable in use? If yes, is it the same
  hardware as the last qualified run?
- Can the operator physically observe the shutter, lens, live-view display,
  camera USB disconnect, and whether an exposure remains active?

### Camera state before each model-specific run

- What is the physical dial position: M, B, B-lens, AstroTracer, or another mode?
- Is the camera-side Bulb timer enabled or disabled?
- Is Live View already active? If yes, can it be turned off for the
  read-only/baseline phase?
- Is the lens AF/MF switch in the state required by the selected focus card?
- What AF area/mode, drive mode, ISO, aperture, shutter, EV, image format,
  noise reduction, and Pixel Shift settings are visible?
- Is the camera in a settled shooting screen, not a menu, playback, or
  processing state?
- Are any other clients connected: Benro Connect, OpenPolaris, gphoto2,
  GVFS/MTP, or another agent?
- Which original values must be restored if a setting is changed?

### Permission and safety envelope

- Has the operator explicitly approved configuration writes?
- Has the operator explicitly approved preview/live-view frames?
- Has the operator explicitly approved ordinary capture?
- Has the operator explicitly approved Bulb, and what maximum exposure duration?
- Has the operator explicitly approved a supervised cancellation test?
- Is a physical power cycle or battery removal available if the body wedges?
- If a command is acknowledged but output or shutter state is uncertain, may the
  run stop without sending another shutter command? The required answer is yes.
- Is the operator present for the entire capture/cancel phase? Bulb is never
  unattended.

## Required execution order

Use the direct-PC/libgphoto2 cards first:
`LibGphoto2/libgphoto2/docs/pentax/CAMERA-WINDOW-OPERATIVE-CARDS.md`.

## Battery-split morning allocation

For this physical window, keep the bodies on separate hosts so each body has a
single owner and the battery change is not spent moving the same body between
hosts:

- **K-1 II → direct PC/libgphoto2.** Use the exact model string
  `Pentax K-1 Mark II (PTP mode)` and the fresh isolated host build recorded
  below. This is the camera-side LibGphoto2 qualification lane. The K-1 ISO
  helper is usable only when its source-advertised 200 baseline is present; do
  not force that helper for another baseline.
- **K-3 III → real Polaris.** Use the exact model string
  `Pentax K-3 Mark III (MTP mode)` and the generic K3-aware canary tooling. This
  is integration evidence against the installed Polaris package. Do **not** run
  the K-1-II-specific `camera-qualification-round.py` against the K-3 III, and
  do not treat this lane as direct-libgphoto2 qualification.

The two lanes may run in parallel after both independent provenance baselines
are captured, but never share a camera client. Do not start Benro Connect or
OpenPolaris during the first Polaris pass. Reserve the battery change for the
body that reaches a later recovery/Bulb gate; do not spend it during discovery,
and stop rather than forcing a low-battery capture or recovery. Bulb and any
cancellation remain last, supervised, and optional.

### K-1 II direct-PC lane

1. Prove the exact isolated loader paths and enumerate PTP `25fb:0183` as
   `Pentax K-1 Mark II (PTP mode)`; MSC `25fb:0182` is a hard stop.
2. Run source-faithful identity, live-conditions, and config reads. Use the
   K-1-specific safe helpers only after the current advertised values are
   recorded: preview, ISO round trip only from the helper's 200 baseline,
   shutter round trip, and focus with physical lens observation.
3. For every write, use live condition polling, changed-value read-back, exact
   restoration, and a fresh-session check. Stop on the first mismatch or
   malformed preview; do not retry an ambiguous shutter event.
4. Ordinary capture is optional and follows the same evidence rules. The
   K-3-only direct-PC Bulb probe is not a K-1 test; K-1 Bulb remains held unless
   an existing source-faithful K-1 procedure is identified and explicitly
   approved.

### K-3 III Polaris lane

1. Capture Polaris `/app/FwVer`, package/component hashes, and the fresh USB
   identity. Run `scripts/control-liveness.py --attempts 2` and stop if the
   service is unhealthy or the camera identity is absent.
2. Run `scripts/canary-probe.py --probe` with the exact live firmware value,
   then `--list-shutters --result-json ...` to record the advertised output
   format, exposure mode, and shutter list. These are the discovery gates.
3. Only after those gates pass, and only with explicit capture approval, run one
   `canary-probe.py --shot --require-exposure-mode` using the camera's observed
   expected file count. It is a capture gate, not a restoration test; record
   preview state, lifecycle states, output publication, and post-operation
   control state.
4. Run `canary-two-shot.py` only after the first K-3 capture is complete and
   the exact output prefix/file count are known. Use no stale candidate files
   and one client owner.
5. K-3 Bulb and cancellation are optional last gates. Do not use the held
   direct-PC K-3 Bulb probe on Polaris, do not guess a stop command, and do not
   run cancellation without direct physical observation and recovery authority.

For both lanes:

1. Record body firmware, USB identity, battery, mode, lens, media, and exact
   current source/build provenance.
2. Run read-only identity, conditions, config, and runtime-loader checks for
   the lane's own host before any write or capture.
3. Run the smallest preview/discovery gate defined for that lane and validate
   the complete result and state restoration where the lane supports it.
4. Run one setting at a time, with changed-value read-back, exact restoration,
   and fresh-session verification.
5. Run focus only after the lane's preview/readiness gate is valid and the
   physical AF/MF state is confirmed.
6. Run ordinary capture only after the preceding gates pass and the output
   contract is known.
7. Run Bulb last, with short durations first and cancellation only under direct
   observation.
8. Keep the K-1 PC and K-3 Polaris evidence roots separate; never move either
   body between hosts during this battery window.
9. On Polaris, collect `/app/FwVer`, provenance, component hashes, fresh USB
   identity, Mlog/Clog snapshots, first PTP/IPC operation, output publication,
   and post-operation control state before claiming a result.

Do not run the full historical Cartesian matrix in the short battery window.
Use the smallest test that distinguishes the competing explanations, then stop.

## Issue-derived questions and observations

### Provenance and ownership

- **libgphoto2 #48, #49, #44, #143, #164, #165:** did the direct PC test
  reproduce the first failing PTP operation, or is this only consumer evidence?
  Was the exact loaded `ptp2.so` proven?
- **Patcher #149, #216, #203, #215, #227:** which exact firmware package,
  Patcher SHA, embedded libgphoto2 SHA, and installed component hashes are
  being tested? Is the candidate a clean reproducible package?
- **OpenPolaris #56 and HardwareValidator #5/#8/#10/#11:** can the full
  source/package/runtime provenance be retained? A synthetic harness pass is
  not physical camera evidence.
- The current v108 device has libgphoto2 `51f636d`, while current main's
  camera-code baseline is `1bf8ba51a`. Which comparison is wanted:
  current v108 integration diagnosis, or a newly packaged candidate with the
  current driver? Do not silently mix them.

### USB startup, rebind, and session ownership

- **Patcher #146, #217, #238, #253, #319; libgphoto2 #33; Patcher #179:**
  was the camera already ON when Polaris/pgphoto started, or powered on later?
  Did the USB address change? Was the selected port present in the fresh port
  list immediately before init?
- Did startup exceed the 20-second readiness window? Record the time from
  process start to vendor enable, config completion, and port 8080 readiness.
- Was there exactly one pgphoto owner, one USB handle, one 8080 listener, and no
  stale restart lock?
- If the camera disappears, did only the camera generation reset, or did
  Polaris/OpenPolaris also restart, lose alignment, or lose tracking state?
- For a reconnect, did the fresh session re-read DeviceInfo, vendor mode,
  conditions, capabilities, and config instead of adopting cached values?
- Never test `25fb:0182` as if it were PTP. Record it as an operator/setup
  failure and correct the camera USB menu.

### Live View and preview

- **libgphoto2 #134, #150, #162; Patcher #147, #307, #319; OpenPolaris
  #56, #61, #74, #80, #94; HardwareValidator #3:** did the direct PC path
  receive a complete valid JPEG, and did the Polaris path receive the same
  frame bytes or fail earlier?
- What were the exact d035 start, 0x9006 frame, and d035 stop responses?
- Did the frame pass SOI/EOI and marker-walk validation?
- Was the camera in M rather than B for the first preview comparison? If B is
  tested, record the direct first failing operation rather than adding a
  blanket Bulb prohibition.
- Did preview OFF restore the original state? Did preview→capture→preview work?
- Did an iPhone/Benro Connect rendering problem occur after a valid standalone
  JPEG was already produced?
- Were two clients active? Run Benro Connect alone, OpenPolaris alone, and the
  combined case as separate supervised sessions; never conflate contention with
  a camera-driver failure.

### Settings and false-success prevention

- **libgphoto2 #143, #152, #161, #164; Patcher #323, #325, #326, #327,
  #328; OpenPolaris #62, #101:** was the requested value advertised by the
  camera, and did the changed live condition/property read back differently
  before restoration?
- For K-1 II M/B, record raw exposure mode, Tv-changeable, Bulb-timer flag,
  and offsets 272/276 before and after each shutter observation.
- Does a refused write leave the UI/widget showing the attempted value? If so,
  record camera truth separately; a cached requested value is not read-back.
- Is the `00-02`/ `00:02` issue only formatting, or does the exact target
  fail at the camera boundary?
- For aperture/ISO/EV, was the first failure at the direct PTP operation, or
  only an app-level `-2110`/timeout after a successful lower-level write?
- Do not test an unadvertised form-less scalar. The current 0xd018 domain is
  source-derived 2500..10000 K in 10 K steps, but no other domain may be
  guessed.

### Focus and autofocus

- **libgphoto2 #8, #135, #151; Patcher #234, #278, #320; OpenPolaris #76,
  #77, #92/#93:** which model-specific IT2 focus path is being exercised?
- Was the lens physically observed moving in the requested direction?
- Was AF/MF, AF area, Live View, and shooting mode recorded before the command?
- For K-1 II, did AF enable fail during init, or did the action fail after a
  valid session? Do not turn the Bulb-only `ret:-1` consumer report into a
  generic prohibition.
- For K-3 III, did the command produce 36 repeated sets or one bounded action?
  The old “only f:0–f:4” premise is disproven; repeated traffic is the
  remaining observation.

### Ordinary capture, transfer, and publication

- **libgphoto2 #44, #48, #73, #114, #115, #142; Patcher #145, #180, #181,
  #182, #192, #307; OpenPolaris #56, #60, #81; HardwareValidator #2/#12:**
  was the shutter physically observed, and how many output objects were
  expected for JPEG, RAW, and RAW+JPEG?
- Did each expected object have one owner, one transfer, a non-zero size,
  valid type/metadata, and publication before success was reported?
- Was there one or more than one file-added event for the same object?
- Did the camera remain connected, pgphoto remain alive, and the next capture
  succeed without restart?
- Was an intermediate `state:-1005` treated as non-terminal only when the
  complete lifecycle and final output proved that interpretation?
- If the result was `-110`, `-1005`, or timeout, was the outcome marked
  unknown and was another shutter blocked until candidates were reconciled?
- Did a fresh session start with no stale candidate from the prior generation?

### Bulb, long exposure, cancellation, and recovery

- **libgphoto2 #95, #106, #114, #132, #165; Patcher #148, #163, #173,
  #186, #230, #239, #241, #242, #243, #251, #317; OpenPolaris #96/#99/#100;
  HardwareValidator #2/#12:** was this Manual, camera-timed B, held-Bulb, or
  Astro Bulb? Record physical dial and camera-side timer separately.
- Did the requested duration become a pre-shot delay? Measure shutter-open
  time independently with EXIF/PTP evidence; app sleep duration is not sensor
  exposure evidence.
- Was the duration actually set on the camera, or merely echoed by the app?
  Command 268 list shape is supporting evidence only, not a dial oracle.
- For held Bulb, did start arm the shutter and did stop physically close it?
  For camera-timed Bulb, did the normal timed path set the advertised duration?
  These are separate paths.
- During cancellation, did the shutter close, did an output still become
  obligated, and was that output reconciled? Never clear ownership merely
  because the caller stopped waiting.
- Did cancellation of a deferred camera-timed start accidentally issue a new
  exposure? This remains a direct-reproducer requirement from #251.
- Did processing/NR/dark-frame time exceed the completion deadline without
  causing a false failure?
- After a failed or cancelled capture, did the next ordinary capture succeed?
- Did the body leave USB after capture, and if so did the app/daemon recover
  without a Polaris reboot?
- Do not repeat the historical v101 42-second success as a cancellation pass:
  it proved one file-producing timed event but did not test red-cancel or
  physical stop.

## Tests explicitly not to repeat as conclusions

- Older v92/v94 claims are historical unless the exact candidate and loaded
  bytes are reproduced. The v101 matrix supersedes older planning evidence but
  still leaves cancellation and preview restoration open.
- The v104 raw-format theory for #317 was disproven by same-format success.
- The #320 “higher focus values are missing” premise was disproven; repeated
  focus traffic is the remaining observation.
- #318's USB compatibility-menu setting is not observable by Polaris and must
  not become a guessed WebUI gate.
- #323/#326 model/vendor checks are present in the config API path; they are not
  evidence that a physical write succeeded.
- #161's libgphoto2 parser fix is in current main, but the v105 UI spelling and
  current packaged runtime still need separate confirmation.
- A host gate, emulator, replay harness, PTP acknowledgement, app return code,
  file presence, or clean process exit is not physical qualification by itself.

## Stop conditions

Stop the session and preserve evidence on any of the following:

- wrong USB personality, unknown body firmware, or unproven runtime library;
- a write is not advertised, does not read back, or cannot be restored;
- preview yields malformed/zero bytes or fails to restore;
- the first failing PTP operation is unknown;
- shutter state, cancellation state, or output ownership is ambiguous;
- the camera leaves USB or pgphoto restarts unexpectedly;
- a second client appears during a single-owner test;
- the operator cannot physically observe the body;
- battery headroom is insufficient for the next recovery/fresh-session gate.

The permitted result is `UNKNOWN` when the evidence is incomplete. Do not turn
an unknown into a pass by running a later successful command.

## Evidence packet

Create one immutable directory per body/session. Store:

```text
00-operator-answers.txt
01-provenance.txt
02-usb-and-process-baseline.txt
03-conditions-before.txt
04-command-and-debug-logs/
05-preview-or-capture-outputs/
06-conditions-after.txt
07-fresh-session-check.txt
08-result.md
```

Every result must state: lane, exact camera/body firmware, USB identity, loaded
library/camlib SHA, Patcher/FwVer/provenance for Polaris, first failing PTP or
IPC operation, application/read-back evidence, restoration, fresh-session
evidence, physical observation, and PASS/FAIL/BLOCKED/UNKNOWN classification.


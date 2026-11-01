# Issue 251 dispatcher follow-up — source and ARM tests only

Base patcher main: `75266c1b15d50b7b5f9ae03acb306b3de6255875`.
Library main, unchanged: `051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff`.
The implementation and tests in this commit are the reviewed source; hashes
are in `tested-source.sha256`. No firmware version was claimed or package
created, published or installed. No device or camera was accessed.

## Changes and their bounds

1. Require a successful `GP_WIDGET_TEXT` type query before interpreting a
   widget value as a pointer. Initialize the widget/type slots and clear the
   reused text-output slot before reading it. Read borrowed text only while
   its widget is alive; free each successfully acquired widget once.
2. Fail with `GP_ERROR_CAMERA_BUSY` for a selected-model read failure or an
   invalid exposure-mode field; do not fall through to an ordinary shot.
   Validate the canonical field delimiter, unsigned decimal, semicolon,
   range 0–31 and absence of duplicate exact keys. This does not validate
   every other field or every possible misspelling of a duplicate key.
3. Match the complete registered abilities label
   `Pentax:K-3 Mark III (MTP mode)`, case-insensitively, not a substring or a
   guessed UI display name. Other registered bodies retain stock dispatch.
4. Recover the existing ARM tests and cancellation diagnostic into main,
   extending the former for omitted outputs and exact model names. Register
   the dispatcher tests in the normal offline test list. The general-purpose
   emulator project remains separate in test-harness issue #15.

The existing routing remains: positive duration/status 0 for the selected
K-3 III reads conditions once; recognized modes 9/12/20 enter the existing
Bulb helper, other recognized values enter stock capture. There is no new
polling loop, vendor command, retry, library change, timing algorithm or
shared stop-path change. The cave grows from 544 to 768 bytes for validation,
not a new capture architecture. Original argument/stack restoration remains.

## Source anchors

- Exact library `libgphoto2/gphoto2-widget.c:345,435`: type getter and text
  getter contracts. `gp_widget_free` releases the borrowed string.
- `libgphoto2/gphoto2-camera.c:204,356`: private core starts with speed then
  `CameraAbilities`; set-abilities copies the registered model label.
- `camlibs/ptp2/library.c:2848`: `25fb:0189` has the full label above.
  Stock `getCameraName` at `0xfdad4` reads private-core offset 4 and calls
  `strncpy_lower` with 128. It returns status, not the text pointer.
  `gp_widget_get_type` at `0x4290c` was also checked in that stock ELF.
- `camlibs/ptp2/config.c:9445` (`_get_Pentax_Conditions`) obtains and parses
  GetAllConditions and emits `; exposure-mode-raw=%u;` in a TEXT widget.
- Local normative `IT2_2625_decompile/RemoteAssistant/ExpMode.cs` defines
  0–31, including M=8, B=9, B_Lens=12, AstroTracer=20. SHA-256:
  `b08234c59a5c4ebb75083ac6b2323d617897ae76fcafd5c0822d9467789a291a`.
  `MtpDevice.cs:4840` distinguishes the existing B/lens-B/Astro modes and
  timer flag; `CamRelease` near 3701 separates an active release from a new
  release. SHA-256:
  `e8d11ed772aad3731d7eabd0c06fb0174aae859c5a1f6d241bf73b6d046de059`.
  Recognizing an enum value is not evidence that every body supports it.

## Executable evidence

- Full documented offline gate with the exact library input: 10 aggregate
  checks pass, 0 fail, 0 skip. Its Python suite is **482 pass / 8 skip**;
  its deterministic suite is **25 pass / 0 fail / 2 prerequisite skips**
  (`test_source_input.sh`, `test_polaris_pentax_build_package.sh`). Those
  sub-suite skips remain recorded despite the aggregate summary. No package
  or device gate ran. This green result excludes the separate RED cancel
  diagnostic below and is not release clearance.
- 85 dispatcher ARM tests pass with Unicorn 2.1.4. They exercise all 32
  recognized modes, invalid fields, duplicate keys, guard-page string ends,
  missing outputs, exact-name matches/mismatches, widget lifetime,
  caller-saved register clobbering, stack alignment and restored arguments.
- Before the changes, the unchanged main instructions routed failed config,
  failed value and null-text reads into stock capture. The parser tests then
  reproduced 21 failures; exact-label tests reproduced four false matches.
  An omitted text output also reproduced pointer value `2` in the recovered
  narrow WIP. Each corresponding test passes after its correction.
- The retained stock ELF (`0308393632dd41d974bd1064e61942655131fe5392959a334cf24623d1bd4a62`)
  accepts the patch, its marker check and idempotent recheck. The temporary
  patched copy is `52f0727b59ed7e27681e224973132bbce634f89969da63d61553b934ea042311`.
  This is patch-layout evidence, not an executable firmware package.
- Stage-2 cross-compilation passes with the installed ARM compiler and
  `-Wall -Wextra -Werror`. The unchanged clean-library Meson tests pass 20/20,
  excluding the documented hardware-dependent `no-ci` suite. Meson host
  tests are not the shipped ARM/autotools configuration.

These CPU tests simulate the external functions, not PTP, a real camera,
installed Stage-2 interposition, shutter movement or file publication.

## The cancellation diagnostic remains RED

`tools/audit_polaris_bulb_cancel.py` accepts only the saved v90 SHA-256
`8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`.
It checks the old marker, reverses only known patch bytes in memory, applies
the current dispatcher, and executes the actual helper return path with
simulated stop/event/file callbacks. The saved input is never modified.

Fresh result: cancelled wait `-52` + successful stop `0` returns **0**, not
`-52`; a failed stop `-1` returns `-1`. The script exits **1**. See
`cancel-return.txt`. This diagnostic is separate from the default offline
suite: a green default suite does not clear this known failing test.

The deferred camera-timed fallback is an additional unresolved risk:
`library.c:7817` turns `bulb=0` into a new timed capture, whereas an already
held exposure needs a real stop. Preserving a return code alone cannot fix
both. Message `264/state:0` and context cancellation also use different flags.
Do not silently skip stop, suppress this failure, close #251 or deploy these
partial changes as a cancellation fix. The missing timed-B list and Manual
wheel physical acceptance also remain open.

## Reproduce without hardware

Use an isolated environment with the existing pytest/pyelftools dependencies
and Unicorn 2.1.4; this run used `/tmp/polaris-251-arm-tests-20261030`. Only
that temporary environment received the free test dependency. No system
package or hardware configuration was changed.

```sh
python -m pytest -q tests/test_polaris_bulb_dispatch_arm.py
./tests/run_prerelease_gate.sh --libgphoto2-src /path/to/clean/libgphoto2-main
python tools/audit_polaris_bulb_cancel.py /path/to/exact/v90/pgphoto.stage2ondisk
```

Put the isolated environment's `bin` first on PATH for the gate. Without
Unicorn the dispatcher suite explicitly skips; the cancellation diagnostic
cannot run. Its historical patcher lookup also requires commit `f344e412`
(fetch the archive tag/full history if using a shallow clone).

## Impact and next boundary

Pentax-only new dispatch behavior: yes, after the exact abilities-label gate.
Generic libgphoto2/PTP2 changed: no. Other vendors: stock dispatch retained,
including original arguments and prologue, with simulated Canon coverage.
The pre-existing shared-helper cancellation issue still potentially affects
other cameras; this change does not alter that helper. Physical non-Pentax
evidence for this change: none. No qualification is claimed for any body.

Next work must distinguish normal expiry, message stop and context cancel
through cleanup, preserve errors and output handling, and prevent a cancelled
deferred start from creating an exposure while still closing a held shutter.
Follow the repository's direct-libgphoto2 reproduction rule before changing
the library for this consumer symptom. Then use the canonical release process
and separately supervised, short-exposure hardware gates.
